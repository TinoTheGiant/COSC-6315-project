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


@pytest.mark.parametrize("start, target", [(2, 3), (3, 2), (3, 3)])
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
