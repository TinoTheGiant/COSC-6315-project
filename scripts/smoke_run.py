#!/usr/bin/env python3
"""Drive the simulator for one episode under each reference policy.

This is the five-second check that the whole stack is wired together. It does
not train anything.

    python scripts/smoke_run.py
    python scripts/smoke_run.py --volatility 3.0 --episodes 3
"""

from __future__ import annotations

import argparse
import statistics
from dataclasses import replace

from shardmind.actions import ActionSpace
from shardmind.config import ShardMindConfig
from shardmind.policies import FollowTrafficPolicy, StaticHashPolicy, RandomPolicy, rollout
from shardmind.simulator import ClusterSimulator


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--volatility", type=float, default=1.0)
    parser.add_argument("--windows", type=int, default=200)
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    base = ShardMindConfig()
    cfg = base.evolve(
        workload=replace(base.workload, volatility=args.volatility),
        episode=replace(base.episode, windows_per_episode=args.windows),
        seed=args.seed,
    )

    sim = ClusterSimulator(cfg)
    space = ActionSpace(cfg.catalog.max_fragments, cfg.n_regions)

    policies = {
        "static hash": StaticHashPolicy(space),
        "random": RandomPolicy(space, seed=args.seed),
        "follow traffic": FollowTrafficPolicy(space),
    }

    print(f"volatility={args.volatility}  windows={args.windows}  episodes={args.episodes}")
    print(f"{space.n} actions over {cfg.n_regions} regions, fragment cap {cfg.catalog.max_fragments}")
    header = f"{'policy':<22s}{'mean ms':>10s}{'p95 ms':>10s}{'GB moved':>11s}{'xregion':>9s}{'frags':>7s}"
    print(header)
    print("-" * len(header))

    for name, policy in policies.items():
        means, tails, moved, xregion, frags = [], [], [], [], []
        for e in range(args.episodes):
            records = rollout(sim, policy, seed=args.seed + e)
            means.append(statistics.fmean(r["mean_latency_ms"] for r in records))
            tails.append(statistics.fmean(r["tail_latency_ms"] for r in records))
            moved.append(sum(r["bytes_moved"] for r in records) / 1e9)
            xregion.append(statistics.fmean(r["cross_region_txn_fraction"] for r in records))
            frags.append(records[-1]["n_fragments"])
        print(
            f"{name:<22s}{statistics.fmean(means):>10.2f}{statistics.fmean(tails):>10.2f}"
            f"{statistics.fmean(moved):>11.1f}{statistics.fmean(xregion):>9.1%}"
            f"{statistics.fmean(frags):>7.1f}"
        )


if __name__ == "__main__":
    main()
