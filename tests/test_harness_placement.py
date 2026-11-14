"""Placement read-back (harness piece 1), without a cluster.

A fake :class:`Sql` returns rows shaped like CockroachDB's, so every parsing and
reconciliation rule is checked here. ``scripts/placement_check.py`` checks the
same code against a real cluster in the Cluster pilot workflow.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from fragalloc.catalog import FragmentCatalog
from fragalloc.config import FragAllocConfig
from fragalloc.harness.placement import (
    Divergence, PlacementError, RangeInfo, StoreMap, TableLayout, compare,
    create_table, observed_catalog, parse_region, parse_start_key,
    parse_store_list, read_back, read_ranges, relocate, resolve_stores,
)

CFG = FragAllocConfig()
NAMES = CFG.topology.region_names
LAYOUT = TableLayout.from_config(CFG)            # 256 cells x 16 rows
# Join order is nondeterministic, so stores are deliberately not 1..6 in order.
STORE_IDS = (4, 1, 6, 2, 5, 3)
STORES = StoreMap(NAMES, STORE_IDS)


class FakeSql:
    """Answers by the first registered substring found in the statement."""

    def __init__(self, answers: dict[str, object] | None = None) -> None:
        self.answers = dict(answers or {})
        self.statements: list[str] = []

    def query(self, stmt, params=()):
        self.statements.append(stmt)
        for needle, rows in self.answers.items():
            if needle in stmt:
                if isinstance(rows, Exception):
                    raise rows
                return list(rows)
        return []


def node_rows(store_ids=STORE_IDS, names=NAMES):
    return [(s, s, f"region={n},zone=a") for s, n in zip(store_ids, names)]


def range_rows(cat: FragmentCatalog, *, key_style: str = "relative",
               shuffle: bool = True, as_text: bool = False):
    """SHOW RANGES-shaped rows for a catalogue, as the cluster would report it."""
    rows = []
    for f in range(cat.n_fragments):
        start = int(cat.boundaries[f])
        if f == 0:
            key = "…/<TableMin>"
        elif key_style == "relative":
            key = f"…/1/{LAYOUT.cell_key(start)}"
        else:
            key = f"/{LAYOUT.cell_key(start)}"
        voters = [STORE_IDS[r] for r in np.flatnonzero(cat.replicas[f])]
        rows.append((key, 100 + f, STORE_IDS[int(cat.primary[f])],
                     "{" + ",".join(map(str, voters)) + "}" if as_text else voters))
    if shuffle:
        rows = rows[1::2] + rows[0::2]
    return rows


def rf3_catalog() -> FragmentCatalog:
    """The default six fragments, at the cluster's replication factor of 3."""
    base = FragmentCatalog(CFG.catalog, CFG.workload.n_cells, len(NAMES))
    replicas = np.zeros_like(base.replicas)
    for f in range(base.n_fragments):
        for j in range(3):
            replicas[f, (base.primary[f] + j) % len(NAMES)] = True
    return FragmentCatalog(CFG.catalog, CFG.workload.n_cells, len(NAMES),
                           base.boundaries, base.primary, replicas)


# ----------------------------------------------------------- boundaries

