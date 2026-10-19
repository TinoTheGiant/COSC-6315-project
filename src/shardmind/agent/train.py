"""Train the DQN, and write down everything needed to believe the result.

    python scripts/train.py --timesteps 300000

Design notes, in the order they will matter to a reader of the paper:

**Seeds are stratified, not fixed.** Training resets onto a rotating set of
seeds rather than one, because a DQN trained on a single workload realization
learns that realization. Evaluation uses a disjoint block of seeds
(``DQNConfig.eval_seed_start``), so the curve in the paper is generalization and
not recall.

**Evaluation is greedy and runs through the same code as the baselines.** The
callback drives :class:`~shardmind.agent.policy.LearnedPolicy` over
``shardmind.policies.rollout``, exactly as ``scripts/run_experiment.py`` drives
the hand-written policies. There is no separate agent evaluation loop to drift
out of step with the baseline one.

**Nothing is saved without its configuration.** Every artefact directory holds
``agent_config.json`` and ``env_config.json`` next to the weights. A checkpoint
with no record of the reward function that produced it is not a result.
"""

from __future__ import annotations

import json
import platform
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from shardmind.agent.config import DQNConfig
from shardmind.config import ShardMindConfig
from shardmind.env import ShardMindEnv


class SeedRotatingEnv(ShardMindEnv):
    """A ShardMind environment that draws a fresh workload seed each episode.

    Stable-Baselines3 calls ``reset()`` with ``seed=None`` between episodes,
    which here would mean "keep whatever the simulator had". That trains the
    agent on one realization of the workload. Instead each reset takes the next
    seed from a fixed list, so one pass through training sees ``train_seeds``
    distinct workloads and the agent has to learn the structure rather than the
    sample.
    """

    def __init__(self, config: ShardMindConfig, seeds: list[int]) -> None:
        super().__init__(config)
        self._seeds = list(seeds)
        self._next = 0

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        if seed is None:
            seed = self._seeds[self._next % len(self._seeds)]
            self._next += 1
        return super().reset(seed=seed, options=options)


def evaluate_greedy(
    model, env_config: ShardMindConfig, seeds: list[int],
) -> dict[str, float]:
    """Score the greedy policy induced by ``model`` on held-out seeds.

    Runs through ``shardmind.policies.rollout``, the same function the baselines
    use, so the agent's number and the baselines' numbers are produced by one
    loop. Returns the quantities the paper reports.
    """
    from shardmind.observation import ObservationEncoder
    from shardmind.policies import rollout
    from shardmind.simulator import ClusterSimulator
    from shardmind.env import observe

    class _Greedy:
        def __init__(self, encoder: ObservationEncoder) -> None:
            self.encoder = encoder

        def act(self, sim: ClusterSimulator) -> int:
            action, _ = model.predict(observe(self.encoder, sim), deterministic=True)
            return int(action)

        def reset(self) -> None:
            return None

    latencies, tails, moved = [], [], []
    for seed in seeds:
        sim = ClusterSimulator(env_config)
        records = rollout(sim, _Greedy(ObservationEncoder(env_config, sim.topology)),
                          seed=seed)
        latencies.append(float(np.mean([r["mean_latency_ms"] for r in records])))
        tails.append(float(np.mean([r["tail_latency_ms"] for r in records])))
        moved.append(float(np.sum([r["bytes_moved"] for r in records])) / 1e9)
    return {
        "mean_latency_ms": float(np.mean(latencies)),
        "mean_tail_latency_ms": float(np.mean(tails)),
        "gb_moved": float(np.mean(moved)),
    }


