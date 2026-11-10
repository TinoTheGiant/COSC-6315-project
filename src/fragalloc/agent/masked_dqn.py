"""DQN that only ever chooses, and only ever bootstraps from, an applicable action.

Measured before this change: 79.9 to 89.8% of the agent's chosen actions were
inapplicable, against 80.4% for a uniformly random policy. The fixed
``inapplicable_action_cost`` was not teaching the agent to avoid them fast
enough, so every such step was a wasted decision and a wasted transition.

Masking is applied in all three places the Q-function's argmax or max is used:

* **greedy choice**: Q-values of inapplicable actions are set to minus
  infinity before the argmax;
* **exploration**: the epsilon branch, and the warm-up before
  ``learning_starts``, sample uniformly from applicable actions only;
* **the bootstrap target**: ``max_a' Q_target(s', a')`` runs over the actions
  applicable in ``s'`` only.

The third matters as much as the first two. A masked agent never takes an
inapplicable action, so those actions' Q-values are never corrected, and they
drift with the shared network. Left inside the target max they leak upward bias
into every update (Huang and Ontanon, 2022, discuss the selection-only case).
To mask the target the replay buffer must know the mask of ``s'``, so the
environment reports it in ``info["action_mask"]`` on every step and
:class:`MaskedReplayBuffer` stores it beside the next observation.

Masks come from the environment's ``action_masks()`` during training and are
passed explicitly as ``action_masks=`` at evaluation, where the caller holds a
simulator rather than an environment. Without ``action_masks`` ``predict``
behaves exactly as ``stable_baselines3.DQN``.
"""

from __future__ import annotations

from typing import Any, NamedTuple

import numpy as np
import torch as th
import torch.nn.functional as F
from stable_baselines3 import DQN
from stable_baselines3.common.buffers import ReplayBuffer


class MaskedReplayBufferSamples(NamedTuple):
    observations: th.Tensor
    actions: th.Tensor
    next_observations: th.Tensor
    dones: th.Tensor
    rewards: th.Tensor
    next_action_masks: th.Tensor
    discounts: th.Tensor | None = None


class MaskedReplayBuffer(ReplayBuffer):
    """A replay buffer that also stores the action mask of each next state."""

    def __init__(self, buffer_size: int, observation_space, action_space,
                 device: Any = "auto", n_envs: int = 1,
                 optimize_memory_usage: bool = False,
                 handle_timeout_termination: bool = True) -> None:
        if optimize_memory_usage:
            raise ValueError("MaskedReplayBuffer does not support optimize_memory_usage")
        super().__init__(buffer_size, observation_space, action_space, device,
                         n_envs=n_envs, optimize_memory_usage=False,
                         handle_timeout_termination=handle_timeout_termination)
        self.next_action_masks = np.zeros(
            (self.buffer_size, self.n_envs, int(action_space.n)), dtype=bool)

    def add(self, obs, next_obs, action, reward, done, infos: list[dict[str, Any]]) -> None:
        try:
            masks = np.stack([np.asarray(info["action_mask"], dtype=bool) for info in infos])
        except KeyError as exc:
            raise KeyError("MaskedReplayBuffer needs info['action_mask'] from every "
                           "env step; FragAllocEnv.step provides it") from exc
        self.next_action_masks[self.pos] = masks      # before super() advances pos
        super().add(obs, next_obs, action, reward, done, infos)

    def _get_samples(self, batch_inds: np.ndarray, env=None) -> MaskedReplayBufferSamples:
        # Restated from ReplayBuffer._get_samples so that the mask is read at the
        # same environment index as the transition it belongs to.
        env_indices = np.random.randint(0, high=self.n_envs, size=(len(batch_inds),))
        data = (
            self._normalize_obs(self.observations[batch_inds, env_indices, :], env),
            self.actions[batch_inds, env_indices, :],
            self._normalize_obs(self.next_observations[batch_inds, env_indices, :], env),
            (self.dones[batch_inds, env_indices]
             * (1 - self.timeouts[batch_inds, env_indices])).reshape(-1, 1),
            self._normalize_reward(self.rewards[batch_inds, env_indices].reshape(-1, 1), env),
            self.next_action_masks[batch_inds, env_indices, :],
        )
        return MaskedReplayBufferSamples(*tuple(map(self.to_torch, data)))


class MaskedDQN(DQN):
    """``stable_baselines3.DQN`` with action masking at selection and in the target."""

    def _setup_model(self) -> None:
        # Also runs on load, so archives written by a plain DQN get the masked
        # buffer too and can be trained further.
        if self.replay_buffer_class in (None, ReplayBuffer):
            self.replay_buffer_class = MaskedReplayBuffer
        elif not issubclass(self.replay_buffer_class, MaskedReplayBuffer):
            raise TypeError("MaskedDQN needs a MaskedReplayBuffer to mask its target")
        super()._setup_model()

    # ----------------------------------------------------------- selection

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

    # ------------------------------------------------------------ learning

    def _masked_next_q(self, next_observations: th.Tensor,
                       next_action_masks: th.Tensor) -> th.Tensor:
        """``max_a' Q_target(s', a')`` over applicable ``a'`` only, shape ``(B, 1)``."""
        masks = next_action_masks.bool()
        if not bool(masks.any(dim=1).all()):
            raise ValueError("a stored next state has no applicable action")
        q = self.q_net_target(next_observations).masked_fill(~masks, -th.inf)
        return q.max(dim=1).values.reshape(-1, 1)

    def train(self, gradient_steps: int, batch_size: int = 100) -> None:
        # Restated from stable_baselines3.DQN.train; the one change is the
        # target, which calls _masked_next_q instead of an unmasked max.
        self.policy.set_training_mode(True)
        self._update_learning_rate(self.policy.optimizer)

        losses = []
        for _ in range(gradient_steps):
            replay_data = self.replay_buffer.sample(batch_size, env=self._vec_normalize_env)
            discounts = replay_data.discounts if replay_data.discounts is not None else self.gamma

            with th.no_grad():
                next_q_values = self._masked_next_q(replay_data.next_observations,
                                                    replay_data.next_action_masks)
                target_q_values = (replay_data.rewards
                                   + (1 - replay_data.dones) * discounts * next_q_values)

            current_q_values = self.q_net(replay_data.observations)
            current_q_values = th.gather(current_q_values, dim=1,
                                         index=replay_data.actions.long())

            loss = F.smooth_l1_loss(current_q_values, target_q_values)
            losses.append(loss.item())

            self.policy.optimizer.zero_grad()
            loss.backward()
            th.nn.utils.clip_grad_norm_(self.policy.parameters(), self.max_grad_norm)
            self.policy.optimizer.step()

        self._n_updates += gradient_steps
        self.logger.record("train/n_updates", self._n_updates, exclude="tensorboard")
        self.logger.record("train/loss", np.mean(losses))
