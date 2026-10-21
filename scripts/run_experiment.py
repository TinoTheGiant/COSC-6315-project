#!/usr/bin/env python3
"""Run a reproducible experiment and record everything needed to repeat it.

This is the only script that should ever produce a number that reaches the
paper. Everything else is for looking at things interactively.

    python scripts/run_experiment.py --seeds 8 --windows 200
    python scripts/run_experiment.py --config results/runs/<id>/config.json --seeds 8

One invocation is one *run*. A run writes a single directory under
``results/runs/`` containing:

    manifest.json   who, what, when, which commit, which package versions
    config.json     the fully resolved FragAllocConfig, reloadable as-is
    steps.csv       one row per (policy, seed, window). The raw record.
    summary.csv     one row per (policy, seed). The unit of statistics.
    report.md       the aggregated table, with bootstrap intervals
    figures/        PNGs, if --figures is passed

Every row in every CSV carries ``run_id``, ``policy`` and ``seed``, so two runs
can be concatenated without ambiguity and no number is ever orphaned from the
configuration that produced it. That is the whole point: the methods section is
then a transcription of manifest.json rather than an act of memory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fragalloc.actions import ActionKind, ActionSpace  # noqa: E402
from fragalloc.config import FragAllocConfig  # noqa: E402
from fragalloc.cost import evaluate  # noqa: E402
from fragalloc.policies import (  # noqa: E402
    FollowTrafficPolicy,
    RandomPolicy,
    StaticHashPolicy,
)
from fragalloc.simulator import ClusterSimulator  # noqa: E402

#: Policies the runner knows how to build. ``best`` is not a policy; it is the
#: per-window lower bound on latency, computed by relocating every primary for
#: free. It is reported as a reference line, never as a competitor.
POLICY_FACTORIES = {
    "static": lambda space, seed: StaticHashPolicy(space),
    "random": lambda space, seed: RandomPolicy(space, seed=seed),
    "follow": lambda space, seed: FollowTrafficPolicy(space),
    "best": None,
    # ``agent`` is filled in at startup from --model. It is listed here so the
    # argument parser accepts it and so the trained policy is driven by exactly
    # the same episode loop as the baselines. Two loops would mean any
    # discrepancy between them showed up as, and was indistinguishable from,
    # learning.
    "agent": None,
}
DEFAULT_POLICIES = ("static", "random", "follow", "best")
#: Reported, but not an achievable policy. Kept out of any "which won" claim.
REFERENCE_POLICIES = ("best",)


# ----------------------------------------------------------------- provenance

def git_state() -> dict[str, str]:
    """The commit the code was at, and whether the tree was dirty.

    A dirty tree is recorded rather than refused. Refusing would push people to
    commit noise just to run something; recording means a reader can see that a
    number came from an uncommitted edit and discount it accordingly.
    """
    def run(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", *args], capture_output=True, text=True, timeout=15,
                cwd=Path(__file__).resolve().parent.parent,
            ).stdout.strip()
        except Exception:
            return ""

    status = run("status", "--porcelain")
    return {
        "commit": run("rev-parse", "HEAD") or "unknown",
        "branch": run("rev-parse", "--abbrev-ref", "HEAD") or "unknown",
        "dirty": "yes" if status else "no",
        "dirty_files": status.splitlines()[:20],
    }


def package_versions() -> dict[str, str]:
    names = ["numpy", "pandas", "matplotlib", "gymnasium", "stable_baselines3", "torch"]
    out = {}
    for name in names:
        try:
            module = __import__(name)
            out[name] = getattr(module, "__version__", "unknown")
        except Exception:
            out[name] = "absent"
    return out


def config_digest(cfg: FragAllocConfig) -> str:
    """A short, stable fingerprint of the configuration.

    Two runs with the same digest used the same environment. Printed in the
    run id so that a directory listing shows at a glance which runs are
    comparable.
    """
    blob = json.dumps(cfg.to_dict(), sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:8]


# -------------------------------------------------------------------- the run

def run_episode(cfg: FragAllocConfig, policy_key: str, seed: int) -> pd.DataFrame:
    """One seeded episode under one policy, as one row per window."""
    space = ActionSpace(cfg.catalog.max_fragments, cfg.n_regions)
    factory = POLICY_FACTORIES[policy_key]
    policy = factory(space, seed) if factory else None

    sim = ClusterSimulator(cfg)
    sim.reset(seed=seed)
    if policy is not None:
        policy.reset()

    rows = []
    cumulative_bytes = 0.0
    # What the policy actually did, not merely what it achieved. Without this
    # a weak result is indistinguishable between "it never moved anything",
    # "it moved constantly and badly" and "it spent the episode splitting",
    # which are three different diagnoses with three different fixes.
    # The first row is the state before any action, so its action columns are
    # empty rather than NOOP. Counting that row as a deliberate no-op would
    # inflate every policy's idleness by one window.
    action_taken = -1
    action_kind_name = ""
    action_applied = True
    for window_index in range(cfg.episode.windows_per_episode + 1):
        window = sim.last.window
        if policy_key == "best":
            # Free, instantaneous relocation of every primary, at the shard
            # boundaries this episode started with. Unreachable by two
            # constructions: it pays no migration cost, and it sees the window
            # it is optimizing for. It is NOT a global optimum, because it
            # never splits a shard. A policy that splits can legitimately beat
            # it, and the figure label says "fixed shards" for that reason.
            catalog = sim.catalog.copy()
            demand = catalog.aggregate_cells(window.reads + window.writes)
            target = (demand @ sim.topology.rtt).argmin(axis=1)
            for fragment in range(catalog.n_fragments):
                catalog.set_primary(fragment, int(target[fragment]))
            cost = evaluate(catalog, window, sim.generator, sim.topology, cfg.cost)
        else:
            cost = sim.last.cost

        rows.append({
            "policy": policy_key,
            "seed": seed,
            "window": window_index,
            "phase": window_index % cfg.workload.diurnal_period_windows,
            "mean_latency_ms": cost.mean_latency_ms,
            "tail_latency_ms": cost.tail_latency_ms,
            "mean_read_latency_ms": cost.mean_read_latency_ms,
            "mean_write_latency_ms": cost.mean_write_latency_ms,
            "mean_txn_latency_ms": cost.mean_txn_latency_ms,
            "cross_region_txn_fraction": cost.cross_region_txn_fraction,
            "load_imbalance": cost.load_imbalance,
            "storage_imbalance": cost.storage_imbalance,
            "n_fragments": float(sim.catalog.n_fragments),
            "gb_moved": sim.last.bytes_moved / 1e9,
            "cum_gb_moved": cumulative_bytes,
            # The action that PRODUCED this row's state, so a row reads as
            # "this is what the cluster looked like after doing that".
            "action": action_taken,
            "action_kind": action_kind_name,
            "action_applied": bool(action_applied),
        })

        if sim.last.done:
            break
        action_taken = policy.act(sim) if policy is not None else space.noop_index
        action_kind_name = space.decode(action_taken).kind.name
        result = sim.step(action_taken)
        action_applied = bool(result.mutation.applied)
        cumulative_bytes += sim.last.bytes_moved / 1e9

    return pd.DataFrame(rows)


def summarize(steps: pd.DataFrame, tail_percentile: float) -> pd.DataFrame:
    """Collapse each (policy, seed) episode to the numbers the paper quotes."""
    rows = []
    for (policy, seed), group in steps.groupby(["policy", "seed"], sort=True):
        acted = group[group["action_kind"] != ""] if "action_kind" in group else group.iloc[0:0]
        attempted = acted[acted["action_kind"] != ActionKind.NOOP.name]
        rows.append({
            "policy": policy,
            "seed": int(seed),
            "windows": int(len(group)),
            "mean_latency_ms": float(group["mean_latency_ms"].mean()),
            f"p{tail_percentile:g}_latency_ms": float(
                np.percentile(group["mean_latency_ms"], tail_percentile)),
            "mean_tail_latency_ms": float(group["tail_latency_ms"].mean()),
            "cross_region_txn_fraction": float(group["cross_region_txn_fraction"].mean()),
            "load_imbalance": float(group["load_imbalance"].mean()),
            "gb_moved_total": float(group["gb_moved"].sum()),
            "final_fragments": float(group["n_fragments"].iloc[-1]),
            # The share of windows spent on each kind of action, and the share
            # of them that were inapplicable in the state they met. A policy
            # that is 95 percent NOOP has not learned a cautious strategy, it
            # has learned to do nothing.
            #
            # NOOP is excluded from the inapplicable rate. Choosing to do
            # nothing is a decision, not a failed action, and counting it as
            # one would report every idle policy as maximally incompetent.
            **{f"frac_{kind.name.lower()}": float(
                (acted["action_kind"] == kind.name).mean()) if len(acted) else 0.0
               for kind in ActionKind},
            "frac_inapplicable": float(
                1.0 - attempted["action_applied"].mean()) if len(attempted) else 0.0,
        })
    return pd.DataFrame(rows)


def bootstrap_ci(values: np.ndarray, reps: int = 10_000, alpha: float = 0.05,
                 seed: int = 12345) -> tuple[float, float]:
    """Percentile bootstrap interval for the mean.

    Used rather than a t interval because the seed counts here are small and
    nothing guarantees the per-seed means are normal.
    """
    values = np.asarray(values, dtype=float)
    if len(values) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    draws = rng.choice(values, size=(reps, len(values)), replace=True).mean(axis=1)
    return (float(np.percentile(draws, 100 * alpha / 2)),
            float(np.percentile(draws, 100 * (1 - alpha / 2))))


def report(summary: pd.DataFrame, manifest: dict, tail_percentile: float) -> str:
    """The aggregated table, written so it can be pasted into the paper."""
    lines = [
        f"# Run `{manifest['run_id']}`",
        "",
        f"- **When** {manifest['started_utc']}",
        f"- **Commit** `{manifest['git']['commit'][:10]}` on `{manifest['git']['branch']}`"
        f" (working tree dirty: {manifest['git']['dirty']})",
        f"- **Config digest** `{manifest['config_digest']}`",
        f"- **Seeds** {manifest['seeds']}",
        f"- **Windows per episode** {manifest['windows_per_episode']},"
        f" volatility {manifest['volatility']}",
        f"- **Machine** {manifest['machine']['platform']},"
        f" python {manifest['machine']['python']}",
        "",
        "## Aggregate over seeds",
        "",
        "Mean of the per-seed episode means, with a 95% percentile bootstrap",
        "interval over seeds. `best` is the lowest latency reachable by moving",
        "every lease for free each window at the starting shard boundaries. It",
        "is not an achievable policy, and it is not a global optimum either: a",
        "policy that splits a shard can sit below it.",
        "",
        f"| Policy | Mean latency (ms) | 95% CI | p{tail_percentile:g} (ms) |"
        " GB moved | Cross-region txns |",
        "|---|---|---|---|---|---|",
    ]
    present = set(summary["policy"])
    order = [p for p in ("agent", *DEFAULT_POLICIES) if p in present]
    label = {"static": "Static hash", "random": "Random", "follow": "Follow traffic",
             "best": "Best per window (fixed shards)", "agent": "Learned policy"}
    tail_col = f"p{tail_percentile:g}_latency_ms"
    for policy in order:
        group = summary[summary.policy == policy]
        mean = group["mean_latency_ms"].mean()
        low, high = bootstrap_ci(group["mean_latency_ms"].to_numpy())
        lines.append(
            f"| {label.get(policy, policy)} | {mean:.2f} |"
            f" [{low:.2f}, {high:.2f}] | {group[tail_col].mean():.2f} |"
            f" {group['gb_moved_total'].mean():.1f} |"
            f" {group['cross_region_txn_fraction'].mean() * 100:.1f}% |")

    if {"static", "follow"} <= set(summary["policy"]):
        static = summary[summary.policy == "static"]["mean_latency_ms"].mean()
        follow = summary[summary.policy == "follow"]["mean_latency_ms"].mean()
        lines += [
            "",
            f"Follow traffic improves on static hash by "
            f"**{(static - follow) / static * 100:.1f}%** of mean latency.",
        ]
    if {"follow", "best"} <= set(summary["policy"]):
        follow = summary[summary.policy == "follow"]["mean_latency_ms"].mean()
        best = summary[summary.policy == "best"]["mean_latency_ms"].mean()
        lines += [
            f"Headroom between follow traffic and the fixed-shard bound: "
            f"**{follow - best:.2f} ms** ({(follow - best) / follow * 100:.1f}% of "
            f"follow traffic). A small number here means the reactive heuristic is "
            f"already close to the best that lease movement alone can do, and that "
            f"what is left for a learned policy is movement cost rather than latency.",
        ]

    # What each policy did with its turns. This is the table that turns "the
    # agent was weak" into a diagnosis.
    if "frac_noop" in summary.columns:
        lines += [
            "",
            "## What each policy did with its windows",
            "",
            "Share of decision windows spent on each kind of action, and the share",
            "of chosen actions that were inapplicable in the state they met. An",
            "inapplicable action costs a small penalty and changes nothing.",
            "",
            "| Policy | Move lease | Move replica | Split | Nothing | Inapplicable |",
            "|---|---|---|---|---|---|",
        ]
        for policy in order:
            group = summary[summary.policy == policy]
            lines.append(
                f"| {label.get(policy, policy)} |"
                f" {group['frac_move_lease'].mean() * 100:.1f}% |"
                f" {group['frac_move_replica_to'].mean() * 100:.1f}% |"
                f" {group['frac_split'].mean() * 100:.1f}% |"
                f" {group['frac_noop'].mean() * 100:.1f}% |"
                f" {group['frac_inapplicable'].mean() * 100:.1f}% |")

    lines += [
        "",
        "## Reproducing this run",
        "",
        "```",
        f"git checkout {manifest['git']['commit'][:10]}",
        f"python scripts/run_experiment.py --config results/runs/{manifest['run_id']}/config.json \\",
        f"    --seeds {len(manifest['seeds'])} --seed-start {manifest['seeds'][0]}"
        + (f" \\\n    --model {manifest['agent']['model_path']}"
           if manifest.get("agent") else ""),
        "```",
        "",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------- plumbing

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=None,
                        help="JSON config to start from. Defaults to FragAllocConfig().")
    parser.add_argument("--seeds", type=int, default=5, help="how many seeds to run")
    parser.add_argument("--seed-start", type=int, default=0, help="first seed")
    parser.add_argument("--windows", type=int, default=None,
                        help="override windows per episode")
    parser.add_argument("--volatility", type=float, default=None,
                        help="override workload volatility")
    parser.add_argument("--w-migration", type=float, default=None,
                        help="override the reward's migration weight. Sweeping this "
                             "traces the responsiveness against stability frontier: "
                             "at zero the agent may thrash, high enough it sits still")
    parser.add_argument("--policies", nargs="+", default=list(DEFAULT_POLICIES),
                        choices=list(POLICY_FACTORIES))
    parser.add_argument("--model", type=Path, default=None,
                        help="a trained model (.zip) to evaluate as the 'agent' policy")
    parser.add_argument("--stochastic", action="store_true",
                        help="sample from the learned policy instead of acting greedily")
    parser.add_argument("--label", default="", help="short tag folded into the run id")
    parser.add_argument("--outdir", type=Path, default=Path("results/runs"))
    parser.add_argument("--figures", action="store_true",
                        help="also render the analysis page into figures/")
    args = parser.parse_args()

    if "agent" in args.policies and args.model is None:
        parser.error("--policies agent requires --model")
    if args.model is not None and "agent" not in args.policies:
        args.policies = list(args.policies) + ["agent"]

    cfg = FragAllocConfig.load(args.config) if args.config else FragAllocConfig()
    if args.windows is not None:
        cfg = cfg.evolve(episode=replace(cfg.episode, windows_per_episode=args.windows))
    if args.volatility is not None:
        cfg = cfg.evolve(workload=replace(cfg.workload, volatility=args.volatility))
    if args.w_migration is not None:
        cfg = cfg.evolve(reward=replace(cfg.reward, w_migration=args.w_migration))

    seeds = list(range(args.seed_start, args.seed_start + args.seeds))
    started = datetime.now(timezone.utc)
    digest = config_digest(cfg)
    tag = f"-{args.label}" if args.label else ""
    run_id = f"{started:%Y%m%dT%H%M%SZ}-{digest}{tag}"

    out = args.outdir / run_id
    out.mkdir(parents=True, exist_ok=True)

    agent_record: dict | None = None
    if args.model is not None:
        from fragalloc.agent.policy import LearnedPolicy

        learned = LearnedPolicy(args.model, cfg, deterministic=not args.stochastic)
        POLICY_FACTORIES["agent"] = lambda space, seed: learned
        model_dir = Path(args.model).resolve().parent
        train_manifest = model_dir / "manifest.json"
        agent_record = {
            "model_path": str(Path(args.model).resolve()),
            "model_sha256": hashlib.sha256(
                Path(args.model).read_bytes()).hexdigest()[:16],
            **learned.metadata,
            # The environment the weights were trained against, so a reader can
            # see whether the agent is being evaluated on the environment it
            # learned or transferred to a different one.
            "training_manifest": (
                json.loads(train_manifest.read_text(encoding="utf-8"))
                if train_manifest.exists() else None),
        }

    manifest = {
        "run_id": run_id,
        "started_utc": started.isoformat(),
        "command": " ".join(sys.argv),
        "git": git_state(),
        "config_digest": digest,
        "config": cfg.to_dict(),
        "seeds": seeds,
        "policies": list(args.policies),
        "windows_per_episode": cfg.episode.windows_per_episode,
        "volatility": cfg.workload.volatility,
        "w_migration": cfg.reward.w_migration,
        "agent": agent_record,
        "packages": package_versions(),
        "machine": {
            "platform": platform.platform(),
            "processor": platform.processor() or "unknown",
            "cpu_count": os.cpu_count(),
            "python": platform.python_version(),
            "ci": os.environ.get("GITHUB_ACTIONS", "no"),
            "runner": os.environ.get("RUNNER_NAME", ""),
            "workflow_run": os.environ.get("GITHUB_RUN_ID", ""),
        },
    }

    print(f"run {run_id}")
    print(f"  {len(args.policies)} policies x {len(seeds)} seeds "
          f"x {cfg.episode.windows_per_episode} windows")

    frames = []
    for policy in args.policies:
        for seed in seeds:
            frames.append(run_episode(cfg, policy, seed))
            print(f"  {policy:<8s} seed {seed:<3d} done", flush=True)

    steps = pd.concat(frames, ignore_index=True)
    steps.insert(0, "run_id", run_id)
    summary = summarize(steps, cfg.cost.tail_percentile)
    summary.insert(0, "run_id", run_id)

    finished = datetime.now(timezone.utc)
    manifest["finished_utc"] = finished.isoformat()
    manifest["duration_seconds"] = round((finished - started).total_seconds(), 1)

    cfg.save(out / "config.json")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    steps.to_csv(out / "steps.csv", index=False)
    summary.to_csv(out / "summary.csv", index=False)
    text = report(summary, manifest, cfg.cost.tail_percentile)
    (out / "report.md").write_text(text, encoding="utf-8")

    if args.figures:
        figures = out / "figures"
        figures.mkdir(exist_ok=True)
        try:
            import matplotlib
            matplotlib.use("Agg")
            from fragalloc import viz  # noqa: F401
            _draw_figures(steps, summary, cfg, figures)
        except Exception as exc:  # pragma: no cover - plotting is not the result
            print(f"  figures skipped: {exc}")

    print()
    print(text)
    print(f"written to {out}")


def _draw_figures(steps: pd.DataFrame, summary: pd.DataFrame,
                  cfg: FragAllocConfig, outdir: Path) -> None:
    """Three figures that belong to the run, drawn in the project's style."""
    import matplotlib.pyplot as plt

    from fragalloc import viz

    viz.use_paper_style()
    series = [p for p in viz.SERIES_POLICIES if p in set(steps["policy"])]
    reference = [p for p in viz.REFERENCE_POLICIES if p in set(steps["policy"])]

    # 1. Latency over the episode, averaged across seeds.
    fig, ax = plt.subplots(figsize=viz.FIG_1COL)
    for key in series:
        group = steps[steps.policy == key].groupby("window")["mean_latency_ms"].mean()
        ax.plot(group.index, group.values, **viz.policy_kwargs(key))
    for key in reference:
        level = steps[steps.policy == key]["mean_latency_ms"].mean()
        viz.policy_reference(ax, key, level)
    ax.set_xlabel("decision window")
    ax.set_ylabel("mean latency (ms)")
    ax.legend(frameon=False, fontsize=7)
    fig.tight_layout()
    fig.savefig(outdir / "latency_over_episode.png", dpi=300)
    plt.close(fig)

    # 2. Distribution of per-window latency.
    fig, ax = plt.subplots(figsize=viz.FIG_1COL)
    for key in series:
        values = steps[steps.policy == key]["mean_latency_ms"].to_numpy()
        ax.hist(values, bins=40, histtype="step", density=True,
                color=viz.POLICY[key]["color"], linestyle=viz.POLICY[key]["dash"],
                linewidth=viz.POLICY[key]["lw"], label=viz.POLICY[key]["label"])
    ax.set_xlabel("mean latency in a window (ms)")
    ax.set_ylabel("density")
    ax.legend(frameon=False, fontsize=7)
    fig.tight_layout()
    fig.savefig(outdir / "latency_distribution.png", dpi=300)
    plt.close(fig)

    # 3. What each policy paid in bandwidth for what it saved in latency.
    fig, ax = plt.subplots(figsize=viz.FIG_1COL)
    for key in series:
        group = summary[summary.policy == key]
        ax.scatter(group["gb_moved_total"], group["mean_latency_ms"],
                   color=viz.POLICY[key]["color"], s=26,
                   label=viz.POLICY[key]["label"], zorder=viz.POLICY[key]["z"])
    ax.set_xlabel("GB moved over the episode")
    ax.set_ylabel("mean latency (ms)")
    ax.legend(frameon=False, fontsize=7)
    fig.tight_layout()
    fig.savefig(outdir / "cost_of_movement.png", dpi=300)
    plt.close(fig)


if __name__ == "__main__":
    main()
