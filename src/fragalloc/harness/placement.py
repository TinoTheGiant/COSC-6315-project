"""Placement on the real cluster: resolve, read back, reconcile.

The simulator's ``FragmentCatalog`` says what the placement *should* be; the
cluster is the authority on what it *is*. This module turns CockroachDB's view
into a ``FragmentCatalog`` of exactly the simulator's shape, and compares the
two. It is steps 2, 4 and 5 of the step protocol in
docs/harness-architecture.md, and its correctness is the harness's: a silent
divergence between intent and cluster is a corrupted reward.

Mapping between the two worlds:

* **Cells to keys.** The harness table has an integer primary key. Cell ``c``
  owns keys ``[c * rows_per_cell, (c + 1) * rows_per_cell)``, so a fragment
  boundary at cell ``c`` is a CockroachDB split at key ``c * rows_per_cell``.
* **Fragments to ranges.** One range per fragment, in key order. The split and
  merge queues are disabled (``scripts/cluster.sh verify``), so the only splits
  are the harness's own.
* **Regions to stores.** Resolved from each node's ``--locality=region=...``,
  never assumed from join order, which is nondeterministic (Cluster pilot #1).
* **Primary to leaseholder; replicas to voting replicas.**

Everything here talks to the database through :class:`Sql`, a one-method
interface, so the parsing and reconciliation rules are unit-tested without a
cluster. ``scripts/placement_check.py`` exercises them against a real one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

import numpy as np

from fragalloc.catalog import FragmentCatalog
from fragalloc.config import FragAllocConfig


class PlacementError(RuntimeError):
    """The cluster's placement cannot be read as a valid catalogue."""


class Sql(Protocol):
    """The one thing the harness needs from a database connection."""

    def query(self, stmt: str, params: Sequence[Any] = ()) -> list[tuple]:
        ...


class PsycopgSql:
    """:class:`Sql` over a psycopg connection, in autocommit mode."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    @classmethod
    def connect(cls, host: str = "127.0.0.1", port: int = 26257,
                dbname: str = "defaultdb") -> "PsycopgSql":
        import psycopg

        return cls(psycopg.connect(host=host, port=port, user="root", dbname=dbname,
                                   autocommit=True, connect_timeout=10))

    def query(self, stmt: str, params: Sequence[Any] = ()) -> list[tuple]:
        with self.conn.cursor() as cur:
            cur.execute(stmt, tuple(params) or None)
            return list(cur.fetchall()) if cur.description else []

    def close(self) -> None:
        self.conn.close()


# ----------------------------------------------------------------- layout

@dataclass(frozen=True)
class TableLayout:
    """How the simulator's cells are laid out as rows of one table."""

    table: str = "fragalloc"
    n_cells: int = 256
    rows_per_cell: int = 16

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", self.table):
            raise ValueError(f"unsafe table name {self.table!r}")
        if self.n_cells < 1 or self.rows_per_cell < 2:
            raise ValueError("need n_cells >= 1 and rows_per_cell >= 2")

    @classmethod
    def from_config(cls, cfg: FragAllocConfig, table: str = "fragalloc",
                    rows_per_cell: int = 16) -> "TableLayout":
        return cls(table=table, n_cells=cfg.workload.n_cells, rows_per_cell=rows_per_cell)

    def cell_key(self, cell: int) -> int:
        return int(cell) * self.rows_per_cell

    @property
    def n_rows(self) -> int:
        return self.n_cells * self.rows_per_cell


def create_table(sql: Sql, layout: TableLayout, boundaries: Sequence[int],
                 payload_bytes: int = 64) -> None:
    """(Re)create the harness table, split at the given fragment boundaries."""
    b = [int(x) for x in boundaries]
    if b[0] != 0 or b[-1] != layout.n_cells or any(y <= x for x, y in zip(b, b[1:])):
        raise ValueError(f"boundaries must rise strictly from 0 to {layout.n_cells}: {b}")
    t = layout.table
    sql.query(f"DROP TABLE IF EXISTS {t}")
    sql.query(f"CREATE TABLE {t} (k INT8 PRIMARY KEY, v STRING)")
    if len(b) > 2:
        points = ", ".join(f"({layout.cell_key(c)})" for c in b[1:-1])
        sql.query(f"ALTER TABLE {t} SPLIT AT VALUES {points}")
    sql.query(f"INSERT INTO {t} SELECT g, repeat('x', {int(payload_bytes)}) "
              f"FROM generate_series(0, {layout.n_rows - 1}) AS g")


# ----------------------------------------------------------------- stores

