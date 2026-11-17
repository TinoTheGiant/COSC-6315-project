"""Exact per-window oracle at fixed shard boundaries.

For one window of demand, find the placement of every shard's primary and
replicas that minimizes total request latency under the cost model in
:mod:`fragalloc.cost`, with movement free and the shard boundaries held as
they are. The result is a lower bound on the mean latency of any placement
with those boundaries in that window, so no policy that does not split can
score below it. A policy that splits changes the boundaries and can.

Why exhaustive search is affordable. With strong reads (``primary_only``)
every term of the cost model except two-phase commit depends on one shard's
primary alone:

* a read costs the round trip from its origin to the primary;
* a write adds the replication wait, which, with replicas free to place, is
  smallest when the followers are the regions nearest the primary, so it is
  a function of the primary only;
* a transaction member costs what the same single-key read or write costs.

Only the commit coordination of a multi-region transaction couples shards,
and each transaction template touches a handful of them, so its cost is a
small table over the primaries of its members. Total latency for every one of
``n_regions ** n_fragments`` assignments is then a sum of table lookups. The
simulator starts every episode with six shards over six regions, 46,656
assignments.

The answer is cross-checked: :func:`exact_oracle` builds the winning catalog
and the caller can score it with :func:`fragalloc.cost.evaluate`; the test
suite asserts the two totals agree and that no sampled placement scores lower.
"""

from __future__ import annotations

import itertools

import numpy as np

from fragalloc.catalog import FragmentCatalog
from fragalloc.config import CostConfig
from fragalloc.topology import Topology
from fragalloc.workload import WorkloadGenerator, WorkloadWindow

#: Refuse searches larger than this many assignments rather than run for hours.
MAX_ASSIGNMENTS = 2_000_000


def follower_wait(topology: Topology, cfg: CostConfig, n_replicas: int) -> np.ndarray:
    """``(R,)`` smallest replication wait achievable with the primary in each region.

    Followers are placed in the regions nearest the primary, which minimizes
    the wait under every acknowledgement rule the cost model supports.
    """
    rtt = topology.rtt
    n_regions = topology.n_regions
    wait = np.zeros(n_regions, dtype=np.float64)
    if cfg.write_ack == "primary" or n_replicas <= 1:
        return wait
    for p in range(n_regions):
        others = np.sort(np.delete(rtt[p], p))[: n_replicas - 1]
        if cfg.write_ack == "all":
            wait[p] = others[-1]
        else:  # majority, counting the leader's own vote
            needed = (n_replicas // 2 + 1) - 1
            wait[p] = others[needed - 1] if needed > 0 else 0.0
    return wait


def nearest_replicas(topology: Topology, primary: int, n_replicas: int) -> list[int]:
    """The primary and the ``n_replicas - 1`` regions nearest it."""
    order = [int(r) for r in np.argsort(topology.rtt[primary], kind="stable") if r != primary]
    return [primary] + order[: n_replicas - 1]


def _coordination(participants: tuple[int, ...], rtt: np.ndarray) -> np.ndarray:
    """``(R,)`` two-phase-commit cost by origin for one participant set."""
    part = np.array(sorted(set(participants)))
    if part.size <= 1:
        return np.zeros(rtt.shape[0])
    farthest = rtt[np.ix_(part, part)].max(axis=1)  # per candidate coordinator
    cost = rtt[:, part] + 2.0 * farthest[None, :]  # (origin, coordinator)
    return cost.min(axis=1)


def placement_totals(
    catalog: FragmentCatalog,
    window: WorkloadWindow,
    generator: WorkloadGenerator,
    topology: Topology,
    cfg: CostConfig,
) -> tuple[np.ndarray, np.ndarray]:
    """Every primary assignment and its total latency (ms x requests).

    Row ``i`` of the first array assigns a region to each shard; the second
    array is the latency that assignment costs with followers in the regions
    nearest each primary. Only strong reads are supported, which is how every
    result in the paper is run.
    """
    if cfg.read_consistency != "primary_only":
        raise NotImplementedError("the exact oracle assumes primary_only reads")

    rtt = topology.rtt
    n_regions = topology.n_regions
    n_frag = catalog.n_fragments
    n_assign = n_regions**n_frag
    if n_assign > MAX_ASSIGNMENTS:
        raise ValueError(f"{n_assign} assignments exceed the exhaustive-search limit")

    n_replicas = int(catalog.cfg.max_replicas)
    wait = follower_wait(topology, cfg, n_replicas)  # (P,)

    reads = catalog.aggregate_cells(window.reads)  # (F, O)
    writes = catalog.aggregate_cells(window.writes)  # (F, O)
    txn = window.txn_counts  # (T, O)
    txn_total = txn.sum(axis=1)  # (T,)

    # Separable part: cost[f, p] if shard f's primary is region p.
    separable = reads @ rtt + writes @ rtt + writes.sum(axis=1)[:, None] * wait[None, :]
    member_frag = catalog.cell_to_fragment()[generator.template_cells]  # (T, A)
    is_write = generator.template_is_write  # (T, A)
    txn_to = txn @ rtt  # (T, P): members' round trips, by primary
    for a in range(member_frag.shape[1]):
        np.add.at(separable, member_frag[:, a], txn_to + (is_write[:, a] * txn_total)[:, None] * wait)

    assignments = np.array(list(itertools.product(range(n_regions), repeat=n_frag)), dtype=np.int64)
    total = separable[np.arange(n_frag)[None, :], assignments].sum(axis=1)

    if cfg.two_phase_commit:
        width = member_frag.shape[1]
        combos = list(itertools.product(range(n_regions), repeat=width))
        coord = np.array([_coordination(c, rtt) for c in combos])  # (P**A, O)
        radix = n_regions ** np.arange(width - 1, -1, -1)
        for t in range(member_frag.shape[0]):
            table = coord @ txn[t]  # (P**A,)
            index = assignments[:, member_frag[t]] @ radix
            total += table[index]

    return assignments, total


def placed_catalog(catalog: FragmentCatalog, topology: Topology, primary: np.ndarray) -> FragmentCatalog:
    """``catalog``'s shards with the given primaries and nearest-region followers."""
    n_replicas = int(catalog.cfg.max_replicas)
    replicas = np.zeros_like(catalog.replicas)
    for f, p in enumerate(primary):
        replicas[f, nearest_replicas(topology, int(p), n_replicas)] = True
    placed = catalog.copy()
    placed.primary = np.asarray(primary, dtype=np.int64).copy()
    placed.replicas = replicas
    return placed


def exact_oracle(
    catalog: FragmentCatalog,
    window: WorkloadWindow,
    generator: WorkloadGenerator,
    topology: Topology,
    cfg: CostConfig,
) -> tuple[FragmentCatalog, float]:
    """The latency-minimizing catalog for ``window`` and its total latency.

    Shard boundaries are those of ``catalog``; primaries and replicas are
    chosen freely.
    """
    assignments, total = placement_totals(catalog, window, generator, topology, cfg)
    best = int(np.argmin(total))
    return placed_catalog(catalog, topology, assignments[best]), float(total[best])
