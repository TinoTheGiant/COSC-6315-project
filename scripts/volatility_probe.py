#!/usr/bin/env python3
"""Measure how each reference policy responds to workload volatility.

Produces the table in ``docs/open-questions.md``. Run it after any change to
the workload model or the cost model, because the finding it records -- that
the static baseline is nearly volatility-invariant -- is a property of those two
and nothing else.

    python scripts/volatility_probe.py
    python scripts/volatility_probe.py --seeds 5 --windows 200
"""

from __future__ import annotations

import argparse
from dataclasses import replace

import numpy as np

from shardmind.config import ShardMindConfig
from shardmind.cost import evaluate
from shardmind.policies import GreedyPrimaryPolicy, NoOpPolicy, rollout
from shardmind.simulator import ClusterSimulator

VOLATILITIES = (0.0, 0.5, 1.0, 2.0, 4.0, 8.0)


def instantaneous_best(sim: ClusterSimulator, cfg: ShardMindConfig, seed: int) -> float:
    """Mean latency of re-optimizing every primary every window, for free.

    Not an oracle. It is the best *allocation-only* placement reachable in one
    window if migration were free and each fragment could be considered
    independently: for each fragment, the primary minimizing that fragment's own
    demand-weighted RTT, with the replica set left alone. It ignores migration
    cost, transaction co-location and fragmentation entirely, so a good agent can
    beat it on some windows and a thrashing one can beat it on none.

    Its purpose is to be a moving target: the gap between a tracking policy and
    this figure is the tracking error, and that is the quantity that should
    respond to volatility.
    """
    sim.reset(seed=seed)
    latencies = []
    while True:
        window = sim.last.window
        catalog = sim.catalog.copy()
        demand = catalog.aggregate_cells(window.reads + window.writes)
        target = (demand @ sim.topology.rtt).argmin(axis=1)
        for fragment in range(catalog.n_fragments):
            catalog.set_primary(fragment, int(target[fragment]))
        latencies.append(
            evaluate(catalog, window, sim.generator, sim.topology, cfg.cost).mean_latency_ms
        )
        if sim.last.done:
            break
        sim.step(sim.action_space.noop_index)
    return float(np.mean(latencies))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--windows", type=int, default=100)
    args = parser.parse_args()

    base = ShardMindConfig()
    header = (
        f"{'vol':>5}{'static':>10}{'greedy':>10}{'inst.best':>11}"
        f"{'track gap':>11}{'GB/episode':>12}"
    )
    print(header)
    print("-" * len(header))

    for volatility in VOLATILITIES:
        cfg = base.evolve(
            workload=replace(base.workload, volatility=volatility),
            episode=replace(base.episode, windows_per_episode=args.windows),
        )
        sim = ClusterSimulator(cfg)
        space = sim.action_space

        static, greedy, moved, best = [], [], [], []
        for seed in range(args.seeds):
            s = rollout(sim, NoOpPolicy(space), seed=seed)
            g = rollout(sim, GreedyPrimaryPolicy(space), seed=seed)
            static.append(np.mean([r["mean_latency_ms"] for r in s]))
            greedy.append(np.mean([r["mean_latency_ms"] for r in g]))
            moved.append(sum(r["bytes_moved"] for r in g) / 1e9)
            best.append(instantaneous_best(sim, cfg, seed))

        print(
            f"{volatility:>5.1f}{np.mean(static):>10.2f}{np.mean(greedy):>10.2f}"
            f"{np.mean(best):>11.2f}{np.mean(greedy) - np.mean(best):>11.2f}"
            f"{np.mean(moved):>12.1f}"
        )


if __name__ == "__main__":
    main()