def test_the_harness_never_imports_the_cost_model_or_simulator() -> None:
    """docs/harness-architecture.md section 3: measured, never modelled."""
    src = Path(__file__).resolve().parents[1] / "src"
    code = ("import sys, fragalloc.harness.placement; "
            "print(sorted(m for m in sys.modules "
            "if m in ('fragalloc.cost', 'fragalloc.simulator')))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={"PYTHONPATH": str(src)}, check=True).stdout.strip()
    assert out == "[]", out


@pytest.mark.parametrize("text, cell", [
    ("…/<TableMin>", 0), ("<before:/Table/104/1/0>", 0), ("", 0), (None, 0),
    ("…/1", 0), ("/Table/104/1", 0),
    ("…/1/2048", 128), ("/2048", 128), ("/Table/104/1/32", 2), ("…/1/16", 1),
])
def test_start_keys_in_every_reported_form_map_to_cells(text, cell) -> None:
    assert parse_start_key(text, LAYOUT) == cell


@pytest.mark.parametrize("text", ["…/1/17", "…/1/4096", "/-16", "…/2/abc", "garbage"])
def test_a_split_off_a_cell_boundary_or_an_odd_key_raises(text) -> None:
    with pytest.raises(PlacementError):
        parse_start_key(text, LAYOUT)


def test_store_lists_parse_from_arrays_and_text() -> None:
    assert parse_store_list([3, 1, 2]) == (3, 1, 2)
    assert parse_store_list("{3,1,2}") == (3, 1, 2)
    assert parse_store_list(None) == ()
    assert parse_region("zone=b,region=eu-west-1") == "eu-west-1"
    assert parse_region("zone=b") is None


# --------------------------------------------------------------- stores

def test_stores_resolve_by_locality_not_join_order() -> None:
    stores = resolve_stores(FakeSql({"kv_store_status": node_rows()}), NAMES)
    assert stores.store_of_region == STORE_IDS
    assert stores.region_of(6) == 2


@pytest.mark.parametrize("rows, message", [
    (node_rows()[:-1], "missing"),
    (node_rows() + [(7, 7, "region=sa-east-1")], "unexpected"),
    (node_rows() + [(7, 7, f"region={NAMES[0]}")], "more than one"),
    ([(4, 9, f"region={NAMES[0]}")] + node_rows()[1:], "one store per node"),
    ([(4, 4, "zone=a")] + node_rows()[1:], "no region"),
])
def test_a_cluster_that_breaks_region_parity_is_refused(rows, message) -> None:
    with pytest.raises(PlacementError, match=message):
        resolve_stores(FakeSql({"kv_store_status": rows}), NAMES)


def test_an_unknown_store_is_an_error_not_a_guess() -> None:
    with pytest.raises(PlacementError, match="no configured region"):
        STORES.region_of(99)


# --------------------------------------------------------------- ranges

@pytest.mark.parametrize("key_style, as_text", [("relative", False), ("old", True)])
def test_read_back_reproduces_the_placement_exactly(key_style, as_text) -> None:
    intent = rf3_catalog()
    intent.move_lease(1, int(np.flatnonzero(intent.replicas[1])[-1]))
    sql = FakeSql({"SHOW RANGES": range_rows(intent, key_style=key_style, as_text=as_text)})
    observed = read_back(sql, STORES, LAYOUT, CFG)
    assert compare(intent, observed) == []
    assert observed.boundaries.tolist() == intent.boundaries.tolist()


def test_ranges_come_back_in_key_order_whatever_order_the_cluster_lists_them() -> None:
    sql = FakeSql({"SHOW RANGES": range_rows(rf3_catalog(), shuffle=True)})
    starts = [r.start_cell for r in read_ranges(sql, LAYOUT)]
    assert starts == sorted(starts) and starts[0] == 0


@pytest.mark.parametrize("rows, message", [
    ([], "no ranges"),
    ([("…/<TableMin>", 1, None, [1, 2, 3])], "no leaseholder"),
    ([("…/1/160", 1, 1, [1, 2, 3])], "tile the table"),
    ([("…/<TableMin>", 1, 1, [1, 2, 3]), ("<before:/Table/9>", 2, 1, [1, 2, 3])],
     "tile the table"),
])
def test_ranges_that_do_not_tile_the_table_are_refused(rows, message) -> None:
    with pytest.raises(PlacementError, match=message):
        read_ranges(FakeSql({"SHOW RANGES": rows}), LAYOUT)


def test_a_lease_outside_the_voters_or_too_many_voters_is_refused() -> None:
    lease_off = [RangeInfo(1, 0, STORE_IDS[5], (STORE_IDS[0], STORE_IDS[1], STORE_IDS[2]))]
    with pytest.raises(PlacementError, match="primary does not hold a replica"):
        observed_catalog(lease_off, STORES, CFG)
    five = [RangeInfo(1, 0, STORE_IDS[0], STORE_IDS[:5])]
    with pytest.raises(PlacementError, match="voters per range"):
        observed_catalog(five, STORES, CFG)


# ------------------------------------------------------------ comparing

def test_compare_names_each_lease_and_replica_difference() -> None:
    intent = rf3_catalog()
    observed = intent.copy()
    lease_target = int(np.flatnonzero(observed.replicas[0])[-1])
    observed.move_lease(0, lease_target)
    observed.move_replica_to(2, int(np.flatnonzero(~observed.replicas[2])[0]),
                             np.ones((len(NAMES), len(NAMES))))
    found = compare(intent, observed)
    assert [(d.kind, d.fragment) for d in found] == [("lease", 0), ("replicas", 2)]
    assert found[0].observed == lease_target
    assert "fragment 0" in str(found[0])


def test_a_boundary_difference_is_reported_alone() -> None:
    intent = rf3_catalog()
    observed = intent.copy()
    observed.split(0)
    observed.move_lease(3, int(np.flatnonzero(observed.replicas[3])[-1]))
    found = compare(intent, observed)
    assert len(found) == 1 and found[0].kind == "boundaries"
    assert isinstance(found[0], Divergence) and found[0].fragment == -1


# ------------------------------------------------------- table and moves

def test_create_table_splits_exactly_at_cell_keys() -> None:
    sql = FakeSql()
    create_table(sql, LAYOUT, [0, 43, 85, 256])
    split = next(s for s in sql.statements if "SPLIT AT" in s)
    assert f"({43 * 16}), ({85 * 16})" in split
    assert any("generate_series(0, 4095)" in s for s in sql.statements)


@pytest.mark.parametrize("bad", [[1, 256], [0, 255], [0, 40, 40, 256]])
def test_create_table_refuses_boundaries_that_do_not_tile(bad) -> None:
    with pytest.raises(ValueError):
        create_table(FakeSql(), LAYOUT, bad)


def test_an_unsafe_table_name_is_refused() -> None:
    with pytest.raises(ValueError):
        TableLayout(table="t; DROP TABLE x")


def test_relocate_trusts_the_result_column_not_the_exit_status() -> None:
    ok = FakeSql({"RELOCATE": [(101, "…/1/16", "ok")]})
    assert relocate(ok, "ALTER RANGE 101 RELOCATE LEASE TO 4") == (True, "ok")
    refused = FakeSql({"RELOCATE": [(101, "…/1/16", "unable to find store 9")]})
    assert relocate(refused, "ALTER RANGE 101 RELOCATE LEASE TO 9") == (
        False, "unable to find store 9")
    raised = FakeSql({"RELOCATE": RuntimeError("range already being rebalanced")})
    assert relocate(raised, "ALTER RANGE 1 RELOCATE VOTERS FROM 1 TO 2")[0] is False
    with pytest.raises(ValueError):
        relocate(ok, "DROP TABLE fragalloc")


class _Sqlstate(Exception):
    def __init__(self, msg: str, sqlstate: str | None) -> None:
        super().__init__(msg)
        self.sqlstate = sqlstate


class OperationalError(Exception):
    """Stands in for psycopg's, which carries no SQLSTATE on a lost connection."""


@pytest.mark.parametrize("exc", [
    ConnectionRefusedError("connection refused"),
    _Sqlstate("server closed the connection", "08006"),
    OperationalError("consuming input failed: server closed the connection"),
])
def test_a_lost_cluster_aborts_instead_of_counting_as_a_refusal(exc) -> None:
    """docs/harness-architecture.md section 6: node death aborts the run."""
    with pytest.raises(type(exc)):
        relocate(FakeSql({"RELOCATE": exc}), "ALTER RANGE 1 RELOCATE LEASE TO 2")


def test_a_statement_error_with_a_server_sqlstate_is_still_a_refusal() -> None:
    sql = FakeSql({"RELOCATE": _Sqlstate("range already being rebalanced", "XX000")})
    assert relocate(sql, "ALTER RANGE 1 RELOCATE LEASE TO 2") == (
        False, "range already being rebalanced")
