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

Evaluation must match training
------------------------------
A model is only valid together with the action rule it was trained under, and
getting this wrong is silent in both directions (three-way review, 10 Nov 2026):

* a masked model evaluated **without** the mask chose an inapplicable action
  100% of the time and scored exactly as static hashing, because its values
  for never-taken actions are untrained and sit about 30 points too high;
* an unmasked model evaluated **with** the mask moved 520.7 GB instead of
  3.4 GB, because its argmax was mostly an inapplicable action that meant
  "stay put", and the mask forced it onto a real move.

So every ``MaskedDQN`` records ``trained_with_mask`` in its archive, and
:func:`resolve_eval_mode` picks the evaluation mode from it and refuses a
mismatch. The modes:

``"mask"``      masked argmax; the only mode for a masked-trained model.
``"none"``      the unmasked argmax, exactly as the model was trained; the
                default for an unmasked model, so recorded numbers reproduce.
``"collapse"``  the unmasked argmax, relabelled NOOP when it is inapplicable.
                For an unmasked model this gives the identical trajectory
                (an inapplicable action already behaves as NOOP) while only
                ever emitting legal actions, which is what a real cluster
                needs. The reward is not identical: since ADR-0013 NOOP
                is free whilst an inapplicable action still pays
                ``inapplicable_action_cost``, so ``"collapse"`` scores slightly
                better on reward. Latency and bytes moved are unchanged.
``"auto"``      ``"mask"`` or ``"none"``, from ``trained_with_mask``.
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
    """A replay buffer that also stores the action mask of each next state.

    With ``n_steps > 1`` it samples n-step returns: the reward is the
    discounted sum of up to ``n_steps`` consecutive rewards, the next
    observation and next-state mask are those at the end of that run, and
    ``discounts`` carries ``gamma ** k`` for the ``k`` steps actually summed.
    A run stops early at an episode end, and never crosses the write head into
    transitions from an older episode. This follows Stable-Baselines3's
    ``NStepReplayBuffer``, which cannot be used here because it does not carry
    the mask of the n-th next state that the masked target needs. ADR-0014.

    ``n_steps == 1`` takes exactly the one-step path used before, so a model
    trained without n-step returns trains identically.
    """

    def __init__(self, buffer_size: int, observation_space, action_space,
                 device: Any = "auto", n_envs: int = 1,
                 optimize_memory_usage: bool = False,
                 handle_timeout_termination: bool = True,
                 n_steps: int = 1, gamma: float = 0.99) -> None:
        if optimize_memory_usage:
            raise ValueError("MaskedReplayBuffer does not support optimize_memory_usage")
        if int(n_steps) < 1:
            raise ValueError("n_steps must be at least 1")
        self.n_steps = int(n_steps)
        self.gamma = float(gamma)
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
        if self.n_steps > 1:
            return self._get_n_step_samples(batch_inds, env)
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

    def _get_n_step_samples(self, batch_inds: np.ndarray, env=None) -> MaskedReplayBufferSamples:
        n, size = self.n_steps, self.buffer_size
        env_indices = np.random.randint(0, high=self.n_envs, size=(len(batch_inds),))

        # The newest transition is followed in storage by the oldest, from a
        # different episode. Treating it as truncated for the duration of this
        # call stops every run there.
        newest = (self.pos - 1) % size
        saved = self.timeouts[newest].copy()
        self.timeouts[newest] = np.logical_or(saved, self.dones[newest] == 0)
        try:
            steps = np.arange(n).reshape(1, -1)
            idx = (batch_inds[:, None] + steps) % size                  # [B, n]
            env_col = env_indices[:, None]
            rewards = self._normalize_reward(self.rewards[idx, env_col], env)
            ends = (self.dones[idx, env_col] > 0) | (self.timeouts[idx, env_col] > 0)
            last = np.where(ends.any(axis=1), ends.argmax(axis=1), n - 1)  # [B]
            used = steps <= last[:, None]
            returns = (rewards * (self.gamma ** steps) * used).sum(axis=1, keepdims=True)

            rows = np.arange(len(batch_inds))
            end_idx = idx[rows, last]
            dones = (self.dones[end_idx, env_indices]
                     * (1 - self.timeouts[end_idx, env_indices])).reshape(-1, 1)
            discounts = (self.gamma ** (last + 1)).reshape(-1, 1)
            data = (
                self._normalize_obs(self.observations[batch_inds, env_indices, :], env),
                self.actions[batch_inds, env_indices, :],
                self._normalize_obs(self.next_observations[end_idx, env_indices, :], env),
                dones,
                returns,
                self.next_action_masks[end_idx, env_indices, :],
                discounts,
            )
        finally:
            self.timeouts[newest] = saved
        return MaskedReplayBufferSamples(
            *tuple(self.to_torch(np.asarray(d, dtype=np.float32) if i in (3, 4, 6) else d)
                   for i, d in enumerate(data)))


