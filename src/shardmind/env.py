"""The Gymnasium adapter.

This module is the only place where the model meets the RL interface. It owns
three translations and nothing else:

* cluster state to an observation vector, via :class:`~shardmind.observation.ObservationEncoder`;
* an integer to a placement action, via :class:`~shardmind.actions.ActionSpace`;
* a cost vector to a scalar reward.

The reward is the negative weighted sum of three normalized terms::

    r = -( w_latency   * mean_latency_ms / latency_scale_ms
         + w_migration * bytes_moved / (dataset_bytes * migration_scale_fraction)
         + w_imbalance * load_imbalance
         + inapplicable_action_cost  if the action changed nothing )

Sweeping ``w_migration`` traces the responsiveness against stability frontier of
Objective 5: at zero the agent is free to thrash, and high enough it learns to
sit still and behave like static hashing.

Episodes truncate at ``windows_per_episode`` and never terminate. The
distinction matters for bootstrapping: the value of the state at the horizon is
not zero, the episode simply stopped being observed, and Stable-Baselines3
handles ``truncated`` correctly only if it is reported separately.
"""

from __future__ import annotations

from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from shardmind.config import ShardMindConfig
from shardmind.observation import ObservationEncoder
from shardmind.simulator import ClusterSimulator

ENV_ID = "ShardMind-v0"


def observe(encoder: ObservationEncoder, sim: ClusterSimulator) -> np.ndarray:
    """Encode a simulator's current state as an observation vector.

    Lives here rather than on the simulator because the simulator knows nothing
    about reinforcement learning ([ADR-0005]). It is a module-level function
    rather than a method so that a trained policy can be evaluated outside a
    Gymnasium environment -- by ``shardmind.agent.policy.LearnedPolicy``, and so
    by ``scripts/run_experiment.py`` -- against exactly the same encoding the
    agent saw during training. One definition, or the agent is quietly scored on
    a different observation than it learned from.
    """
    result = sim.last
    return encoder.encode(
        catalog=sim.catalog,
        window=result.window,
        generator=sim.generator,
        cost=result.cost,
        churn_history=sim.churn_history,
        progress=sim.progress,
    )


class ShardMindEnv(gym.Env):
    """Continuous re-fragmentation and re-allocation as a Gymnasium environment."""

    metadata = {"render_modes": ["ansi", "human"], "render_fps": 4}

    def __init__(
        self,
        config: ShardMindConfig | None = None,
        render_mode: str | None = None,
    ) -> None:
        super().__init__()
        self.cfg = config or ShardMindConfig()
        self.sim = ClusterSimulator(self.cfg)
        self.encoder = ObservationEncoder(self.cfg, self.sim.topology)

        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(self.encoder.dim,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(self.sim.action_space.n)
        self.render_mode = render_mode

    # ------------------------------------------------------------------ core

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        result = self.sim.reset(seed=seed)
        return self._observe(), self._info(result, reward=0.0)

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        result = self.sim.step(int(action))
        reward = self._reward(result)
        return self._observe(), reward, False, bool(result.done), self._info(result, reward)

    def render(self) -> str | None:
        text = self._render_text()
        if self.render_mode == "human":
            print(text)
            return None
        return text

    # ------------------------------------------------------------- internals

    def _observe(self) -> np.ndarray:
        return observe(self.encoder, self.sim)

    def _reward(self, result) -> float:
        w = self.cfg.reward
        latency_term = result.cost.mean_latency_ms / w.latency_scale_ms
        # A fraction of the dataset, never a byte count. This is what makes a
        # Q-function pre-trained on the 60 GB simulator meaningful on a 1 GB
        # cluster: the same physical move scores the same in both. ADR-0010.
        migration_term = result.bytes_moved / (
            self.cfg.catalog.dataset_bytes * w.migration_scale_fraction)
        imbalance_term = result.cost.load_imbalance
        penalty = 0.0 if result.mutation.applied else w.inapplicable_action_cost
        return float(
            -(
                w.w_latency * latency_term
                + w.w_migration * migration_term
                + w.w_imbalance * imbalance_term
                + penalty
            )
        )

    def _info(self, result, reward: float) -> dict[str, Any]:
        info = self.sim.snapshot()
        info["reward"] = reward
        info["action_applied"] = result.mutation.applied
        info["action_reason"] = result.mutation.reason
        return info

    def _render_text(self) -> str:
        c = self.sim.last.cost
        return (
            f"window {self.sim.window_index:>4d}  "
            f"mean {c.mean_latency_ms:7.2f} ms  "
            f"p{self.cfg.cost.tail_percentile:.0f} {c.tail_latency_ms:7.2f} ms  "
            f"xregion-txn {c.cross_region_txn_fraction:5.1%}  "
            f"imbalance {c.load_imbalance:5.3f}  "
            f"fragments {self.sim.catalog.n_fragments:>2d}\n"
            + self.sim.catalog.summary()
        )


def register_env() -> None:
    """Register ``ShardMind-v0`` with Gymnasium, idempotently."""
    if ENV_ID in gym.registry:
        return
    gym.register(id=ENV_ID, entry_point="shardmind.env:ShardMindEnv")


register_env()
