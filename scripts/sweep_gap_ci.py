#!/usr/bin/env python3
"""Paired bootstrap interval for the follow-to-bound gap in each sweep run.

The paper quotes the gap between the follow-traffic heuristic and the
per-window bound at each volatility. Each run's report.md gives an interval
per policy, but the gap is a paired quantity (same seed, two policies), so
its interval has to be computed from the per-seed differences.

    python scripts/sweep_gap_ci.py results/runs/*sweep-v*/

Uses the same percentile bootstrap, repetitions and RNG seed as
run_experiment.py, so the numbers are reproducible to the digit.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_experiment import bootstrap_ci  # noqa: E402


def gap(run_dir: Path) -> tuple[float, float, float, float]:
    summary = pd.read_csv(run_dir / "summary.csv")
    latency = summary.pivot(index="seed", columns="policy", values="mean_latency_ms")
    diff = (latency["follow"] - latency["best"]).to_numpy()
    volatility = float(pd.read_json(run_dir / "config.json", typ="series")["workload"]["volatility"])
    low, high = bootstrap_ci(diff)
    return volatility, float(diff.mean()), low, high


def main(paths: list[str]) -> None:
    rows = sorted(gap(Path(p)) for p in paths)
    print("volatility,gap_ms,ci_low,ci_high")
    for volatility, mean, low, high in rows:
        print(f"{volatility},{mean:.2f},{low:.2f},{high:.2f}")


if __name__ == "__main__":
    main(sys.argv[1:])
