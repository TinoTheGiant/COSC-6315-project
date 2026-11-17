"""Replica count and rebalancer freeze (ADR-0015), against the fake cluster."""

from __future__ import annotations

import numpy as np
import pytest

from fake_cluster import FakeCluster
from fragalloc.catalog import FragmentCatalog
from fragalloc.config import FragAllocConfig
from fragalloc.harness.cluster import (
    REBALANCER_OFF, ClusterError, converge_replication, freeze_rebalancer, voter_counts,
)
from fragalloc.harness.placement import StoreMap, TableLayout

CFG = FragAllocConfig()
NAMES = CFG.topology.region_names
LAYOUT = TableLayout.from_config(CFG)
STORES = StoreMap(NAMES, (4, 1, 6, 2, 5, 3))


def cluster_at(rf: int) -> FakeCluster:
    """Six ranges stuck at ``rf`` voters, as pilot #2 left them at 2."""
    base = FragmentCatalog(CFG.catalog, CFG.workload.n_cells, len(NAMES))
    replicas = np.zeros_like(base.replicas)
    for f in range(base.n_fragments):
        for j in range(rf):
            replicas[f, (base.primary[f] + j) % len(NAMES)] = True
    cat = FragmentCatalog.__new__(FragmentCatalog)        # skip RF validation
    cat.cfg, cat.n_cells, cat.n_regions = CFG.catalog, CFG.workload.n_cells, len(NAMES)
    cat.boundaries, cat.primary, cat.replicas = base.boundaries, base.primary, replicas
    return FakeCluster.from_catalog(cat, STORES, LAYOUT)


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s


@pytest.mark.parametrize("start, target", [(2, 3), (5, 3), (3, 3)])
def test_every_range_reaches_the_chosen_count_before_the_freeze(start, target) -> None:
    c, clock = cluster_at(start), Clock()
    converge_replication(c, LAYOUT, target, sleep=clock.sleep, clock=clock)
    assert all(v == target and lr == 0 for _, v, lr in voter_counts(c, LAYOUT))
    assert c.settings["kv.replicate_queue.enabled"] == "false"
    zone = next(i for i, s in enumerate(c.statements) if "CONFIGURE ZONE" in s)
    froze = max(i for i, s in enumerate(c.statements)
                if s == "SET CLUSTER SETTING kv.replicate_queue.enabled = false")
    assert zone < froze, "the zone config must be set before the freeze"


def test_the_queue_is_frozen_even_when_convergence_times_out() -> None:
    c, clock = cluster_at(2), Clock()
    c.num_replicas = None                                  # never moves
    original = c.query

    def stuck(stmt, params=()):
        out = original(stmt, params)
        if "CONFIGURE ZONE" in stmt:
            c.num_replicas = None
        return out

    c.query = stuck
    with pytest.raises(ClusterError, match="not at 3 voters"):
        converge_replication(c, LAYOUT, 3, timeout_s=10, poll_s=2,
                             sleep=clock.sleep, clock=clock)
    assert all(c.settings[k] == v for k, v in REBALANCER_OFF.items())


def test_a_setting_that_does_not_take_is_an_error_not_a_warning() -> None:
    c = cluster_at(3)
    c.ignored_settings.add("kv.lease_queue.enabled")
    c.settings["kv.lease_queue.enabled"] = "true"
    with pytest.raises(ClusterError, match="kv.lease_queue.enabled reads back as 'true'"):
        freeze_rebalancer(c)


def test_every_rebalancer_setting_is_read_back_after_it_is_set() -> None:
    c = cluster_at(3)
    freeze_rebalancer(c)
    for name in REBALANCER_OFF:
        s = c.statements.index(f"SET CLUSTER SETTING {name} = "
                               f"{REBALANCER_OFF[name] if REBALANCER_OFF[name] in ('true', 'false') else repr(REBALANCER_OFF[name])}")
        assert c.statements[s + 1] == f"SHOW CLUSTER SETTING {name}"


def test_a_range_still_adding_a_learner_is_not_converged() -> None:
    """A learner is a replica mid-copy: the count looks right before it is."""
    c, clock = cluster_at(3), Clock()
    c.learner_polls[c.ranges[2]["id"]] = 3
    converge_replication(c, LAYOUT, 3, poll_s=1, sleep=clock.sleep, clock=clock)
    assert clock.t >= 3, "must keep polling until the learner is gone"


def test_an_absurd_replica_count_is_refused() -> None:
    with pytest.raises(ValueError):
        converge_replication(cluster_at(3), LAYOUT, 0)


def test_two_replicas_is_refused_before_touching_the_cluster() -> None:
    """CockroachDB rejects num_replicas = 2 (Cluster pilot #5)."""
    c = cluster_at(3)
    before = list(c.log) if hasattr(c, "log") else None
    with pytest.raises(ValueError, match="refuses 2"):
        converge_replication(c, LAYOUT, 2, sleep=lambda _: None)
    if before is not None:
        assert list(c.log) == before


def test_split_queue_runs_during_convergence_and_is_frozen_after() -> None:
    c, clock = cluster_at(2), Clock()
    seen = []
    real = c.query

    def spy(stmt, params=()):
        if "learner_replicas" in stmt:
            seen.append(c.settings.get("kv.split_queue.enabled"))
        return real(stmt, params)
    c.query = spy
    converge_replication(c, LAYOUT, 3, sleep=clock.sleep, clock=clock)
    assert seen and set(seen) == {"true"}
    assert c.settings["kv.split_queue.enabled"] == "false"
    assert len(seen) >= 2                 # two clean polls before returning


def test_release_hands_leases_and_replicas_back_but_keeps_boundaries() -> None:
    from fragalloc.harness.cluster import REBALANCER_CRDB, release_rebalancer
    c, clock = cluster_at(3), Clock()
    converge_replication(c, LAYOUT, 3, sleep=clock.sleep, clock=clock)
    release_rebalancer(c)
    assert c.settings["kv.allocator.load_based_rebalancing"] == "leases and replicas"
    assert c.settings["kv.replicate_queue.enabled"] == "true"
    assert c.settings["kv.lease_queue.enabled"] == "true"
    # Splits and merges would change the shards every policy is compared on.
    assert c.settings["kv.split_queue.enabled"] == "false"
    assert c.settings["kv.range_merge.queue.enabled"] == "false"
    assert set(REBALANCER_CRDB) == set(REBALANCER_OFF)
    freeze_rebalancer(c)
    assert all(c.settings[k] == v for k, v in REBALANCER_OFF.items())


def test_bytes_added_counts_new_replicas_only() -> None:
    from fragalloc.harness.env import bytes_added
    before = FragmentCatalog(CFG.catalog, CFG.workload.n_cells, len(NAMES))
    after = before.copy()
    assert bytes_added(before, after) == 0.0
    after.move_lease(0, int(np.flatnonzero(after.replicas[0] & (np.arange(len(NAMES)) != after.primary[0]))[0]))
    assert bytes_added(before, after) == 0.0, "a lease move copies nothing"
    free = int(np.flatnonzero(~after.replicas[1])[0])
    after.move_replica_to(1, free, CFG_RTT())
    assert bytes_added(before, after) == pytest.approx(float(after.sizes_bytes[1]))
    split = before.copy()
    split.split(0)
    with pytest.raises(ValueError):
        bytes_added(before, split)


def CFG_RTT() -> np.ndarray:
    from fragalloc.topology import build_topology
    return build_topology(CFG.topology, CFG.catalog.dataset_bytes).rtt
