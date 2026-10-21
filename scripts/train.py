#!/usr/bin/env python3
"""Train the DQN agent on the simulator.

    python scripts/train.py                          # defaults, 300k steps
    python scripts/train.py --timesteps 50000        # a short run, to check wiring
    python scripts/train.py --agent-config a.json --config env.json

Writes one directory under ``results/models/`` holding the weights, both
configurations, the evaluation history and a manifest. Evaluate the result
against the baselines with::

    python scripts/run_experiment.py --policies static follow best agent \\
        --model results/models/<id>/best_model.zip
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fragalloc.agent.config import DQNConfig  # noqa: E402
from fragalloc.agent.train import train  # noqa: E402
from fragalloc.config import FragAllocConfig  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=None,
                        help="environment config JSON. Defaults to FragAllocConfig().")
    parser.add_argument("--agent-config", type=Path, default=None,
                        help="hyperparameter JSON. Defaults to DQNConfig().")
    parser.add_argument("--timesteps", type=int, default=None,
                        help="override total_timesteps")
    parser.add_argument("--windows", type=int, default=None,
                        help="override windows per episode")
    parser.add_argument("--volatility", type=float, default=None)
    parser.add_argument("--w-migration", type=float, default=None,
                        help="reward weight on migration. This is the knob the "
                             "stability frontier is swept over, and it only means "
                             "anything here: the baselines never read the reward")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--outdir", type=Path, default=None)
    parser.add_argument("--no-tensorboard", action="store_true")
    args = parser.parse_args()

    env_cfg = FragAllocConfig.load(args.config) if args.config else FragAllocConfig()
    if args.windows is not None:
        env_cfg = env_cfg.evolve(episode=replace(env_cfg.episode,
                                                 windows_per_episode=args.windows))
    if args.volatility is not None:
        env_cfg = env_cfg.evolve(workload=replace(env_cfg.workload,
                                                  volatility=args.volatility))
    if args.w_migration is not None:
        env_cfg = env_cfg.evolve(reward=replace(env_cfg.reward,
                                                w_migration=args.w_migration))

    agent_cfg = DQNConfig.load(args.agent_config) if args.agent_config else DQNConfig()
    changes = {}
    if args.timesteps is not None:
        changes["total_timesteps"] = args.timesteps
        # learning_starts must stay below the budget, which a short wiring
        # check would otherwise violate.
        changes["learning_starts"] = min(agent_cfg.learning_starts, max(1, args.timesteps // 10))
        changes["eval_every_steps"] = min(agent_cfg.eval_every_steps,
                                          max(1, args.timesteps // 5))
    if args.seed is not None:
        changes["seed"] = args.seed
    if changes:
        agent_cfg = replace(agent_cfg, **changes)

    outdir = train(agent_cfg, env_cfg, args.outdir, tensorboard=not args.no_tensorboard)
    print(f"\nartefacts in {outdir}")


if __name__ == "__main__":
    main()