@dataclass(frozen=True)
class StoreMap:
    """Region index <-> CockroachDB store id, resolved from the cluster."""

    region_names: tuple[str, ...]
    store_of_region: tuple[int, ...]

    def region_of(self, store: int) -> int:
        try:
            return self.store_of_region.index(int(store))
        except ValueError:
            raise PlacementError(
                f"store {store} belongs to no configured region; stores are "
                f"{dict(zip(self.region_names, self.store_of_region))}") from None


def parse_region(locality: str) -> str | None:
    """``'region=us-east-1,zone=a'`` -> ``'us-east-1'``."""
    for part in str(locality).split(","):
        key, _, value = part.strip().partition("=")
        if key == "region" and value:
            return value
    return None


def resolve_stores(sql: Sql, region_names: Sequence[str]) -> StoreMap:
    """Map each configured region to its one store, or fail loudly.

    Requires one store per node with ``store_id == node_id``, which is how the
    generated cluster runs. ``SHOW RANGES`` reports the leaseholder by node and
    replicas by store, so the two ids must coincide for one map to serve both;
    if they ever diverge this raises rather than guess.
    """
    rows = sql.query(
        "SELECT s.store_id, s.node_id, n.locality "
        "FROM crdb_internal.kv_store_status AS s "
        "JOIN crdb_internal.kv_node_status AS n ON s.node_id = n.node_id")
    by_region: dict[str, list[int]] = {}
    for store_id, node_id, locality in rows:
        if int(store_id) != int(node_id):
            raise PlacementError(
                f"store {store_id} is on node {node_id}; the harness assumes one store "
                "per node with matching ids")
        region = parse_region(locality)
        if region is None:
            raise PlacementError(f"node {node_id} has no region in locality {locality!r}")
        by_region.setdefault(region, []).append(int(store_id))

    names = tuple(region_names)
    extra = sorted(set(by_region) - set(names))
    missing = [r for r in names if r not in by_region]
    doubled = {r: s for r, s in by_region.items() if len(s) > 1}
    if missing or extra or doubled:
        raise PlacementError(
            "cluster regions do not match the simulator's (ADR-0009 parity): "
            f"missing {missing}, unexpected {extra}, more than one store {doubled}")
    return StoreMap(names, tuple(by_region[r][0] for r in names))


# ----------------------------------------------------------------- ranges

@dataclass(frozen=True)
class RangeInfo:
    range_id: int
    start_cell: int
    lease_store: int
    voter_stores: tuple[int, ...]


_INDEX_START = re.compile(r"(?:…|\.\.\.)?(?:/Table/\d+)?/1")
_INDEX_KEY = re.compile(r"(?:…|\.\.\.)?(?:/Table/\d+)?(?:/1)?/(-?\d+)")


def parse_start_key(text: Any, layout: TableLayout) -> int:
    """A range's pretty-printed start key -> the cell it starts at.

    Accepts the forms ``SHOW RANGES FROM TABLE`` uses: ``…/1/2048`` (a key in
    the primary index), ``/2048`` (older releases), and, for the first range,
    which may begin at or before the table, ``…/<TableMin>``, ``<before:...>``,
    ``…/1`` or an empty key. A split that is not on a cell boundary raises: it
    means something other than the harness split the table.
    """
    s = str(text or "").strip()
    if not s or s.startswith("<before") or "TableMin" in s or _INDEX_START.fullmatch(s):
        return 0
    m = _INDEX_KEY.fullmatch(s)
    if not m:
        raise PlacementError(f"unrecognised range start key {s!r}")
    key = int(m.group(1))
    cell, rem = divmod(key, layout.rows_per_cell)
    if key < 0 or rem or cell >= layout.n_cells:
        raise PlacementError(
            f"range starts at key {key}, which is not a cell boundary of this layout "
            f"({layout.rows_per_cell} rows per cell, {layout.n_cells} cells)")
    return cell


def parse_store_list(value: Any) -> tuple[int, ...]:
    """``[1, 2, 3]`` or ``'{1,2,3}'`` -> ``(1, 2, 3)``."""
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(int(v) for v in value)
    return tuple(int(v) for v in str(value).strip("{}[] ").split(",") if v.strip())


def read_ranges(sql: Sql, layout: TableLayout) -> list[RangeInfo]:
    """Every range of the harness table, in key order. One query."""
    rows = sql.query(
        f"SELECT start_key, range_id, lease_holder, voting_replicas "
        f"FROM [SHOW RANGES FROM TABLE {layout.table} WITH DETAILS]")
    if not rows:
        raise PlacementError(f"table {layout.table} has no ranges; was it created?")
    ranges = []
    for start_key, range_id, lease_holder, voters in rows:
        if lease_holder is None:
            raise PlacementError(f"range {range_id} has no leaseholder yet; retry")
        ranges.append(RangeInfo(int(range_id), parse_start_key(start_key, layout),
                                int(lease_holder), parse_store_list(voters)))
    ranges.sort(key=lambda r: r.start_cell)
    starts = [r.start_cell for r in ranges]
    if starts[0] != 0 or len(set(starts)) != len(starts):
        raise PlacementError(f"ranges do not tile the table from cell 0: start cells {starts}")
    return ranges


