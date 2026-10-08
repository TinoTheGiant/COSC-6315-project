#!/usr/bin/env python3
"""Render the episode figures as PNGs, ready for the paper.

Reads the JSON written by ``export_episode.py`` and writes four figures into
``results/figures/``. Run the export first.

    python scripts/export_episode.py
    python scripts/plot_figures.py

Colors come from a colorblind-checked categorical palette. Keep the slot order:
it is what keeps adjacent series distinguishable under color vision deficiency.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"
BLUE_RAMP = ["#fcfcfb", "#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#184f95", "#0d366b"]

mpl.rcParams.update({
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "font.family": "sans-serif",
    "font.size": 10,
    "text.color": INK,
    "axes.labelcolor": INK,
    "axes.edgecolor": GRID,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "grid.color": GRID,
    "grid.linewidth": 0.6,
    "lines.linewidth": 2.0,
})


def traffic_heatmap(data: dict, out: Path) -> None:
    """Where the requests came from, window by window."""
    traffic = np.array(data["regionTraffic"]).T  # regions x windows
    regions = data["meta"]["regions"]

    fig, ax = plt.subplots(figsize=(10, 2.8))
    cmap = LinearSegmentedColormap.from_list("blues", BLUE_RAMP)
    im = ax.imshow(traffic, aspect="auto", cmap=cmap, vmin=0, interpolation="nearest")

    ax.set_yticks(range(len(regions)), regions)
    ax.set_xlabel("decision window")
    ax.set_title("Where the traffic came from", loc="left", fontweight="bold", pad=10)
    period = data["meta"]["diurnalPeriodWindows"]
    for x in range(period, traffic.shape[1], period):
        ax.axvline(x - 0.5, color=INK, lw=0.8, ls=":", alpha=0.35)

    bar = fig.colorbar(im, ax=ax, pad=0.015, fraction=0.03)
    bar.set_label("share of requests", color=MUTED)
    bar.outline.set_visible(False)
    ax.annotate(
        f"Dotted lines mark one full day ({period} windows). "
        "An even split would be 16.7% everywhere.",
        xy=(0, -0.42), xycoords="axes fraction", color=MUTED, fontsize=8, va="top",
    )
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)


def latency_over_time(data: dict, out: Path) -> None:
    """The headline comparison."""
    fig, ax = plt.subplots(figsize=(10, 4))
    order = ["static", "greedy", "best"]
    for slot, key in enumerate(order):
        p = data["policies"][key]
        y = np.array(p["latency"])
        ax.plot(y, color=SERIES[slot], label=p["label"], alpha=0.95)
        ax.annotate(f"{y.mean():.0f} ms avg", xy=(len(y) - 1, y[-1]),
                    xytext=(6, 0), textcoords="offset points",
                    color=SERIES[slot], fontsize=9, va="center", fontweight="bold")

    ax.set_xlabel("decision window")
    ax.set_ylabel("mean request latency (ms)")
    ax.set_title("What each strategy costs the user", loc="left", fontweight="bold", pad=10)
    ax.grid(axis="y")
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper right", ncols=3)
    ax.margins(x=0.08)
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)


def cumulative_migration(data: dict, out: Path) -> None:
    """What chasing the traffic costs in bandwidth."""
    fig, ax = plt.subplots(figsize=(10, 3.4))
    for slot, key in enumerate(["static", "greedy"]):
        p = data["policies"][key]
        y = np.cumsum(p["gbMoved"])
        ax.plot(y, color=SERIES[slot], label=p["label"])
        ax.annotate(f"{y[-1]:.0f} GB", xy=(len(y) - 1, y[-1]), xytext=(6, 0),
                    textcoords="offset points", color=SERIES[slot],
                    fontsize=9, va="center", fontweight="bold")

    ax.set_xlabel("decision window")
    ax.set_ylabel("cumulative data moved (GB)")
    ax.set_title("What chasing the traffic costs", loc="left", fontweight="bold", pad=10)
    ax.grid(axis="y")
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper left")
    ax.margins(x=0.08)
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)


def chunk_homes(data: dict, out: Path) -> None:
    """Which region each chunk lived in, turn by turn, under each strategy."""
    regions = data["meta"]["regions"]
    keys = ["static", "greedy", "best"]

    fig, axes = plt.subplots(len(keys), 1, figsize=(10, 6.2), sharex=True)
    for ax, key in zip(axes, keys):
        homes = np.array(data["policies"][key]["homes"]).T  # chunks x windows
        cmap = mpl.colors.ListedColormap(SERIES[: len(regions)])
        ax.imshow(homes, aspect="auto", cmap=cmap, vmin=0, vmax=len(regions) - 1,
                  interpolation="nearest")
        ax.set_yticks(range(homes.shape[0]), [f"chunk {i}" for i in range(homes.shape[0])])
        ax.set_title(data["policies"][key]["label"], loc="left", fontsize=10, fontweight="bold")
        ax.tick_params(length=0)

    axes[-1].set_xlabel("decision window")
    fig.suptitle("Where each chunk lived", x=0.125, ha="left", fontweight="bold", fontsize=12)
    handles = [Patch(facecolor=SERIES[i], label=r) for i, r in enumerate(regions)]
    fig.legend(handles=handles, frameon=False, loc="lower center", ncols=6,
               bbox_to_anchor=(0.5, -0.04))
    fig.tight_layout(rect=(0, 0.02, 1, 0.96))
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("results/episode.json"))
    parser.add_argument("--outdir", type=Path, default=Path("results/figures"))
    args = parser.parse_args()

    if not args.data.exists():
        raise SystemExit(f"{args.data} not found. Run: python scripts/export_episode.py")

    data = json.loads(args.data.read_text(encoding="utf-8"))
    args.outdir.mkdir(parents=True, exist_ok=True)

    figures = {
        "traffic-heatmap.png": traffic_heatmap,
        "latency-over-time.png": latency_over_time,
        "cumulative-migration.png": cumulative_migration,
        "chunk-homes.png": chunk_homes,
    }
    for name, fn in figures.items():
        fn(data, args.outdir / name)
        print(f"wrote {args.outdir / name}")


if __name__ == "__main__":
    main()
