#!/usr/bin/env python3
"""Combine several experiment runs into one sweep table and figure.

A sweep is several runs that differ in exactly one setting. Each run is
produced on its own, usually by dispatching the Experiments workflow once per
value, and this script joins them afterwards.

    python scripts/assemble_sweep.py --over volatility results/runs/*/
    python scripts/assemble_sweep.py --over w_migration --out results/figures/frontier

It refuses to combine runs that differ in more than the swept setting. That
check is the reason the script exists rather than a spreadsheet: a sweep
assembled from runs with different episode lengths or different reward weights
is not a sweep, and the resulting figure is wrong in a way nobody notices until
a reviewer asks.

Writes, into the output directory:

    sweep.csv       every (policy, seed, swept value) row from every run
    sweep.md        the table, with the run ids it came from
    sweep.png       latency and movement against the swept value
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fragalloc import viz  # noqa: E402

#: Where each sweepable setting lives inside the resolved config.
SWEEPABLE = {
    "volatility": ("workload", "volatility"),
    "w_migration": ("reward", "w_migration"),
    "w_imbalance": ("reward", "w_imbalance"),
    "read_fraction": ("workload", "read_fraction"),
    "txn_fraction": ("workload", "txn_fraction"),
    "windows_per_episode": ("episode", "windows_per_episode"),
}

LABEL = {"static": "Static hash", "random": "Random", "follow": "Follow traffic",
         "best": "Best per window (fixed shards)", "agent": "Learned policy"}


def load_run(directory: Path) -> tuple[dict, pd.DataFrame]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    summary = pd.read_csv(directory / "summary.csv")
    return manifest, summary


def swept_value(manifest: dict, over: str) -> float:
    section, field = SWEEPABLE[over]
    return float(manifest["config"][section][field])


def config_without(manifest: dict, over: str) -> str:
    """The configuration with the swept field removed, as a comparable string.

    Two runs belong in the same sweep exactly when this matches.
    """
    section, field = SWEEPABLE[over]
    config = json.loads(json.dumps(manifest["config"]))
    config[section].pop(field, None)
    return json.dumps(config, sort_keys=True)


def assemble(directories: list[Path], over: str) -> tuple[pd.DataFrame, list[str]]:
    rows, run_ids, signatures = [], [], {}
    for directory in sorted(directories):
        if not (directory / "manifest.json").exists():
            continue
        manifest, summary = load_run(directory)
        signature = config_without(manifest, over)
        signatures.setdefault(signature, []).append(manifest["run_id"])
        summary[over] = swept_value(manifest, over)
        summary["commit"] = manifest["git"]["commit"][:10]
        rows.append(summary)
        run_ids.append(manifest["run_id"])

    if not rows:
        raise SystemExit("no runs found. Point this at directories under results/runs/")
    if len(signatures) > 1:
        groups = "\n".join(
            f"  group {i + 1}: {', '.join(ids)}" for i, ids in enumerate(signatures.values()))
        raise SystemExit(
            f"these runs differ in more than {over}, so they are not one sweep:\n{groups}\n"
            "Re-run them from a single config, overriding only the swept setting.")

    frame = pd.concat(rows, ignore_index=True)
    return frame, run_ids


def table(frame: pd.DataFrame, over: str, run_ids: list[str]) -> str:
    tail = next((c for c in frame.columns if c.startswith("p") and c.endswith("_latency_ms")),
                "mean_latency_ms")
    values = sorted(frame[over].unique())
    policies = [p for p in ("agent", "static", "random", "follow", "best")
                if p in set(frame["policy"])]

    lines = [
        f"# Sweep over `{over}`",
        "",
        f"{len(run_ids)} runs, {frame['seed'].nunique()} seeds each, "
        f"commit `{frame['commit'].iloc[0]}`.",
        "",
        "## Mean latency (ms)",
        "",
        "| " + over + " | " + " | ".join(LABEL.get(p, p) for p in policies) + " |",
        "|" + "---|" * (len(policies) + 1),
    ]
    for value in values:
        cells = []
        for policy in policies:
            group = frame[(frame[over] == value) & (frame.policy == policy)]
            cells.append(f"{group['mean_latency_ms'].mean():.2f}")
        lines.append(f"| {value:g} | " + " | ".join(cells) + " |")

    lines += ["", "## GB moved per episode", "",
              "| " + over + " | " + " | ".join(LABEL.get(p, p) for p in policies) + " |",
              "|" + "---|" * (len(policies) + 1)]
    for value in values:
        cells = []
        for policy in policies:
            group = frame[(frame[over] == value) & (frame.policy == policy)]
            cells.append(f"{group['gb_moved_total'].mean():.1f}")
        lines.append(f"| {value:g} | " + " | ".join(cells) + " |")

    # The quantity the sweep is usually asked about: does the advantage over
    # doing nothing grow or shrink as the setting moves?
    if {"static", "follow"} <= set(frame["policy"]):
        lines += ["", "## Advantage over static hashing", "",
                  f"| {over} | follow traffic | agent |" if "agent" in set(frame["policy"])
                  else f"| {over} | follow traffic |",
                  "|---|---|---|" if "agent" in set(frame["policy"]) else "|---|---|"]
        for value in values:
            at = frame[frame[over] == value]
            static = at[at.policy == "static"]["mean_latency_ms"].mean()
            cells = [f"{(static - at[at.policy == 'follow']['mean_latency_ms'].mean()) / static * 100:.1f}%"]
            if "agent" in set(frame["policy"]):
                agent = at[at.policy == "agent"]["mean_latency_ms"].mean()
                cells.append(f"{(static - agent) / static * 100:.1f}%")
            lines.append(f"| {value:g} | " + " | ".join(cells) + " |")

    lines += ["", "## Runs combined", "", *(f"- `{r}`" for r in run_ids), ""]
    return "\n".join(lines)


def figure(frame: pd.DataFrame, over: str, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    viz.use_paper_style()
    series = [p for p in viz.SERIES_POLICIES if p in set(frame["policy"])]
    fig, (left, right) = plt.subplots(1, 2, figsize=viz.FIG_2COL)

    for key in series:
        group = frame[frame.policy == key].groupby(over)
        mean = group["mean_latency_ms"].mean()
        spread = group["mean_latency_ms"].std().fillna(0.0)
        left.plot(mean.index, mean.values, **viz.policy_kwargs(key))
        left.fill_between(mean.index, mean - spread, mean + spread,
                          color=viz.POLICY[key]["color"], alpha=0.12, linewidth=0)
        moved = frame[frame.policy == key].groupby(over)["gb_moved_total"].mean()
        right.plot(moved.index, moved.values, **viz.policy_kwargs(key))

    if "best" in set(frame["policy"]):
        bound = frame[frame.policy == "best"].groupby(over)["mean_latency_ms"].mean()
        left.plot(bound.index, bound.values, **viz.policy_kwargs("best"))

    left.set_xlabel(over.replace("_", " "))
    left.set_ylabel("mean latency (ms)")
    left.legend(frameon=False, fontsize=7)
    right.set_xlabel(over.replace("_", " "))
    right.set_ylabel("GB moved per episode")
    fig.tight_layout()
    fig.savefig(path, dpi=300)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", nargs="*", type=Path,
                        help="run directories. Defaults to everything under results/runs/")
    parser.add_argument("--over", default="volatility", choices=sorted(SWEEPABLE),
                        help="the setting that varies across the runs")
    parser.add_argument("--out", type=Path, default=None,
                        help="output directory. Defaults to results/sweeps/<over>")
    args = parser.parse_args()

    directories = args.runs or sorted(Path("results/runs").glob("*/"))
    frame, run_ids = assemble([Path(d) for d in directories], args.over)

    out = args.out or Path("results/sweeps") / args.over
    out.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out / "sweep.csv", index=False)
    text = table(frame, args.over, run_ids)
    (out / "sweep.md").write_text(text, encoding="utf-8")
    figure(frame, args.over, out / "sweep.png")

    print(text)
    print(f"written to {out}")


if __name__ == "__main__":
    main()
