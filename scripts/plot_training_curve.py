#!/usr/bin/env python3
"""Draw the training curve for one or more agent runs, with the baselines on it.

    python scripts/plot_training_curve.py results/models/<id> --out paper/figures/training.png
    python scripts/plot_training_curve.py results/models/A results/models/B --labels "w=0.30" "w=0.00"

A learning curve on its own tells a reader that a number went down. It does not
tell them whether the number went down far enough to matter, and that is the
only question the reader has. So this draws the held-out evaluation against
training step with the follow-traffic baseline and the fixed-shard bound as
reference rules, which turns "the agent improved" into "the agent improved and
is still this far short".

The baselines come from an evaluation run directory, passed with --baselines,
because they must be measured at the same volatility the agent trained at.
Taking them from a different environment would put a reference line on the
figure that means nothing. If no such directory is given, the curve is drawn
without reference lines and the figure says so.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from shardmind import viz  # noqa: E402


def load_history(directory: Path) -> pd.DataFrame:
    path = directory / "eval_history.json"
    if not path.exists():
        raise SystemExit(f"no eval_history.json in {directory}")
    frame = pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))
    if frame.empty:
        raise SystemExit(f"{path} is empty: the run recorded no evaluations")
    return frame


def load_baselines(directory: Path) -> dict[str, float]:
    """Mean latency per policy from an evaluation run's summary.csv."""
    path = directory / "summary.csv"
    if not path.exists():
        return {}
    summary = pd.read_csv(path)
    return {str(policy): float(group["mean_latency_ms"].mean())
            for policy, group in summary.groupby("policy")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("models", nargs="+", type=Path,
                        help="model directories, each holding eval_history.json")
    parser.add_argument("--labels", nargs="*", default=None,
                        help="one label per model directory. Defaults to the directory names")
    parser.add_argument("--baselines", type=Path, default=None,
                        help="an evaluation run directory, for the reference lines. "
                             "It must be at the same volatility the agent trained at")
    parser.add_argument("--out", type=Path, default=Path("paper/figures/training-curve.png"))
    args = parser.parse_args()

    labels = args.labels or [d.name for d in args.models]
    if len(labels) != len(args.models):
        parser.error("--labels needs one label per model directory")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    viz.use_paper_style()
    fig, ax = plt.subplots(figsize=viz.FIG_1COL)

    # The agent's own curve carries the emphasis form. Several runs are
    # separated by line style within that one color, rather than by adding
    # colors, so the figure stays inside the grayscale budget.
    dashes = [(0, ()), (0, (4, 1.5)), (0, (1.5, 1.5)), (0, (6, 2, 1, 2))]
    for i, (directory, label) in enumerate(zip(args.models, labels)):
        history = load_history(directory)
        ax.plot(history["timestep"], history["mean_latency_ms"],
                color=viz.POLICY["agent"]["color"],
                linestyle=dashes[i % len(dashes)],
                linewidth=viz.POLICY["agent"]["lw"],
                zorder=viz.POLICY["agent"]["z"],
                label=f"Learned policy, {label}" if len(args.models) > 1
                      else "Learned policy")

    note = ""
    if args.baselines:
        baselines = load_baselines(args.baselines)
        # Reference labels on the left, legend on the right. They collide
        # otherwise, because the agent's curve starts high on the left and the
        # static baseline's rule sits at the top of the same corner.
        for key in ("follow", "static", "best"):
            if key in baselines:
                viz.policy_reference(ax, baselines[key], key, side="left")
        if not baselines:
            note = "baselines unavailable"
    else:
        note = "no baselines drawn"

    ax.set_xlabel("training step")
    ax.set_ylabel("held-out mean latency (ms)")
    ax.legend(frameon=False, fontsize=7, loc="upper right")
    if note:
        ax.annotate(note, xy=(0.01, 0.01), xycoords="axes fraction",
                    fontsize=6, color=viz.MUTED)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(args.out, dpi=300)
    plt.close(fig)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
