"""The exact oracle is a true per-window minimum at fixed shard boundaries.

Three independent checks, each able to fail:

* the oracle's own total equals what :func:`fragalloc.cost.evaluate` charges
  the catalog it returns (so the lookup tables model the same cost);
* no sampled placement, scored by ``evaluate``, is cheaper (so it is a minimum);
* the greedy placement it replaced is never cheaper either.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from fragalloc.config import FragAllocConfig
from fragalloc.cost import evaluate
from fragalloc.oracle import exact_oracle, nearest_replicas, placed_catalog, placement_totals
from fragalloc.simulator import ClusterSimulator


def _sim(seed: int, volatility: float = 4.0) -> ClusterSimulator:
    cfg = FragAllocConfig()
    cfg = dataclasses.replace(
        cfg,
        cost=dataclasses.replace(cfg.cost, read_consistency="primary_only"),
        workload=dataclasses.replace(cfg.workload, volatility=volatility),
    )
    sim = ClusterSimulator(cfg)
    sim.reset(seed=seed)
    return sim


def _total(sim: ClusterSimulator, catalog) -> float:
    cost = evaluate(catalog, sim.last.window, sim.generator, sim.topology, sim.cfg.cost)
    return cost.mean_latency_ms * cost.total_requests


@pytest.mark.parametrize("seed", [0, 2000])
def test_oracle_total_matches_evaluate(seed):
    sim = _sim(seed)
    placed, total = exact_oracle(sim.catalog, sim.last.window, sim.generator, sim.topology, sim.cfg.cost)
    assert _total(sim, placed) == pytest.approx(total, rel=1e-9)


@pytest.mark.parametrize("seed", [1, 2001])
def test_no_sampled_placement_beats_the_oracle(seed):
    sim = _sim(seed)
    placed, total = exact_oracle(sim.catalog, sim.last.window, sim.generator, sim.topology, sim.cfg.cost)
    rng = np.random.default_rng(seed)
    n_regions = sim.topology.n_regions
    for _ in range(300):
        trial = sim.catalog.copy()
        trial.primary = rng.integers(0, n_regions, trial.n_fragments)
        trial.replicas = np.zeros_like(trial.replicas)
        for f, p in enumerate(trial.primary):
            trial.replicas[f, nearest_replicas(sim.topology, int(p), trial.replicas.shape[1] // 2)] = True
            trial.replicas[f, rng.choice(n_regions, 2, replace=False)] = True
            trial.replicas[f, p] = True
            while trial.replicas[f].sum() > 3:
                drop = rng.choice([r for r in np.flatnonzero(trial.replicas[f]) if r != p])
                trial.replicas[f, drop] = False
        assert _total(sim, trial) >= total - 1e-6


def test_greedy_placement_is_never_cheaper():
    sim = _sim(3)
    for _ in range(20):
        window = sim.last.window
        _, total = exact_oracle(sim.catalog, window, sim.generator, sim.topology, sim.cfg.cost)
        greedy = sim.catalog.copy()
        demand = greedy.aggregate_cells(window.reads + window.writes)
        for f, r in enumerate((demand @ sim.topology.rtt).argmin(axis=1)):
            greedy.set_primary(f, int(r))
        assert _total(sim, greedy) >= total - 1e-6
        sim.step(0)


def test_refuses_nearest_replica_reads():
    sim = _sim(0)
    cfg = dataclasses.replace(sim.cfg.cost, read_consistency="nearest_replica")
    with pytest.raises(NotImplementedError):
        exact_oracle(sim.catalog, sim.last.window, sim.generator, sim.topology, cfg)


@pytest.mark.parametrize("seed", [4, 2002])
def test_every_term_matches_evaluate_on_sampled_assignments(seed):
    """Checks the tables term by term, two-phase commit included.

    The optimum often co-locates every shard, which never exercises commit
    coordination; scoring arbitrary assignments does.
    """
    sim = _sim(seed)
    assignments, totals = placement_totals(
        sim.catalog, sim.last.window, sim.generator, sim.topology, sim.cfg.cost
    )
    rng = np.random.default_rng(seed)
    multi = 0
    for i in rng.choice(len(assignments), 60, replace=False):
        placed = placed_catalog(sim.catalog, sim.topology, assignments[i])
        multi += len(set(assignments[i])) > 1
        assert _total(sim, placed) == pytest.approx(totals[i], rel=1e-9)
    assert multi > 50
