"""The executor (harness piece 2), against a fake cluster with CockroachDB's rules.

The fake enforces the database's constraints independently of the catalogue,
so an action that passes through it unchanged has been translated correctly,
not merely consistently.
"""

from __future__ import annotations

import numpy as np
import pytest

from fake_cluster import FakeCluster
from fragalloc.actions import ActionKind, ActionSpace
from fragalloc.catalog import FragmentCatalog
from fragalloc.config import FragAllocConfig
from fragalloc.harness.executor import APPLIED, NO_OP, REJECTED, Executor
from fragalloc.harness.placement import PlacementError, StoreMap, TableLayout
from fragalloc.topology import build_topology

CFG = FragAllocConfig()
NAMES = CFG.topology.region_names
LAYOUT = TableLayout.from_config(CFG)
STORES = StoreMap(NAMES, (4, 1, 6, 2, 5, 3))
SPACE = ActionSpace(CFG.catalog.max_fragments, len(NAMES))
RTT = build_topology(CFG.topology, CFG.catalog.dataset_bytes).rtt


def rf3_catalog() -> FragmentCatalog:
    base = FragmentCatalog(CFG.catalog, CFG.workload.n_cells, len(NAMES))
    replicas = np.zeros_like(base.replicas)
    for f in range(base.n_fragments):
        for j in range(3):
            replicas[f, (base.primary[f] + j) % len(NAMES)] = True
    return FragmentCatalog(CFG.catalog, CFG.workload.n_cells, len(NAMES),
                           base.boundaries, base.primary, replicas)


def setup(cat: FragmentCatalog | None = None):
    cat = cat or rf3_catalog()
    cluster = FakeCluster.from_catalog(cat, STORES, LAYOUT)
    slept: list[float] = []
    ex = Executor(cluster, STORES, LAYOUT, CFG, settle_tries=5, settle_wait_s=0.5,
                  sleep=slept.append)
    return cat, cluster, ex, slept


def test_every_applicable_action_lands_on_the_cluster_exactly_as_the_simulator_says() -> None:
    """The core parity property, over every legal action from one state."""
    start = rf3_catalog()
    legal = np.flatnonzero(SPACE.applicable_mask(start))
    # 6 fragments at RF 3 in 6 regions: 2 lease moves and 3 replica moves each,
    # 6 splits, and NOOP.
    assert len(legal) == 6 * 2 + 6 * 3 + 6 + 1
    kinds = set()
    for index in legal:
        if index == SPACE.noop_index:
            continue
        cat, cluster, ex, _ = setup(start.copy())
        expected = cat.copy()
        sim_result = SPACE.apply(expected, int(index), RTT)
        out = ex.step(cat, int(index))
        kinds.add(out.action.kind)
        assert out.outcome == APPLIED, (SPACE.describe(index), out.detail)
        assert not out.diverged, (SPACE.describe(index), [str(d) for d in out.divergences])
        assert out.catalog.boundaries.tolist() == expected.boundaries.tolist()
        assert np.array_equal(out.catalog.primary, expected.primary)
        assert np.array_equal(out.catalog.replicas, expected.replicas)
        assert out.bytes_moved == pytest.approx(sim_result.bytes_moved)
    assert kinds == {ActionKind.MOVE_LEASE, ActionKind.MOVE_REPLICA_TO, ActionKind.SPLIT}


def test_a_replica_move_evicts_the_farthest_non_primary_from_the_destination() -> None:
    cat, cluster, ex, _ = setup()
    dest = int(np.flatnonzero(~cat.replicas[0])[0])
    held = [r for r in np.flatnonzero(cat.replicas[0]) if r != cat.primary[0]]
    farthest = max(held, key=lambda r: RTT[r, dest])
    _, _, stmts = ex.plan(cat, SPACE.encode(ActionKind.MOVE_REPLICA_TO, 0, dest),
                          [101, 102, 103, 104, 105, 106])
    assert stmts == [f"ALTER RANGE 101 RELOCATE VOTERS FROM "
                     f"{STORES.store_of_region[farthest]} TO {STORES.store_of_region[dest]}"]


def test_a_split_cuts_at_the_first_key_of_the_midpoint_cell() -> None:
    cat, cluster, ex, _ = setup()
    lo, hi = int(cat.boundaries[2]), int(cat.boundaries[3])
    out = ex.step(cat, SPACE.encode(ActionKind.SPLIT, 2))
    assert out.statements == (f"ALTER TABLE fragalloc SPLIT AT VALUES "
                              f"({LAYOUT.cell_key(lo + (hi - lo) // 2)})",)
    assert out.catalog.n_fragments == cat.n_fragments + 1


@pytest.mark.parametrize("make_index", [
    lambda cat: SPACE.noop_index,
    lambda cat: SPACE.encode(ActionKind.MOVE_LEASE, 0, int(cat.primary[0])),        # already
    lambda cat: SPACE.encode(ActionKind.MOVE_LEASE, 0,
                             int(np.flatnonzero(~cat.replicas[0])[0])),              # no voter
    lambda cat: SPACE.encode(ActionKind.MOVE_REPLICA_TO, 0, int(cat.primary[0])),   # present
    lambda cat: SPACE.encode(ActionKind.SPLIT, 15),                                  # no such f
])
def test_an_inapplicable_action_sends_nothing(make_index) -> None:
    cat, cluster, ex, _ = setup()
    before = len(cluster.statements)
    out = ex.step(cat, make_index(cat))
    assert out.outcome == NO_OP and out.statements == ()
    assert not any("ALTER" in s for s in cluster.statements[before:])
    assert out.bytes_moved == 0.0 and not out.diverged


