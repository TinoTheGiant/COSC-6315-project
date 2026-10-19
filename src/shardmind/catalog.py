"""The fragment catalogue: what the data is cut into, and where each piece lives.

A fragment is a contiguous, half-open run of keyspace cells ``[lo, hi)``. The
catalogue therefore is fully described by a strictly increasing boundary vector
starting at 0 and ending at ``n_cells``, plus a primary region and a replica set
per fragment. Representing fragments over cells rather than as opaque objects is
what makes ``split`` and ``merge`` meaningful: a fragment spanning cells whose
traffic comes from different parts of the world can be cut so that each half
follows its own traffic.

All five mutators are *declarative*: each names a desired end state rather than
an operation, and each is defined in every state. When the requested end state
already holds, or a limit forbids it, the mutator reports ``applied=False`` and
changes nothing. The environment charges a small fixed cost for that outcome.
This is what removes the need for action masking, which DQN does not provide.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from shardmind.config import CatalogConfig


@dataclass(frozen=True)
class MutationResult:
    """Outcome of one declarative mutation.

    Attributes
    ----------
    applied:
        Whether the catalogue changed.
    bytes_moved:
        Data transferred over the wide area to bring the new state about.
        Dropping a replica is free; acquiring one costs the fragment's size.
    reason:
        Why an unapplied mutation was refused. Diagnostics only.
    """

    applied: bool
    bytes_moved: float = 0.0
    reason: str = ""


class FragmentCatalog:
    """Mutable fragmentation and placement state.

    Invariants, checked by :meth:`validate`:

    1. ``boundaries[0] == 0`` and ``boundaries[-1] == n_cells``, strictly increasing,
       so the fragments partition the keyspace with no gap and no overlap.
    2. ``1 <= n_fragments <= max_fragments``.
    3. every fragment holds between ``min_replicas`` and ``max_replicas`` replicas;
    4. every fragment's primary is one of its replicas.
    """

    def __init__(
        self,
        cfg: CatalogConfig,
        n_cells: int,
        n_regions: int,
        boundaries: np.ndarray | None = None,
        primary: np.ndarray | None = None,
        replicas: np.ndarray | None = None,
    ) -> None:
        self.cfg = cfg
        self.n_cells = int(n_cells)
        self.n_regions = int(n_regions)

        if boundaries is None:
            self.boundaries = _even_boundaries(self.n_cells, cfg.initial_fragments)
            self.primary, self.replicas = self._initial_placement()
        else:
            self.boundaries = np.asarray(boundaries, dtype=np.int64).copy()
            if primary is None or replicas is None:
                raise ValueError("primary and replicas must accompany explicit boundaries")
            self.primary = np.asarray(primary, dtype=np.int64).copy()
            self.replicas = np.asarray(replicas, dtype=bool).copy()

        self.validate()

    # ----------------------------------------------------------- construction

    def _initial_placement(self) -> tuple[np.ndarray, np.ndarray]:
        cfg = self.cfg
        f = self.n_fragments
        if cfg.initial_placement == "hash":
            primary = np.arange(f, dtype=np.int64) % self.n_regions
        elif cfg.initial_placement == "single_region":
            primary = np.zeros(f, dtype=np.int64)
        else:  # pragma: no cover - guarded by the Literal type
            raise ValueError(f"unknown initial_placement {cfg.initial_placement!r}")

        replicas = np.zeros((f, self.n_regions), dtype=bool)
        for i in range(f):
            # Primary plus the next (min_replicas - 1) regions round robin: the
            # rack-unaware default a hash partitioner with a replication factor
            # would produce.
            for j in range(cfg.min_replicas):
                replicas[i, (primary[i] + j) % self.n_regions] = True
        return primary, replicas

    def copy(self) -> "FragmentCatalog":
        return FragmentCatalog(
            self.cfg,
            self.n_cells,
            self.n_regions,
            self.boundaries,
            self.primary,
            self.replicas,
        )

    # -------------------------------------------------------------- geometry

    @property
    def n_fragments(self) -> int:
        return len(self.boundaries) - 1

    @property
    def sizes_cells(self) -> np.ndarray:
        """``(F,)`` number of cells in each fragment."""
        return np.diff(self.boundaries)

    @property
    def sizes_bytes(self) -> np.ndarray:
        """``(F,)`` bytes in each fragment, pro rata by cell count."""
        return self.cfg.dataset_bytes * self.sizes_cells / self.n_cells

    @property
    def replica_counts(self) -> np.ndarray:
        return self.replicas.sum(axis=1)

    def cell_to_fragment(self) -> np.ndarray:
        """``(n_cells,)`` fragment index owning each cell."""
        return np.repeat(np.arange(self.n_fragments), self.sizes_cells)

    def aggregate_cells(self, per_cell: np.ndarray) -> np.ndarray:
        """Sum a ``(n_cells, ...)`` array into ``(n_fragments, ...)``."""
        if per_cell.shape[0] != self.n_cells:
            raise ValueError(f"expected leading axis {self.n_cells}, got {per_cell.shape[0]}")
        return np.add.reduceat(per_cell, self.boundaries[:-1], axis=0)

    def storage_bytes_per_region(self) -> np.ndarray:
        """``(R,)`` bytes stored in each region across all replicas."""
        return self.replicas.T.astype(np.float64) @ self.sizes_bytes

    # -------------------------------------------------------------- mutators

    def set_primary(self, fragment: int, region: int) -> MutationResult:
        """Make ``region`` the primary of ``fragment``.

        If the region does not already hold a replica it acquires one, which
        costs the fragment's size in bytes. If the fragment is already at
        ``max_replicas`` the outgoing primary's replica is released to make
        room, which keeps the action applicable in every state.
        """
        self._check(fragment, region)
        if self.primary[fragment] == region:
            return MutationResult(False, 0.0, "already primary")

        old = int(self.primary[fragment])
        moved = 0.0
        if not self.replicas[fragment, region]:
            if self.replica_counts[fragment] >= self.cfg.max_replicas:
                self.replicas[fragment, old] = False
            self.replicas[fragment, region] = True
            moved = float(self.sizes_bytes[fragment])

        self.primary[fragment] = region
        return MutationResult(True, moved, "")

    def ensure_replica(self, fragment: int, region: int) -> MutationResult:
        """Guarantee a replica of ``fragment`` in ``region``."""
        self._check(fragment, region)
        if self.replicas[fragment, region]:
            return MutationResult(False, 0.0, "replica already present")
        if self.replica_counts[fragment] >= self.cfg.max_replicas:
            return MutationResult(False, 0.0, "at max_replicas")

        self.replicas[fragment, region] = True
        return MutationResult(True, float(self.sizes_bytes[fragment]), "")

    def drop_replica(self, fragment: int, region: int) -> MutationResult:
        """Guarantee no replica of ``fragment`` in ``region``.

        Refused for the primary: demote it with :meth:`set_primary` first. This
        keeps the primary-is-a-replica invariant a property of the type rather
        than of the caller's discipline.
        """
        self._check(fragment, region)
        if not self.replicas[fragment, region]:
            return MutationResult(False, 0.0, "no replica present")
        if self.primary[fragment] == region:
            return MutationResult(False, 0.0, "cannot drop the primary")
        if self.replica_counts[fragment] <= self.cfg.min_replicas:
            return MutationResult(False, 0.0, "at min_replicas")

        self.replicas[fragment, region] = False
        return MutationResult(True, 0.0, "")

    def move_lease(self, fragment: int, region: int) -> MutationResult:
        """Make ``region`` the primary of ``fragment``, without moving data.

        Refused when ``region`` holds no replica. That restriction is not
        fastidiousness: it is what CockroachDB enforces. ``ALTER RANGE ...
        RELOCATE LEASE TO <store>`` only works to a store that already holds a
        voting replica, which Cluster pilot #1 discovered by asking for
        leaseholders in six regions and getting two (`docs/results-log.md`).

        Keeping the restriction here is what preserves the two-tier cost
        structure: a lease move costs one round trip and no bytes, a replica
        move costs a fragment. Fusing them, as :meth:`set_primary` does, buys
        action-space density at the price of the distinction ADR-0009 chose
        CockroachDB to obtain.
        """
        self._check(fragment, region)
        if not self.replicas[fragment, region]:
            return MutationResult(False, 0.0, "no replica in that region")
        if self.primary[fragment] == region:
            return MutationResult(False, 0.0, "already primary")
        self.primary[fragment] = region
        return MutationResult(True, 0.0, "")

    def move_replica_to(self, fragment: int, region: int, rtt: np.ndarray) -> MutationResult:
        """Ensure ``fragment`` has a replica in ``region``, at constant count.

        The replication factor is fixed (ADR-0009), so acquiring a replica
        means releasing one. The released replica is **the non-primary replica
        whose region is farthest from** ``region`` by round-trip time. That
        tie-break is part of the action's semantics, not an implementation
        detail, and the paper must state it: the agent names only a
        destination, so the source is chosen for it.

        Naming both ends instead would need ``F * R * R`` actions, 720 at the
        default shape against 120 here, and measured 16.8% applicable against
        33.6%. Breadth-first search over the replica-set state space confirms
        the tie-break costs no reachability: every placement remains reachable,
        with a worst-case path of 5 actions against 3 when both ends are named.
        """
        self._check(fragment, region)
        if self.replicas[fragment, region]:
            return MutationResult(False, 0.0, "replica already present")

        held = [r for r in range(self.n_regions)
                if self.replicas[fragment, r] and r != self.primary[fragment]]
        if not held:                      # degenerate: RF 1, the primary alone
            held = [int(self.primary[fragment])]
        donor = max(held, key=lambda r: float(rtt[r, region]))

        self.replicas[fragment, donor] = False
        self.replicas[fragment, region] = True
        if self.primary[fragment] == donor:
            self.primary[fragment] = region
        return MutationResult(True, float(self.sizes_bytes[fragment]), "")

    def split(self, fragment: int) -> MutationResult:
        """Cut ``fragment`` in half at its midpoint cell.

        Both halves inherit the parent's placement, so no data crosses the wide
        area: the split is a catalogue edit, not a migration. The halves can
        then diverge under later allocation actions, which is the entire point
        of making granularity a decision variable.
        """
        self._check(fragment)
        if self.n_fragments >= self.cfg.max_fragments:
            return MutationResult(False, 0.0, "at max_fragments")
        lo, hi = int(self.boundaries[fragment]), int(self.boundaries[fragment + 1])
        if hi - lo < 2:
            return MutationResult(False, 0.0, "fragment is a single cell")

        mid = lo + (hi - lo) // 2
        self.boundaries = np.insert(self.boundaries, fragment + 1, mid)
        self.primary = np.insert(self.primary, fragment + 1, self.primary[fragment])
        self.replicas = np.insert(self.replicas, fragment + 1, self.replicas[fragment], axis=0)
        return MutationResult(True, 0.0, "")

    def merge(self, fragment: int) -> MutationResult:
        """Absorb ``fragment + 1`` into ``fragment``.

        The merged fragment keeps the left fragment's placement. The right
        fragment's data must therefore be copied to every region in the left's
        replica set that did not already hold it, which is where the cost comes
        from. Merging is how the agent recovers from over-splitting.
        """
        self._check(fragment)
        if fragment >= self.n_fragments - 1:
            return MutationResult(False, 0.0, "no right neighbour")

        left_set = self.replicas[fragment]
        right_set = self.replicas[fragment + 1]
        newly_covered = int(np.count_nonzero(left_set & ~right_set))
        moved = float(self.sizes_bytes[fragment + 1]) * newly_covered

        self.boundaries = np.delete(self.boundaries, fragment + 1)
        self.primary = np.delete(self.primary, fragment + 1)
        self.replicas = np.delete(self.replicas, fragment + 1, axis=0)
        return MutationResult(True, moved, "")

    # ------------------------------------------------------------ validation

    def _check(self, fragment: int, region: int | None = None) -> None:
        if not 0 <= fragment < self.n_fragments:
            raise IndexError(f"fragment {fragment} out of range [0, {self.n_fragments})")
        if region is not None and not 0 <= region < self.n_regions:
            raise IndexError(f"region {region} out of range [0, {self.n_regions})")

    def validate(self) -> None:
        """Raise ``AssertionError`` if any catalogue invariant is broken."""
        b = self.boundaries
        assert b[0] == 0, "keyspace must start at cell 0"
        assert b[-1] == self.n_cells, "keyspace must end at n_cells"
        assert np.all(np.diff(b) >= 1), "fragments must be non-empty and ordered"
        assert 1 <= self.n_fragments <= self.cfg.max_fragments, "fragment count out of range"
        assert self.primary.shape == (self.n_fragments,), "primary vector is the wrong shape"
        assert self.replicas.shape == (self.n_fragments, self.n_regions), "replica matrix shape"

        counts = self.replica_counts
        assert np.all(counts >= self.cfg.min_replicas), "a fragment is under-replicated"
        assert np.all(counts <= self.cfg.max_replicas), "a fragment is over-replicated"
        assert np.all(
            self.replicas[np.arange(self.n_fragments), self.primary]
        ), "a primary does not hold a replica"

    def summary(self) -> str:
        lines = [f"{self.n_fragments} fragments over {self.n_cells} cells"]
        for i in range(self.n_fragments):
            members = ",".join(str(r) for r in np.flatnonzero(self.replicas[i]))
            lines.append(
                f"  f{i:<2d} cells [{self.boundaries[i]:>4d},{self.boundaries[i + 1]:>4d})"
                f"  primary=r{self.primary[i]}  replicas={{{members}}}"
            )
        return "\n".join(lines)


def _even_boundaries(n_cells: int, n_fragments: int) -> np.ndarray:
    """Boundary vector splitting ``n_cells`` into ``n_fragments`` near-equal runs."""
    if not 1 <= n_fragments <= n_cells:
        raise ValueError("require 1 <= n_fragments <= n_cells")
    edges = np.linspace(0, n_cells, n_fragments + 1)
    return np.unique(np.round(edges).astype(np.int64))