def observed_catalog(ranges: Sequence[RangeInfo], stores: StoreMap,
                     cfg: FragAllocConfig) -> FragmentCatalog:
    """The cluster's placement as a ``FragmentCatalog`` of the simulator's shape."""
    n_regions = len(stores.region_names)
    boundaries = [r.start_cell for r in ranges] + [cfg.workload.n_cells]
    primary = np.array([stores.region_of(r.lease_store) for r in ranges], dtype=np.int64)
    replicas = np.zeros((len(ranges), n_regions), dtype=bool)
    for i, r in enumerate(ranges):
        for s in r.voter_stores:
            replicas[i, stores.region_of(s)] = True
    try:
        return FragmentCatalog(cfg.catalog, cfg.workload.n_cells, n_regions,
                               boundaries, primary, replicas)
    except AssertionError as exc:
        counts = sorted(set(int(c) for c in replicas.sum(axis=1)))
        raise PlacementError(
            f"cluster placement is not a valid catalogue ({exc}); voters per range "
            f"{counts}, config allows {cfg.catalog.min_replicas} to "
            f"{cfg.catalog.max_replicas}") from exc


def read_back(sql: Sql, stores: StoreMap, layout: TableLayout,
              cfg: FragAllocConfig) -> FragmentCatalog:
    """Resolve the harness table's current placement. Step 4 of the protocol."""
    return observed_catalog(read_ranges(sql, layout), stores, cfg)


# ----------------------------------------------------------- reconciling

@dataclass(frozen=True)
class Divergence:
    kind: str           # "boundaries", "lease" or "replicas"
    fragment: int       # -1 for "boundaries"
    expected: Any
    observed: Any

    def __str__(self) -> str:
        where = "table" if self.fragment < 0 else f"fragment {self.fragment}"
        return f"{self.kind} differ at {where}: expected {self.expected}, observed {self.observed}"


def compare(intent: FragmentCatalog, observed: FragmentCatalog) -> list[Divergence]:
    """Every way the cluster differs from intent. Empty means they agree.

    A boundary mismatch is reported alone: once fragments differ, comparing
    their placements fragment by fragment would only add noise.
    """
    if not np.array_equal(intent.boundaries, observed.boundaries):
        return [Divergence("boundaries", -1, intent.boundaries.tolist(),
                           observed.boundaries.tolist())]
    out = []
    for f in range(intent.n_fragments):
        if intent.primary[f] != observed.primary[f]:
            out.append(Divergence("lease", f, int(intent.primary[f]), int(observed.primary[f])))
        if not np.array_equal(intent.replicas[f], observed.replicas[f]):
            out.append(Divergence("replicas", f,
                                  np.flatnonzero(intent.replicas[f]).tolist(),
                                  np.flatnonzero(observed.replicas[f]).tolist()))
    return out


# ------------------------------------------------------------- relocating

def is_connection_error(exc: BaseException) -> bool:
    """True when the cluster is unreachable, as opposed to refusing a statement.

    psycopg raises ``OperationalError`` with no SQLSTATE when the connection is
    lost; the server reports connection failures in SQLSTATE class 08.
    """
    if isinstance(exc, (ConnectionError, OSError)):
        return True
    state = getattr(exc, "sqlstate", None)
    if state:
        return str(state).startswith("08")
    return type(exc).__name__ == "OperationalError"


def relocate(sql: Sql, stmt: str) -> tuple[bool, str]:
    """Run one ``ALTER RANGE ... RELOCATE`` and read its RESULT COLUMN.

    The statement reports ``ok`` or the error text as a column of its own
    result set and succeeds either way, which made the first pilot report zero
    failures whilst relocations failed. Only the column is trusted.

    A statement the database refuses returns ``(False, reason)``. A lost
    connection or dead node raises instead: docs/harness-architecture.md
    section 6 requires the run to abort, never to record a "refused" move from
    a cluster that is not there.
    """
    if not stmt.lstrip().upper().startswith("ALTER RANGE"):
        raise ValueError("relocate() runs ALTER RANGE statements only")
    try:
        rows = sql.query(stmt)
    except Exception as exc:  # noqa: BLE001 - classified below
        if is_connection_error(exc):
            raise
        text = str(exc).strip()
        return False, text.splitlines()[-1][:200] if text else repr(exc)
    for row in rows:
        result = str(row[-1]).strip()
        if result.lower() != "ok":
            return False, result[:200]
    return True, "ok"
