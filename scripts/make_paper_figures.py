#!/usr/bin/env python3
"""Draw every figure the paper uses, from the recorded result tables.

    python scripts/make_paper_figures.py

Reads results/recorded/ rather than a run directory, because the agent runs and
the sweep live in GitHub Actions artifacts rather than on this machine. Each row
in those files names the run it came from.

Writes into paper/figures/. Everything uses the project's print-safe style: one
chromatic series for the agent against graded grays, a mandatory dash pattern on
every series, and column widths that match the IEEE two-column measure.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from fragalloc import viz  # noqa: E402

REC = ROOT / "results" / "recorded"
# The midterm draft (main.tex) keeps the figures it was submitted with; the
# CCGrid paper (ccgrid.tex) draws from its own folder.
OUT = ROOT / "paper" / "figures" / "ccgrid"


def sweep_figure(plt) -> None:
    """Latency and movement against volatility. The paper's central figure."""
    d = pd.read_csv(REC / "sweep.csv", comment="#")
    fig, (left, right) = plt.subplots(1, 2, figsize=viz.FIG_2COL)

    for col, key in (("static", "static"), ("follow", "follow")):
        left.plot(d.volatility, d[col], **viz.policy_kwargs(key))
    left.plot(d.volatility, d["bound"], **viz.policy_kwargs("best"))
    left.set_xlabel("workload volatility")
    left.set_ylabel("mean latency (ms)")
    left.set_xscale("log", base=2)
    left.set_xticks(d.volatility)
    left.set_xticklabels([f"{v:g}" for v in d.volatility])
    left.legend(frameon=False, fontsize=6.5, loc="center left")

    # The gap is the quantity the paper argues from, so draw it directly
    # rather than leaving the reader to subtract two lines by eye.
    gap = d["follow"] - d["bound"]
    right.plot(d.volatility, gap, **viz.policy_kwargs("agent",
                                                      label="gap to the bound"))
    right.set_xlabel("workload volatility")
    right.set_ylabel("follow traffic above the bound (ms)")
    right.set_xscale("log", base=2)
    right.set_xticks(d.volatility)
    right.set_xticklabels([f"{v:g}" for v in d.volatility])
    for x, y in zip(d.volatility, gap):
        right.annotate(f"{y:.1f}", (x, y), textcoords="offset points",
                       xytext=(0, 7), ha="center", fontsize=6.5,
                       color=viz.POLICY["agent"]["color"])
    right.set_ylim(bottom=-4)

    fig.tight_layout()
    fig.savefig(OUT / "sweep.png", dpi=300)
    plt.close(fig)


def movement_figure(plt) -> None:
    """What following the traffic costs, as volatility rises."""
    d = pd.read_csv(REC / "sweep.csv", comment="#")
    fig, ax = plt.subplots(figsize=viz.FIG_1COL)
    ax.plot(d.volatility, d.follow_gb, **viz.policy_kwargs("follow"))
    ax.plot(d.volatility, d.random_gb, **viz.policy_kwargs("random")
            if "random" in viz.POLICY else viz.policy_kwargs("static"))
    ax.set_xscale("log", base=2)
    ax.set_xticks(d.volatility)
    ax.set_xticklabels([f"{v:g}" for v in d.volatility])
    ax.set_xlabel("workload volatility")
    ax.set_ylabel("GB moved per episode")
    ax.legend(frameon=False, fontsize=6.5)
    fig.tight_layout()
    fig.savefig(OUT / "movement.png", dpi=300)
    plt.close(fig)


def cluster_figure(plt) -> None:
    """Co-located against spread leaseholders, the RF 3 gate."""
    d = pd.read_csv(REC / "cluster.csv", comment="#")
    fig, ax = plt.subplots(figsize=viz.FIG_1COL)

    labels, p50s, p95s, colors = [], [], [], []
    for _, r in d.iterrows():
        labels.append(f"{r.case}\nN={r.transactions}")
        p50s.append(r.p50_ms); p95s.append(r.p95_ms)
        colors.append(viz.POLICY["static" if r.case == "co-located" else "follow"]["color"])

    x = range(len(labels))
    ax.bar([i - 0.19 for i in x], p50s, width=0.38, color=colors,
           edgecolor=viz.INK, linewidth=0.5, label="p50")
    ax.bar([i + 0.19 for i in x], p95s, width=0.38, color=colors, alpha=0.55,
           edgecolor=viz.INK, linewidth=0.5, hatch="///", label="p95")
    ax.set_xticks(list(x)); ax.set_xticklabels(labels, fontsize=6.5)
    ax.set_ylabel("transaction latency (ms)")
    ax.legend(frameon=False, fontsize=6.5)
    for i, v in enumerate(p95s):
        ax.annotate(f"{v:.0f}", (i + 0.19, v), textcoords="offset points",
                    xytext=(0, 3), ha="center", fontsize=6)
    fig.tight_layout()
    fig.savefig(OUT / "cluster.png", dpi=300)
    plt.close(fig)


def main() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    viz.use_paper_style()
    OUT.mkdir(parents=True, exist_ok=True)
    sweep_figure(plt)
    movement_figure(plt)
    cluster_figure(plt)
    print("wrote sweep.png, movement.png, cluster.png to", OUT)


if __name__ == "__main__":
    main()