def _make_eval_callback(agent_config: DQNConfig, env_config: ShardMindConfig,
                        outdir: Path, history: list[dict[str, Any]]):
    """A callback that scores the greedy policy periodically and keeps the best.

    Written against the SB3 callback API rather than ``EvalCallback`` because
    the quantity that decides "best" here is mean latency over held-out seeds,
    not episode return. Return and latency move together, but return also
    carries the migration and imbalance terms, and the model the paper should
    quote is the one that served requests fastest for a stated movement budget.
    """
    from stable_baselines3.common.callbacks import BaseCallback

    eval_seeds = list(range(agent_config.eval_seed_start,
                            agent_config.eval_seed_start + agent_config.eval_episodes))

    class _Eval(BaseCallback):
        def __init__(self) -> None:
            super().__init__(verbose=0)
            self.best = float("inf")

        def _on_step(self) -> bool:
            if self.num_timesteps % agent_config.eval_every_steps != 0:
                return True
            scores = evaluate_greedy(self.model, env_config, eval_seeds)
            row = {"timestep": int(self.num_timesteps), **scores}
            history.append(row)
            for key, value in scores.items():
                self.logger.record(f"eval/{key}", value)
            print(f"  [{self.num_timesteps:>8d}] "
                  f"latency {scores['mean_latency_ms']:7.2f} ms  "
                  f"moved {scores['gb_moved']:7.1f} GB", flush=True)
            if scores["mean_latency_ms"] < self.best:
                self.best = scores["mean_latency_ms"]
                self.model.save(str(outdir / "best_model"))
                (outdir / "best_model.json").write_text(
                    json.dumps(row, indent=2), encoding="utf-8")
            return True

    return _Eval()


def train(
    agent_config: DQNConfig | None = None,
    env_config: ShardMindConfig | None = None,
    outdir: Path | None = None,
    tensorboard: bool = True,
) -> Path:
    """Run one training job. Returns the directory holding its artefacts."""
    from stable_baselines3 import DQN

    agent_config = agent_config or DQNConfig()
    env_config = env_config or ShardMindConfig()

    started = datetime.now(timezone.utc)
    outdir = Path(outdir or Path("results/models") / f"{started:%Y%m%dT%H%M%SZ}")
    outdir.mkdir(parents=True, exist_ok=True)

    agent_config.save(outdir / "agent_config.json")
    env_config.save(outdir / "env_config.json")

    env = SeedRotatingEnv(env_config, list(range(agent_config.train_seeds)))
    model = DQN(
        "MlpPolicy", env,
        tensorboard_log=str(outdir / "tensorboard") if tensorboard else None,
        verbose=0,
        **agent_config.to_sb3_kwargs(),
    )

    print(f"training into {outdir}")
    print(f"  {agent_config.total_timesteps:,} steps, "
          f"{env.action_space.n} actions, "
          f"{env.observation_space.shape[0]} observation dimensions")
    print(f"  device {model.device}, net {list(agent_config.net_arch)}")

    history: list[dict[str, Any]] = []
    callback = _make_eval_callback(agent_config, env_config, outdir, history)

    t0 = time.perf_counter()
    model.learn(total_timesteps=agent_config.total_timesteps, callback=callback,
                progress_bar=False)
    elapsed = time.perf_counter() - t0

    model.save(str(outdir / "final_model"))
    (outdir / "eval_history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
    (outdir / "manifest.json").write_text(json.dumps({
        "started_utc": started.isoformat(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "wall_clock_seconds": round(elapsed, 1),
        "steps_per_second": round(agent_config.total_timesteps / max(elapsed, 1e-9), 1),
        "command": " ".join(sys.argv),
        "agent_config": agent_config.to_dict(),
        "env_config": env_config.to_dict(),
        "train_seeds": [0, agent_config.train_seeds],
        "eval_seeds": [agent_config.eval_seed_start,
                       agent_config.eval_seed_start + agent_config.eval_episodes],
        "device": str(model.device),
        "python": platform.python_version(),
        "platform": platform.platform(),
    }, indent=2), encoding="utf-8")

    print(f"  done in {elapsed / 60:.1f} min "
          f"({agent_config.total_timesteps / max(elapsed, 1e-9):.0f} steps/s)")
    if history:
        best = min(history, key=lambda r: r["mean_latency_ms"])
        print(f"  best held-out latency {best['mean_latency_ms']:.2f} ms "
              f"at step {best['timestep']:,}")
    return outdir
