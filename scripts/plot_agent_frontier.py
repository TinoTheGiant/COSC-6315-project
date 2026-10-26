#!/usr/bin/env python3
"""Latency against data movement, for every policy at one volatility.

    python scripts/plot_agent_frontier.py --volatility 4.0

The point this figure exists to make: comparing the agent to the heuristic on
latency alone compares them on something only one of them is optimizing. On
this plane the trade is visible. Follow traffic sits low and far right, having
bought its latency with a terabyte of movement. The agent sits higher and hard
against the left axis. Static hashing sits at the top left, having bought
nothing.

Reads the transcribed tables in results/recorded/ rather than a run directory,
because the agent runs live in Actions artifacts rather than on this machine.
Each row in those files names the run it came from.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fragalloc import viz  # noqa: E402

RECORDED = Path(__file__).resolve().parent.parent / "results" / "recorded"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--volatility", type=float, default=4.0)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    agents = pd.read_csv(RECORDED / "agent-runs.csv", comment="#")
    base = pd.read_csv(RECORDED / "baselines-heldout.csv", comment="#")
    agents = agents[agents.volatility == args.volatility]
    base = base[base.volatility == args.volatility]
    if agents.empty or base.empty:
        raise SystemExit(f"no recorded rows at volatility {args.volatility:g}")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    viz.use_paper_style()
    fig, ax = plt.subplots(figsize=viz.FIG_1COL)

    for _, row in base.iterrows():
        key = row.policy
        if key == "best":
            # The bound pays no movement, so it is a rule rather than a point.
            viz.policy_reference(ax, row.latency_ms, "best", side="left")
            continue
        spec = viz.POLICY.get(key, {})
        ax.scatter(row.gb_moved, row.latency_ms, s=46, zorder=spec.get("z", 3),
                   color=spec.get("color", viz.MUTED), marker="s")
        # Static hash and random sit close together at the left, so their
        # labels are placed on opposite sides rather than both above.
        offset = {"static": (-4, 11), "random": (10, 7), "follow": (0, 11)}.get(key, (0, 9))
        align = {"static": "left", "random": "left"}.get(key, "center")
        ax.annotate(spec.get("label", key), (row.gb_moved, row.latency_ms),
                    textcoords="offset points", xytext=offset, fontsize=7,
                    ha=align, color=spec.get("color", viz.MUTED))

    spec = viz.POLICY["agent"]
    ax.scatter(agents.agent_gb, agents.agent_latency_ms, s=52, zorder=spec["z"],
               color=spec["color"], marker="o")
    # The agent runs cluster tightly, so the labels fan out rather than stack.
    fan = [(10, 6), (12, -1), (10, -8), (12, 12), (10, -14)]
    for i, (_, row) in enumerate(agents.sort_values("agent_gb").iterrows()):
        ax.annotate(f"run {int(row.run)}  w={row.w_migration:g}  seed {int(row.seed)}",
                    (row.agent_gb, row.agent_latency_ms),
                    textcoords="offset points", xytext=fan[i % len(fan)], fontsize=6,
                    ha="left", va="center", color=spec["color"])

    ax.set_xlabel("data moved over the episode (GB)")
    ax.set_ylabel("mean latency (ms)")
    ax.set_title(f"volatility {args.volatility:g}, held-out seeds", fontsize=8)

    out = args.out or Path("paper/figures") / f"frontier-v{args.volatility:g}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out, dpi=300)
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
