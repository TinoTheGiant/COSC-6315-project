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
OUT = ROOT / "paper" / "figures"


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
    """Co-located against spread leaseholders, both pilots."""
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


def objective_figure(plt) -> None:
    """Every policy scored under the objective the agent actually minimises.

    The latency figures elsewhere in the paper show one term of a three-term
    cost. This figure shows the whole cost, which is the only comparison that
    decides whether the learned policy is better, and it scores each pair at
    the SAME migration weight, because scoring a learned run against a
    baseline evaluated at a different weight is how a win gets manufactured.
    """
    import csv

    def cost(lat, gb, imb, w):
        return lat / 100.0 + w * (gb / 2000.0) + 0.10 * imb

    def read(name):
        with open(REC / name, newline="") as fh:
            return list(csv.DictReader(ln for ln in fh if not ln.startswith("#")))

    base = {(float(r["volatility"]), r["policy"]):
            (float(r["latency_ms"]), float(r["gb_moved"]), float(r["imbalance"]))
            for r in read("baselines-heldout.csv") if r["imbalance"]}

    # Only the w = 0.30 agent runs, so every bar in a group shares one weight.
    agents = [r for r in read("agent-runs.csv")
              if r["agent_imbalance"] and float(r["w_migration"]) == 0.30]

    W = 0.30
    vols = [2.0, 4.0]
    fig, ax = plt.subplots(figsize=viz.FIG_1COL_TALL)

    width = 0.26
    for off, key in ((-width, "static"), (0.0, "follow")):
        spec = viz.POLICY[key]
        ax.bar([i + off for i in range(len(vols))],
               [cost(*base[(v, key)], W) for v in vols],
               width=width, color=spec["color"], edgecolor=viz.INK,
               linewidth=0.5, label=spec["label"], zorder=spec["z"])

    # One bar per volatility for the agent: its best recorded learner seed at
    # that volatility. Both seeds are reported in the table; the figure would
    # become unreadable with two more bars.
    agent_cost = {}
    for r in agents:
        v = float(r["volatility"])
        c = cost(float(r["agent_latency_ms"]), float(r["agent_gb"]),
                 float(r["agent_imbalance"]), W)
        agent_cost[v] = min(c, agent_cost.get(v, c))
    spec = viz.POLICY["agent"]
    ax.bar([i + width for i in range(len(vols))],
           [agent_cost[v] for v in vols], width=width, color=spec["color"],
           edgecolor=viz.INK, linewidth=0.5, label=spec["label"],
           zorder=spec["z"])

    for i, v in enumerate(vols):
        for off, val in ((-width, cost(*base[(v, "static")], W)),
                         (0.0, cost(*base[(v, "follow")], W)),
                         (width, agent_cost[v])):
            ax.annotate(f"{val:.3f}", (i + off, val), textcoords="offset points",
                        xytext=(0, 3), ha="center", fontsize=6)

    # The bound, as a reference rule per group rather than a fourth series.
    for i, v in enumerate(vols):
        b = cost(*base[(v, "best")], W)
        ax.plot([i - 1.6 * width, i + 1.6 * width], [b, b],
                color=viz.POLICY["best"]["color"],
                dashes=viz.POLICY["best"]["dash"][1] or (1, 0),
                linewidth=viz.POLICY["best"]["lw"], zorder=6,
                label=viz.POLICY["best"]["label"] if i == 0 else None)
        ax.annotate(f"{b:.3f}", (i + 1.6 * width, b), textcoords="offset points",
                    xytext=(2, -1), ha="left", va="center", fontsize=6,
                    color=viz.POLICY["best"]["color"])

    ax.set_xticks(range(len(vols)))
    ax.set_xticklabels([f"volatility {v:g}" for v in vols])
    ax.set_ylabel("objective cost (lower is better)")
    ax.set_ylim(0.70, 1.95)
    ax.set_xlim(-0.58, len(vols) - 1 + 0.78)
    ax.legend(frameon=False, fontsize=6.0, loc="upper left", ncol=2,
              columnspacing=1.0, handlelength=1.6)
    fig.tight_layout()
    fig.savefig(OUT / "objective.png", dpi=300)
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
    objective_figure(plt)
    print("wrote sweep.png, movement.png, cluster.png, objective.png to", OUT)


if __name__ == "__main__":
    main()