def test_a_refusal_is_rejected_unretried_and_leaves_the_placement_unchanged() -> None:
    cat, cluster, ex, _ = setup()
    cluster.refuse_next = "range already being rebalanced"
    index = SPACE.encode(ActionKind.MOVE_LEASE, 0, int(np.flatnonzero(cat.replicas[0])[-1]))
    out = ex.step(cat, index)
    assert out.outcome == REJECTED and out.detail == "range already being rebalanced"
    assert sum("RELOCATE" in s for s in cluster.statements) == 1, "never retried"
    assert out.bytes_moved == 0.0
    assert not out.diverged and np.array_equal(out.catalog.primary, cat.primary)


def test_a_database_error_on_a_split_is_a_rejection() -> None:
    cat, cluster, ex, _ = setup()
    cluster.raise_next = None
    original = cluster.query

    def failing(stmt, params=()):
        if "SPLIT AT" in stmt:
            raise RuntimeError("split refused: descriptor changed")
        return original(stmt, params)

    cluster.query = failing
    out = ex.step(cat, SPACE.encode(ActionKind.SPLIT, 1))
    assert out.outcome == REJECTED and "descriptor changed" in out.detail
    assert out.catalog.n_fragments == cat.n_fragments


def test_a_lost_cluster_aborts_the_step() -> None:
    cat, cluster, ex, _ = setup()
    index = SPACE.encode(ActionKind.MOVE_LEASE, 0, int(np.flatnonzero(cat.replicas[0])[-1]))
    original = cluster.query

    def drop_on_relocate(stmt, params=()):
        if "RELOCATE" in stmt:
            raise ConnectionRefusedError("node gone")
        return original(stmt, params)

    cluster.query = drop_on_relocate
    with pytest.raises(ConnectionRefusedError):
        ex.step(cat, index)


def test_a_move_that_lands_late_is_waited_for_not_reported_as_divergence() -> None:
    cat, cluster, ex, slept = setup()
    cluster.stale_reads = 2
    index = SPACE.encode(ActionKind.MOVE_LEASE, 1, int(np.flatnonzero(cat.replicas[1])[-1]))
    out = ex.step(cat, index)
    assert out.outcome == APPLIED and not out.diverged
    assert slept == [0.5, 0.5]


def test_a_move_that_never_lands_is_reported_and_the_cluster_wins() -> None:
    cat, cluster, ex, slept = setup()
    cluster.stale_reads = 99
    index = SPACE.encode(ActionKind.MOVE_LEASE, 1, int(np.flatnonzero(cat.replicas[1])[-1]))
    out = ex.step(cat, index)
    assert out.outcome == APPLIED and out.diverged
    assert out.divergences[0].kind == "lease"
    assert np.array_equal(out.catalog.primary, cat.primary), "returns what the cluster holds"
    assert len(slept) == 4


def test_drift_behind_the_agents_back_is_surfaced_on_a_noop() -> None:
    """The allocator should be off; the design says assume it is not."""
    cat, cluster, ex, _ = setup()
    r0 = cluster.ranges[0]
    r0["lease"] = next(v for v in r0["voters"] if v != r0["lease"])
    out = ex.step(cat, SPACE.noop_index)
    assert out.outcome == NO_OP and out.diverged
    assert out.divergences[0].kind == "lease" and out.divergences[0].fragment == 0


def test_acting_on_a_stale_catalogue_is_refused_before_anything_is_sent() -> None:
    cat, cluster, ex, _ = setup()
    stale = cat.copy()
    stale.split(0)
    before = len(cluster.statements)
    with pytest.raises(PlacementError, match="resync"):
        ex.step(stale, SPACE.encode(ActionKind.MOVE_LEASE, 0, 1))
    assert not any("ALTER" in s for s in cluster.statements[before:])


def test_a_region_count_mismatch_is_refused_at_construction() -> None:
    with pytest.raises(ValueError):
        Executor(FakeCluster(STORES, LAYOUT), StoreMap(NAMES[:4], (1, 2, 3, 4)), LAYOUT, CFG)


@pytest.mark.parametrize("seed", range(5))
def test_simulator_and_cluster_stay_in_lockstep_over_a_random_walk(seed) -> None:
    """From any reachable state, not just the first: 40 random legal actions."""
    rng = np.random.default_rng(seed)
    sim, cluster, ex, _ = setup()
    cat = sim.copy()
    for _ in range(40):
        index = int(rng.choice(np.flatnonzero(SPACE.applicable_mask(sim))))
        SPACE.apply(sim, index, RTT)
        out = ex.step(cat, index)
        assert not out.diverged, (SPACE.describe(index), [str(d) for d in out.divergences])
        assert out.catalog.boundaries.tolist() == sim.boundaries.tolist()
        assert np.array_equal(out.catalog.primary, sim.primary)
        assert np.array_equal(out.catalog.replicas, sim.replicas)
        cat = out.catalog