class MaskedDQN(DQN):
    """``stable_baselines3.DQN`` with action masking at selection and in the target."""

    def __init__(self, *args: Any, n_steps: int = 1, **kwargs: Any) -> None:
        # n-step returns are handled by MaskedReplayBuffer, never by
        # Stable-Baselines3's own n_steps, which would be ignored next to a
        # custom buffer. Stored under a distinct name so it survives save/load
        # and an older archive without it reads as one step.
        if int(n_steps) < 1:
            raise ValueError("n_steps must be at least 1")
        self.n_step_returns = int(n_steps)
        # A model built to train is a masked model. One being loaded is built
        # with _init_setup_model=False and then takes the archived value, so an
        # archive written by a plain DQN, which has no such field, reads False.
        self.trained_with_mask = bool(kwargs.get("_init_setup_model", True))
        super().__init__(*args, **kwargs)

    def learn(self, *args: Any, **kwargs: Any):
        # Any masked training at all, including fine-tuning a plain-DQN
        # archive, leaves never-taken actions untrained, so the flag is set.
        self.trained_with_mask = True
        return super().learn(*args, **kwargs)

    def _setup_model(self) -> None:
        # Also runs on load, so archives written by a plain DQN get the masked
        # buffer too and can be trained further.
        if self.replay_buffer_class in (None, ReplayBuffer):
            self.replay_buffer_class = MaskedReplayBuffer
        elif not issubclass(self.replay_buffer_class, MaskedReplayBuffer):
            raise TypeError("MaskedDQN needs a MaskedReplayBuffer to mask its target")
        self.replay_buffer_kwargs = {
            **(self.replay_buffer_kwargs or {}),
            "n_steps": getattr(self, "n_step_returns", 1),
            "gamma": self.gamma,
        }
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


# ---------------------------------------------------------------- evaluation

EVAL_MODES = ("auto", "mask", "none", "collapse")


def trained_with_mask(model: Any) -> bool:
    """True if ``model`` was trained with masked selection. Plain DQN: False."""
    return bool(getattr(model, "trained_with_mask", False))


def resolve_eval_mode(model: Any, requested: str | bool = "auto") -> str:
    """Turn a requested evaluation mode into a concrete one, refusing mismatches.

    ``True`` and ``False`` are accepted for the earlier boolean ``mask=``
    argument and mean ``"mask"`` and ``"none"``.
    """
    if requested is True:
        requested = "mask"
    elif requested is False:
        requested = "none"
    if requested not in EVAL_MODES:
        raise ValueError(f"evaluation mode must be one of {EVAL_MODES}, got {requested!r}")

    masked = trained_with_mask(model)
    if requested == "auto":
        return "mask" if masked else "none"
    if masked and requested != "mask":
        raise ValueError(
            f"this model was trained with action masking; evaluating it with "
            f"mode {requested!r} reports a do-nothing policy. Use 'mask' or 'auto'.")
    if not masked and requested == "mask":
        raise ValueError(
            "this model was trained without action masking; masking its argmax "
            "turns its 'stay put' choices into real moves. Use 'none', "
            "'collapse' or 'auto'.")
    return requested


def select_action(model: Any, obs: np.ndarray, mask: np.ndarray, noop_index: int,
                  mode: str, deterministic: bool = True) -> int:
    """One action from ``model`` under a mode already checked by :func:`resolve_eval_mode`."""
    if mode == "mask":
        action, _ = model.predict(obs, deterministic=deterministic, action_masks=mask)
        return int(action)
    action, _ = model.predict(obs, deterministic=deterministic)
    action = int(action)
    if mode == "collapse" and not mask[action]:
        return int(noop_index)
    return action
