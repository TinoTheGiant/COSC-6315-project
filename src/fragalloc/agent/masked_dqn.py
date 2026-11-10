"""DQN that only ever chooses an applicable action.

Measured before this change: 79.9 to 89.8% of the agent's chosen actions were
inapplicable, against 80.4% for a uniformly random policy. The fixed
``inapplicable_action_cost`` was not teaching the agent to avoid them fast
enough, so every such step was a wasted decision and a wasted transition.

Masking is applied in the two places an action is chosen:

* **greedy choice**: Q-values of inapplicable actions are set to minus
  infinity before the argmax;
* **exploration**: the epsilon branch, and the warm-up before
  ``learning_starts``, sample uniformly from applicable actions only.

Not yet masked: **the bootstrap target**. SB3's ``train`` takes
``max_a' Q_target(s', a')`` over all 261 actions, and the replay buffer does not
store the next state's mask. Actions the masked agent never takes are never
updated, so their Q-values can drift upward and leak into that max. This is the
known bias of masking only at selection time (Huang and Ontanon, 2022). The fix
is to store the next-state mask with each transition and mask the max; it is
recorded in docs/tech-debt.md and should land before the next training run is
reported.

Masks come from the environment's ``action_masks()`` during training and are
passed explicitly as ``action_masks=`` at evaluation, where the caller holds a
simulator rather than an environment. Without ``action_masks`` the class
behaves exactly as ``stable_baselines3.DQN``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import torch as th
from stable_baselines3 import DQN


class MaskedDQN(DQN):
    """``stable_baselines3.DQN`` with action masking at selection time."""

    def _env_masks(self) -> np.ndarray:
        """One mask row per vectorized environment, shape ``(n_envs, n_actions)``."""
        return np.stack(self.env.env_method("action_masks")).astype(bool)

    @staticmethod
    def _sample_masked(masks: np.ndarray) -> np.ndarray:
        return np.array([np.random.choice(np.flatnonzero(m)) for m in masks])

    def _sample_action(
        self, learning_starts: int, action_noise: Any = None, n_envs: int = 1,
    ) -> tuple[np.ndarray, np.ndarray]:
        masks = self._env_masks()
        if self.num_timesteps < learning_starts:
            action = self._sample_masked(masks)
        else:
            action, _ = self.predict(self._last_obs, deterministic=False,
                                     action_masks=masks)
        return action, action

    def predict(
        self,
        observation: np.ndarray | dict[str, np.ndarray],
        state: tuple[np.ndarray, ...] | None = None,
        episode_start: np.ndarray | None = None,
        deterministic: bool = False,
        action_masks: np.ndarray | None = None,
    ) -> tuple[np.ndarray, tuple[np.ndarray, ...] | None]:
        if action_masks is None:
            return super().predict(observation, state, episode_start, deterministic)

        masks = np.asarray(action_masks, dtype=bool).reshape(-1, self.action_space.n)
        if not masks.any(axis=1).all():
            raise ValueError("every state needs at least one applicable action")

        obs_tensor, vectorized = self.policy.obs_to_tensor(observation)
        if not deterministic and np.random.rand() < self.exploration_rate:
            action = self._sample_masked(masks)
        else:
            self.policy.set_training_mode(False)
            with th.no_grad():
                q = self.q_net(obs_tensor).cpu().numpy()
            action = np.where(masks, q, -np.inf).argmax(axis=1)

        if not vectorized:
            action = action.squeeze(axis=0)
        return action, state
