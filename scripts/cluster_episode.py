"""Run one policy for one episode on the cluster (harness piece 4).

The same policies as the simulator's evaluation, on CockroachDB: static
(never acts), random (uniform over the legal actions), follow (the
traffic-following heuristic, unchanged), or agent (a saved model, loaded with
the simulator's own spaces and selection rule). One row per step: the action,
the executor's outcome, measured latency, data moved, imbalance, reward, and
how long the step took, which is what decides whether 200-window episodes fit
between classes.

Usage:
    python scripts/cluster_episode.py --policy static --windows 5 --transactions 200
    python scripts/cluster_episode.py --policy agent --model results/models/X/best_model.zip
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fragalloc.config import FragAllocConfig                     # noqa: E402
from fragalloc.harness.driver import port_connector               # noqa: E402
from fragalloc.harness.env import ClusterFragAllocEnv             # noqa: E402
from fragalloc.harness.placement import PsycopgSql, resolve_stores  # noqa: E402
from fragalloc.policies import FollowTrafficPolicy                # noqa: E402


def chooser(name: str, env: ClusterFragAllocEnv, model_path: str | None, seed: int):
    space = env.space
    if name == "static":
        return lambda obs: space.noop_index
    if name == "random":
        rng = np.random.default_rng(seed)
        return lambda obs: int(rng.choice(np.flatnonzero(env.action_masks())))
    if name == "follow":
        follow = FollowTrafficPolicy(space)
        # The heuristic reads catalogue, RTT and the current window; give it the
        # cluster's, through the attributes it reads on the simulator.
        return lambda obs: follow.act(SimpleNamespace(
            catalog=env.catalog, topology=env.topology,
            last=SimpleNamespace(window=env._window)))
    if name == "agent":
        from fragalloc.agent.masked_dqn import MaskedDQN, resolve_eval_mode, select_action
        if not model_path:
            raise SystemExit("--policy agent needs --model")
        model = MaskedDQN.load(model_path, device="cpu")
        if model.observation_space != env.observation_space or \
                model.action_space != env.action_space:
            raise SystemExit("model spaces differ from the cluster's (ADR-0009 parity)")
        mode = resolve_eval_mode(model, "auto")
        return lambda obs: select_action(model, obs, env.action_masks(), space.noop_index, mode)
    raise SystemExit(f"unknown policy {name}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", choices=("static", "random", "follow", "agent"), default="static")
    ap.add_argument("--model", default=None)
    ap.add_argument("--seed", type=int, default=2000, help="workload seed (held-out range)")
    ap.add_argument("--windows", type=int, default=5)
    ap.add_argument("--transactions", type=int, default=200, help="N per step (measure_n.py)")
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--replicas", type=int, default=None)
    ap.add_argument("--read-consistency", choices=("primary_only", "nearest_replica"),
                    default=None)
    ap.add_argument("--volatility", type=float, default=None)
    ap.add_argument("--port", type=int, default=26257)
    ap.add_argument("--out", default="results/cluster_episode.csv")
    args = ap.parse_args()

    cfg = FragAllocConfig()
    cfg = cfg.evolve(episode=replace(cfg.episode, windows_per_episode=args.windows))
    if args.replicas and args.replicas != cfg.catalog.min_replicas:
        cfg = cfg.evolve(catalog=replace(cfg.catalog, min_replicas=args.replicas,
                                         max_replicas=args.replicas))
    if args.read_consistency:
        cfg = cfg.evolve(cost=replace(cfg.cost, read_consistency=args.read_consistency))
    if args.volatility is not None:
        cfg = cfg.evolve(workload=replace(cfg.workload, volatility=args.volatility))

    sql = PsycopgSql.connect(port=args.port)
    stores = resolve_stores(sql, cfg.topology.region_names)
    env = ClusterFragAllocEnv(cfg, sql, stores, port_connector(args.port),
                              n_transactions=args.transactions, concurrency=args.concurrency)
    choose = chooser(args.policy, env, args.model, args.seed)

    t0 = time.monotonic()
    obs, info = env.reset(seed=args.seed)
    print(f"reset in {time.monotonic() - t0:.0f} s; {args.policy}, seed {args.seed}, "
          f"N={args.transactions}, reads {env.read_mode}")
    rows = []
    try:
        for i in range(args.windows):
            a = choose(obs)
            t = time.monotonic()
            obs, r, _, trunc, info = env.step(a)
            row = {"step": i, "window": info["window"], "action": env.space.describe(a),
                   "outcome": info["outcome"], "mean_ms": info["mean_latency_ms"],
                   "p95_ms": info["tail_latency_ms"], "gb_moved": info["bytes_moved"] / 1e9,
                   "imbalance": info["load_imbalance"], "reward": r,
                   "executor_s": info["step_seconds"], "drive_s": info["drive"]["wall_s"],
                   "step_s": time.monotonic() - t, "retries": info["drive"]["retries"],
                   "failures": info["drive"]["failures"], "suspect": info["suspect"],
                   "divergences": len(info["divergences"])}
            rows.append(row)
            print(f"  {i:>3} {row['action']:<28} {row['outcome']:<9} mean {row['mean_ms']:7.1f} "
                  f"p95 {row['p95_ms']:7.1f} ms  reward {r:7.3f}  step {row['step_s']:5.1f} s"
                  + ("  SUSPECT" if row["suspect"] else ""))
            if trunc:
                break
    finally:
        env.close()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    summary = {
        "policy": args.policy, "seed": args.seed, "steps": len(rows),
        "mean_latency_ms": statistics.fmean(r["mean_ms"] for r in rows),
        "gb_moved_total": sum(r["gb_moved"] for r in rows),
        "mean_step_s": statistics.fmean(r["step_s"] for r in rows),
        "suspect_steps": sum(r["suspect"] for r in rows),
        "divergent_steps": sum(r["divergences"] > 0 for r in rows),
    }
    Path(args.out).with_suffix(".json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    ok = summary["suspect_steps"] == 0 and summary["divergent_steps"] == 0
    print("VERDICT:", "PASS, the cluster ran as an environment end to end."
          if ok else "CHECK, suspect or divergent steps above.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
