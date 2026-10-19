#!/usr/bin/env python3
"""Nine statistical views of the same question: is chasing the traffic worth it?

Run after the simulation. Builds tidy pandas frames from fresh episodes, then
draws a single page covering distribution, spread, rhythm, cost and stability.

    python scripts/analysis_dashboard.py
    python scripts/analysis_dashboard.py --seeds 5 --windows 300 --out results/figures/analysis.png

Each panel answers one question:

1  distribution      Is the average hiding a bad tail?
2  cumulative curve  What fraction of turns come in under a given latency?
3  mean with CI      Is the gap bigger than the noise between seeds?
4  cost curve        What does each millisecond saved cost in bandwidth?
5  daily rhythm      Does the advantage come and go with the day?
6  request origins   Where does the load actually come from?
7  residence time    How long does a chunk get to stay put?
8  load balance      Does chasing latency pile work onto one region?
9  tracking error    How far behind the moving target does each strategy sit?
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec

from shardmind import viz
from shardmind.actions import ActionSpace
from shardmind.config import ShardMindConfig
from shardmind.cost import evaluate
from shardmind.policies import FollowTrafficPolicy, StaticHashPolicy
from shardmind.simulator import ClusterSimulator

TITLE = "Reinforcement Learning for Dynamic Data Fragmentation and Allocation"

POLICIES = ["static", "follow", "best"]


# ------------------------------------------------------------------ data

def episode_frame(cfg: ShardMindConfig, seed: int) -> pd.DataFrame:
    """One seeded episode under every strategy, as tidy rows."""
    space = ActionSpace(cfg.catalog.max_fragments, cfg.n_regions)
    rows = []

    for key in POLICIES:
        sim = ClusterSimulator(cfg)
        sim.reset(seed=seed)
        policy = {"static": StaticHashPolicy(space), "follow": FollowTrafficPolicy(space)}.get(key)
        prev_homes = list(sim.catalog.primary)
        cumulative = 0.0

        for turn in range(cfg.episode.windows_per_episode + 1):
            window = sim.last.window
            if key == "best":
                catalog = sim.catalog.copy()
                demand = catalog.aggregate_cells(window.reads + window.writes)
                target = (demand @ sim.topology.rtt).argmin(axis=1)
                for fragment in range(catalog.n_fragments):
                    catalog.set_primary(fragment, int(target[fragment]))
                cost = evaluate(catalog, window, sim.generator, sim.topology, cfg.cost)
                homes = [int(t) for t in target]
            else:
                cost = sim.last.cost
                homes = [int(p) for p in sim.catalog.primary]

            by_region = (window.reads + window.writes).sum(axis=0)
            rows.append({
                "policy": key, "seed": seed, "turn": turn,
                "phase": turn % cfg.workload.diurnal_period_windows,
                "latency": cost.mean_latency_ms,
                "tail": cost.tail_latency_ms,
                "imbalance": cost.load_imbalance,
                "gb": sim.last.bytes_moved / 1e9,
                "cum_gb": cumulative,
                "moves": sum(1 for a, b in zip(prev_homes, homes) if a != b),
                "top_region_share": float(by_region.max() / by_region.sum()),
                **{f"ops_{i}": float(v) for i, v in enumerate(cost.ops_per_region)},
                **{f"traffic_{i}": float(v / by_region.sum()) for i, v in enumerate(by_region)},
            })
            prev_homes = homes
            if sim.last.done:
                break
            sim.step(policy.act(sim) if policy else space.noop_index)
            cumulative += sim.last.bytes_moved / 1e9

    return pd.DataFrame(rows)


def sweep_frame(base: ShardMindConfig, volatilities, seeds: int, windows: int) -> pd.DataFrame:
    """Latency and churn across the volatility sweep, one row per run."""
    rows = []
    for volatility in volatilities:
        cfg = base.evolve(
            workload=replace(base.workload, volatility=volatility),
            episode=replace(base.episode, windows_per_episode=windows),
        )
        for seed in range(seeds):
            frame = episode_frame(cfg, seed)
            for key, group in frame.groupby("policy"):
                rows.append({
                    "policy": key, "volatility": volatility, "seed": seed,
                    "latency": group["latency"].mean(),
                    "gb": group["gb"].sum(),
                    "moves": group["moves"].sum(),
                })
    return pd.DataFrame(rows)


def residence_times(frame: pd.DataFrame, cfg: ShardMindConfig) -> dict[str, list[int]]:
    """How many consecutive turns each chunk spent in one region."""
    # Reconstructed from move counts is not enough, so re-run and track per chunk.
    space = ActionSpace(cfg.catalog.max_fragments, cfg.n_regions)
    out: dict[str, list[int]] = {}
    for key in POLICIES:
        sim = ClusterSimulator(cfg)
        sim.reset(seed=int(frame["seed"].iloc[0]))
        policy = {"static": StaticHashPolicy(space), "follow": FollowTrafficPolicy(space)}.get(key)
        n = sim.catalog.n_fragments
        since = [0] * n
        prev = list(sim.catalog.primary)
        spans: list[int] = []
        for _ in range(cfg.episode.windows_per_episode):
            if key == "best":
                window = sim.last.window
                demand = sim.catalog.aggregate_cells(window.reads + window.writes)
                homes = [int(t) for t in (demand @ sim.topology.rtt).argmin(axis=1)]
                sim.step(space.noop_index)
            else:
                sim.step(policy.act(sim))
                homes = list(sim.catalog.primary)
            for c in range(n):
                if homes[c] != prev[c]:
                    spans.append(since[c] + 1)
                    since[c] = 0
                else:
                    since[c] += 1
            prev = homes
        spans.extend(s + 1 for s in since)
        out[key] = spans
    return out


# ---------------------------------------------------------------- panels

def panel_distribution(ax, frame: pd.DataFrame) -> None:
    ax.set_title("1. Is the average hiding a bad tail?")
    data = [frame.loc[frame.policy == k, "latency"].to_numpy() for k in POLICIES]
    parts = ax.violinplot(data, positions=range(3), widths=0.78, showextrema=False)
    for body, key in zip(parts["bodies"], POLICIES):
        body.set_facecolor(viz.POLICY_COLOR[key])
        body.set_alpha(0.22)
        body.set_edgecolor("none")
    box = ax.boxplot(data, positions=range(3), widths=0.16, patch_artist=True,
                     medianprops={"color": viz.SURFACE, "lw": 1.6},
                     flierprops={"marker": ".", "ms": 3, "mfc": viz.MUTED, "mec": "none"},
                     whiskerprops={"color": viz.MUTED, "lw": 1},
                     capprops={"color": viz.MUTED, "lw": 1})
    for patch, key in zip(box["boxes"], POLICIES):
        patch.set_facecolor(viz.POLICY_COLOR[key])
        patch.set_edgecolor("none")
    ax.set_xticks(range(3), [viz.POLICY_LABEL[k].replace(" each turn", "") for k in POLICIES],
                  fontsize=8)
    ax.set_ylabel("mean latency per turn (ms)")
    ax.grid(axis="y")
    ax.set_axisbelow(True)


def panel_cdf(ax, frame: pd.DataFrame) -> None:
    ax.set_title("2. What share of turns beat a given latency?")
    for key in POLICIES:
        v = np.sort(frame.loc[frame.policy == key, "latency"].to_numpy())
        ax.plot(v, np.linspace(0, 1, len(v)), color=viz.POLICY_COLOR[key],
                label=viz.POLICY_LABEL[key])
    ax.axhline(0.5, color=viz.MUTED, lw=0.8, ls=(0, (3, 3)))
    ax.annotate("median", (ax.get_xlim()[0], 0.5), xytext=(4, 4),
                textcoords="offset points", fontsize=7.5, color=viz.MUTED)
    ax.set_xlabel("mean latency per turn (ms)")
    ax.set_ylabel("share of turns at or below")
    ax.set_ylim(0, 1)
    ax.legend(loc="lower right")
    ax.grid(axis="y")
    ax.set_axisbelow(True)


def panel_means(ax, sweep: pd.DataFrame, volatility: float) -> None:
    ax.set_title("3. Is the gap bigger than the noise?")
    subset = sweep[sweep.volatility == volatility]
    means, errs = [], []
    for key in POLICIES:
        v = subset.loc[subset.policy == key, "latency"].to_numpy()
        means.append(v.mean())
        errs.append(1.96 * v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else 0.0)
    bars = ax.bar(range(3), means, yerr=errs, width=0.56, capsize=5,
                  color=[viz.POLICY_COLOR[k] for k in POLICIES],
                  error_kw={"ecolor": viz.INK_2, "lw": 1.2})
    for rect, m, e in zip(bars, means, errs):
        ax.annotate(f"{m:.0f}", (rect.get_x() + rect.get_width() / 2, m + e),
                    xytext=(0, 7), textcoords="offset points", ha="center",
                    fontsize=9, fontweight="bold", color=viz.INK_2)
    ax.set_ylim(0, (max(means) + max(errs)) * 1.22)
    ax.set_xticks(range(3), [viz.POLICY_LABEL[k].replace(" each turn", "") for k in POLICIES],
                  fontsize=8)
    ax.set_ylabel("mean latency (ms), 95% CI")
    ax.grid(axis="y")
    ax.set_axisbelow(True)


def panel_tradeoff(ax, sweep: pd.DataFrame) -> None:
    ax.set_title("4. What does a millisecond cost in bandwidth?")
    grouped = sweep.groupby(["policy", "volatility"]).mean(numeric_only=True).reset_index()

    chase = grouped[grouped.policy == "follow"].sort_values("volatility")
    ax.plot(chase["gb"], chase["latency"], "-o", ms=6.5,
            color=viz.POLICY_COLOR["follow"], mec=viz.SURFACE, mew=1.3, zorder=3)
    for _, row in chase.iterrows():
        ax.annotate(f"volatility {row.volatility:g}", (row.gb, row.latency),
                    xytext=(7, 7), textcoords="offset points",
                    fontsize=7.5, color=viz.MUTED)

    # The other two never move data, so they are lines, not points.
    for key in ("static", "best"):
        level = grouped.loc[grouped.policy == key, "latency"].mean()
        ax.axhline(level, color=viz.POLICY_COLOR[key], lw=1.6, ls=(0, (5, 3)), zorder=2)
        ax.annotate(f"{viz.POLICY_LABEL[key]} — {level:.0f} ms, nothing moved",
                    (0.02, level), xycoords=("axes fraction", "data"),
                    xytext=(0, 5), textcoords="offset points",
                    fontsize=8, color=viz.POLICY_COLOR[key])

    ax.set_xlabel("data moved per episode (GB)")
    ax.set_ylabel("mean latency (ms)")
    ax.set_xlim(left=-30)
    ax.annotate("cheaper and faster is down and left", (0.02, 0.04),
                xycoords="axes fraction", fontsize=8, color=viz.MUTED)
    ax.grid(True)
    ax.set_axisbelow(True)


def panel_rhythm(ax, frame: pd.DataFrame, period: int) -> None:
    ax.set_title("5. Does the advantage follow the day?")
    for key in POLICIES:
        g = frame[frame.policy == key].groupby("phase")["latency"]
        mean, sd = g.mean(), g.std().fillna(0)
        ax.plot(mean.index, mean.values, color=viz.POLICY_COLOR[key],
                label=viz.POLICY_LABEL[key])
        ax.fill_between(mean.index, mean - sd, mean + sd,
                        color=viz.POLICY_COLOR[key], alpha=0.13, lw=0)
    ax.set_xlim(0, period - 1)
    ax.set_xlabel(f"position in the day (0 to {period - 1} turns)")
    ax.set_ylabel("mean latency (ms)")
    ax.legend(loc="upper right")
    ax.grid(axis="y")
    ax.set_axisbelow(True)


def panel_origins(ax, frame: pd.DataFrame, regions: list[str]) -> None:
    ax.set_title("6. Where the load came from, at its most lopsided")
    one = frame[frame.policy == "static"]
    peak = one.loc[one["top_region_share"].idxmax()]
    shares = np.array([peak[f"traffic_{i}"] for i in range(len(regions))])
    order = np.argsort(shares)[::-1]
    wedges, _ = ax.pie(
        shares[order], colors=[viz.region_color(i) for i in order],
        startangle=90, counterclock=False,
        wedgeprops={"width": 0.40, "edgecolor": viz.SURFACE, "linewidth": 1.6},
    )
    ax.text(0, 0.06, "busiest region", ha="center", fontsize=8, color=viz.MUTED)
    ax.text(0, -0.26, f"{shares[order[0]] * 100:.0f}%", ha="center", fontsize=19,
            fontweight="bold", color=viz.region_color(int(order[0])))
    ax.legend(wedges, [f"{regions[i]}  {shares[i] * 100:.0f}%" for i in order],
              loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=7.5)
    average = np.mean([one[f"traffic_{i}"].max() for i in range(len(regions))])
    ax.annotate(
        f"Averaged over the whole episode every region lands near an even "
        f"{100 / len(regions):.0f}%, because the busy band travels. The skew is "
        f"only visible turn by turn: this is turn {int(peak.turn)}.",
        (0.5, -0.12), xycoords="axes fraction", ha="center", va="top",
        fontsize=7.5, color=viz.MUTED, wrap=True,
    )


def panel_residence(ax, spans: dict[str, list[int]]) -> None:
    ax.set_title("7. How long does a chunk stay put?")
    bins = np.arange(0, 42, 3)
    for key in ("follow", "best"):
        ax.hist(np.clip(spans[key], 0, 40), bins=bins, histtype="stepfilled",
                color=viz.POLICY_COLOR[key], alpha=0.35, lw=0,
                label=f"{viz.POLICY_LABEL[key]} (median {int(np.median(spans[key]))})")
        ax.hist(np.clip(spans[key], 0, 40), bins=bins, histtype="step",
                color=viz.POLICY_COLOR[key], lw=1.6)
    ax.set_xlabel("consecutive turns in one region")
    ax.set_ylabel("count")
    ax.legend(loc="upper right")
    ax.grid(axis="y")
    ax.set_axisbelow(True)


def panel_balance(ax, frame: pd.DataFrame, regions: list[str]) -> None:
    ax.set_title("8. Does chasing latency unbalance the cluster?")
    width = 0.26
    x = np.arange(len(regions))
    for slot, key in enumerate(POLICIES):
        g = frame[frame.policy == key]
        totals = np.array([g[f"ops_{i}"].mean() for i in range(len(regions))])
        ax.bar(x + (slot - 1) * width, totals / totals.sum() * 100, width=width * 0.92,
               color=viz.POLICY_COLOR[key], label=viz.POLICY_LABEL[key])
    ax.axhline(100 / len(regions), color=viz.MUTED, lw=1, ls=(0, (3, 3)))
    ax.annotate("an even split", (-0.45, 100 / len(regions)),
                xytext=(0, 4), textcoords="offset points", ha="left",
                fontsize=7.5, color=viz.MUTED)
    ax.set_xticks(x, [r.replace("-1", "").replace("-2", "") for r in regions],
                  fontsize=7.5, rotation=20, ha="right")
    ax.set_ylabel("share of work done (%)")
    ax.legend(loc="upper right", fontsize=7.5)
    ax.grid(axis="y")
    ax.set_axisbelow(True)


def panel_tracking(ax, frame: pd.DataFrame) -> None:
    ax.set_title("9. How far behind the moving target?")
    best = frame[frame.policy == "best"].groupby("turn")["latency"].mean()
    for key in ("static", "follow"):
        series = frame[frame.policy == key].groupby("turn")["latency"].mean() - best
        ax.plot(series.index, series.rolling(9, min_periods=1, center=True).mean(),
                color=viz.POLICY_COLOR[key], label=viz.POLICY_LABEL[key])
        ax.fill_between(series.index, 0,
                        series.rolling(9, min_periods=1, center=True).mean(),
                        color=viz.POLICY_COLOR[key], alpha=0.12, lw=0)
    ax.axhline(0, color=viz.MUTED, lw=1)
    ax.set_xlabel("turn")
    ax.set_ylabel("ms behind the best each turn")
    ax.legend(loc="upper right")
    ax.grid(axis="y")
    ax.set_axisbelow(True)


# ------------------------------------------------------------------ main

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=None,
                        help="a saved ShardMindConfig JSON to start from "
                             "(see configs/), instead of the built-in defaults")
    parser.add_argument("--seeds", type=int, default=4)
    parser.add_argument("--windows", type=int, default=200)
    parser.add_argument("--volatility", type=float, default=1.0)
    parser.add_argument("--out", type=Path, default=Path("results/figures/analysis.png"))
    parser.add_argument("--show", action="store_true", help="open a window instead of saving")
    args = parser.parse_args()

    base = ShardMindConfig.load(args.config) if args.config else ShardMindConfig()
    cfg = base.evolve(
        workload=replace(base.workload, volatility=args.volatility),
        episode=replace(base.episode, windows_per_episode=args.windows),
    )
    regions = list(cfg.topology.region_names)

    print("running episodes...")
    frame = pd.concat([episode_frame(cfg, seed) for seed in range(args.seeds)],
                      ignore_index=True)
    print("running the volatility sweep...")
    sweep = sweep_frame(base, [0.0, 1.0, 2.0, 4.0, 8.0], max(2, args.seeds // 2),
                        min(args.windows, 150))
    spans = residence_times(frame, cfg)

    viz.use_house_style()
    fig = plt.figure(figsize=(16.5, 12.5))
    gs = GridSpec(3, 3, figure=fig, hspace=0.42, wspace=0.28,
                  left=0.055, right=0.965, top=0.90, bottom=0.05)

    fig.text(0.055, 0.966, TITLE, fontsize=15, fontweight="bold", color=viz.INK)
    fig.text(0.055, 0.941, "Does chasing the traffic pay?",
             fontsize=19, fontweight="bold", color=viz.INK)
    fig.text(0.055, 0.916,
             f"{args.seeds} seeds x {args.windows} turns at volatility {args.volatility}, "
             f"plus a sweep from 0 to 8.  Every panel is the same simulated cluster, "
             f"asked a different question.",
             fontsize=10, color=viz.MUTED)

    panel_distribution(fig.add_subplot(gs[0, 0]), frame)
    panel_cdf(fig.add_subplot(gs[0, 1]), frame)
    panel_means(fig.add_subplot(gs[0, 2]), sweep, args.volatility)
    panel_tradeoff(fig.add_subplot(gs[1, 0]), sweep)
    panel_rhythm(fig.add_subplot(gs[1, 1]), frame, cfg.workload.diurnal_period_windows)
    panel_origins(fig.add_subplot(gs[1, 2]), frame, regions)
    panel_residence(fig.add_subplot(gs[2, 0]), spans)
    panel_balance(fig.add_subplot(gs[2, 1]), frame, regions)
    panel_tracking(fig.add_subplot(gs[2, 2]), frame)

    if args.show:
        plt.show()
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.out, dpi=150, bbox_inches="tight")
        print(f"wrote {args.out}")

    summary = frame.groupby("policy").agg(
        mean_ms=("latency", "mean"), p95_ms=("latency", lambda s: s.quantile(0.95)),
        gb=("gb", "sum"), moves=("moves", "sum"),
    ).reindex(POLICIES)
    print()
    print(summary.round(1).to_string())


if __name__ == "__main__":
    main()
