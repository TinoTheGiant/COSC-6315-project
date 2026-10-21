#!/usr/bin/env python3
"""Export one episode to JSON so it can be plotted or fed to a web page.

Runs the same seeded episode under each reference policy and writes everything
a visualization needs: where the traffic was each window, what latency each
policy produced, how much data it moved, and where each chunk was living.

    python scripts/export_episode.py
    python scripts/export_episode.py --volatility 4 --windows 300 --out results/volatile.json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import numpy as np

from fragalloc.config import FragAllocConfig
from fragalloc.topologies import region_meta
from fragalloc.cost import evaluate
from fragalloc.policies import FollowTrafficPolicy, StaticHashPolicy
from fragalloc.simulator import ClusterSimulator


def run(sim: ClusterSimulator, policy, seed: int) -> dict:
    """One episode, recording per-window latency, churn and chunk homes."""
    sim.reset(seed=seed)
    policy.reset()
    latency, tail, moved, homes = [], [], [], []

    def record() -> None:
        snap = sim.last.cost
        latency.append(round(snap.mean_latency_ms, 3))
        tail.append(round(snap.tail_latency_ms, 3))
        moved.append(round(sim.last.bytes_moved / 1e9, 4))
        homes.append([int(p) for p in sim.catalog.primary])

    record()
    while not sim.last.done:
        sim.step(policy.act(sim))
        record()
    return {"latency": latency, "tail": tail, "gbMoved": moved, "homes": homes}


def instantaneous_best(sim: ClusterSimulator, cfg: FragAllocConfig, seed: int) -> dict:
    """Re-home every chunk optimally every window, with migration free.

    A moving target, not an upper bound: it ignores migration cost, transaction
    co-location and fragmentation. See scripts/volatility_probe.py.
    """
    sim.reset(seed=seed)
    latency, homes, traffic = [], [], []
    while True:
        window = sim.last.window
        catalog = sim.catalog.copy()
        demand = catalog.aggregate_cells(window.reads + window.writes)
        target = (demand @ sim.topology.rtt).argmin(axis=1)
        for fragment in range(catalog.n_fragments):
            catalog.set_primary(fragment, int(target[fragment]))
        latency.append(
            round(evaluate(catalog, window, sim.generator, sim.topology, cfg.cost).mean_latency_ms, 3)
        )
        homes.append([int(t) for t in target])

        by_region = (window.reads + window.writes).sum(axis=0)
        traffic.append([round(float(x), 5) for x in by_region / by_region.sum()])

        if sim.last.done:
            break
        sim.step(sim.action_space.noop_index)
    return {"latency": latency, "homes": homes, "regionTraffic": traffic}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None,
                        help="a saved FragAllocConfig JSON to start from "
                             "(see configs/), instead of the built-in defaults")
    parser.add_argument("--volatility", type=float, default=1.0)
    parser.add_argument("--windows", type=int, default=200)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=Path("results/episode.json"))
    args = parser.parse_args()

    base = FragAllocConfig.load(args.config) if args.config else FragAllocConfig()
    cfg = base.evolve(
        workload=replace(base.workload, volatility=args.volatility),
        episode=replace(base.episode, windows_per_episode=args.windows),
        seed=args.seed,
    )
    sim = ClusterSimulator(cfg)
    space = sim.action_space

    reference = instantaneous_best(sim, cfg, args.seed)
    payload = {
        "meta": {
            "generated": date.today().isoformat(),
            "regions": list(cfg.topology.region_names),
            "longitudes": list(cfg.topology.region_longitudes_deg),
            "regionMeta": region_meta(cfg.topology.region_names),
            "windows": args.windows,
            "seed": args.seed,
            "volatility": args.volatility,
            "diurnalPeriodWindows": cfg.workload.diurnal_period_windows,
            "rtt": [[round(float(x), 1) for x in row] for row in sim.topology.rtt],
        },
        "regionTraffic": reference["regionTraffic"],
        "policies": {
            "static": {
                "label": "Do nothing",
                "note": "What a normal sharded database does: the layout never changes.",
                **run(sim, StaticHashPolicy(space), args.seed),
            },
            "follow": {
                "label": "Chase the traffic",
                "note": "Every turn, move the single worst-placed chunk to where its traffic is.",
                **run(sim, FollowTrafficPolicy(space), args.seed),
            },
            "best": {
                "label": "Best possible each turn",
                "note": "Re-home every chunk optimally every turn, with moving data made free.",
                "latency": reference["latency"],
                "homes": reference["homes"],
                "gbMoved": [0.0] * (args.windows + 1),
            },
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload), encoding="utf-8")
    size_kb = args.out.stat().st_size / 1024
    print(f"wrote {args.out} ({size_kb:.0f} KB)")
    for name, p in payload["policies"].items():
        mean = float(np.mean(p["latency"]))
        gb = float(np.sum(p["gbMoved"]))
        print(f"  {name:<8s} mean {mean:7.2f} ms   {gb:7.1f} GB moved")


if __name__ == "__main__":
    main()
