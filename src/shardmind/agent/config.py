"""Hyperparameters for the DQN, as a frozen dataclass.

Separate from :class:`~shardmind.config.ShardMindConfig` on purpose. That one
describes the *environment*: a question about the world. This one describes the
*learner*: a question about how we attack it. Keeping them apart means a sweep
over environments and a sweep over learners are different experiments, and a
reader of ``manifest.json`` can tell at a glance which one changed.

Defaults are chosen for the shape of this problem rather than copied from an
Atari configuration, and each is justified where it departs from the
Stable-Baselines3 default.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DQNConfig:
    """Everything the learner needs, and nothing about the environment."""

    #: Gradient steps are cheap here and the simulator is not, so the default
    #: budget is large enough to converge and small enough to finish inside a
    #: GitHub Actions job.
    total_timesteps: int = 300_000

    #: A 261-action space with a 703-element observation. Two hidden layers of
    #: 256 is the smallest network that can represent a per-fragment decision
    #: without bottlenecking; it is also small enough to train on CPU, which is
    #: what the runners provide.
    net_arch: tuple[int, ...] = (256, 256)

    learning_rate: float = 1e-4
    #: One episode is 200 windows, so this holds roughly 500 episodes. Large
    #: enough that the replay buffer spans several diurnal cycles, which is the
    #: timescale the agent has to learn to anticipate.
    buffer_size: int = 100_000
    batch_size: int = 128
    #: Transitions collected before the first gradient step. One buffer-tenth,
    #: so the first updates are not drawn from a near-empty buffer.
    learning_starts: int = 10_000
    #: Discount. A diurnal cycle is 96 windows; 0.99 gives an effective horizon
    #: of about 100 windows, which is the right order to see a full rotation.
    gamma: float = 0.99
    #: One gradient step per environment step. Raising it trades wall clock for
    #: sample efficiency, which is the wrong trade when the simulator is fast.
    train_freq: int = 1
    gradient_steps: int = 1
    #: Hard target update, in environment steps.
    target_update_interval: int = 2_000

    #: Exploration. The action space is large and most actions are locally
    #: useless, so exploration is annealed slowly and never quite to zero.
    exploration_fraction: float = 0.30
    exploration_initial_eps: float = 1.0
    exploration_final_eps: float = 0.05

    #: Gradient clipping. Reward is bounded but its migration term is spiky.
    max_grad_norm: float = 10.0

    #: Evaluation during training, on seeds disjoint from the training seeds.
    eval_every_steps: int = 10_000
    eval_episodes: int = 3
    #: Training uses seeds [0, train_seeds); evaluation uses
    #: [eval_seed_start, eval_seed_start + eval_episodes). They must not
    #: overlap, or the reported curve is a training curve wearing a disguise.
    train_seeds: int = 64
    eval_seed_start: int = 1_000

    seed: int = 0
    device: str = "auto"

    def __post_init__(self) -> None:
        if self.eval_seed_start < self.train_seeds:
            raise ValueError(
                "eval seeds must not overlap training seeds: "
                f"eval_seed_start={self.eval_seed_start} < train_seeds={self.train_seeds}")
        if not 0.0 <= self.exploration_final_eps <= self.exploration_initial_eps <= 1.0:
            raise ValueError("require 0 <= final_eps <= initial_eps <= 1")
        if self.learning_starts >= self.total_timesteps:
            raise ValueError("learning_starts must be smaller than total_timesteps")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DQNConfig":
        data = dict(data)
        if "net_arch" in data:
            data["net_arch"] = tuple(data["net_arch"])
        return cls(**data)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "DQNConfig":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_sb3_kwargs(self) -> dict[str, Any]:
        """The subset Stable-Baselines3's ``DQN`` constructor takes."""
        return {
            "learning_rate": self.learning_rate,
            "buffer_size": self.buffer_size,
            "learning_starts": self.learning_starts,
            "batch_size": self.batch_size,
            "gamma": self.gamma,
            "train_freq": self.train_freq,
            "gradient_steps": self.gradient_steps,
            "target_update_interval": self.target_update_interval,
            "exploration_fraction": self.exploration_fraction,
            "exploration_initial_eps": self.exploration_initial_eps,
            "exploration_final_eps": self.exploration_final_eps,
            "max_grad_norm": self.max_grad_norm,
            "policy_kwargs": {"net_arch": list(self.net_arch)},
            "seed": self.seed,
            "device": self.device,
        }
