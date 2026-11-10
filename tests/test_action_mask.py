"""The action mask: it must agree with the mutators, and the agent must obey it."""

from __future__ import annotations

import numpy as np
import pytest

from fragalloc.actions import ActionSpace
from fragalloc.env import FragAllocEnv


def _states(config, n_episodes: int = 5):
    """Yield (simulator, mask) along random-policy trajectories."""
    env = FragAllocEnv(config)
    rng = np.random.default_rng(0)
    for seed in range(n_episodes):
        env.reset(seed=seed)
        done = False
        while not done:
            yield env.sim, env.action_masks()
            _, _, _, done, _ = env.step(int(rng.integers(env.action_space.n)))


def test_mask_agrees_with_apply_in_every_visited_state(tiny_config) -> None:
    """The mask restates the catalogue's refusals; trial application is the truth."""
    checked = 0
    for sim, mask in _states(tiny_config):
        space: ActionSpace = sim.action_space
        for a in range(space.n):
            trial = sim.catalog.copy()
            applied = space.apply(trial, a, sim.topology.rtt).applied
            # NOOP never "applies", but it is always a legal choice.
            expected = True if a == space.noop_index else applied
            assert mask[a] == expected, (space.describe(a), mask[a], applied)
        checked += 1
    assert checked > 20


def test_mask_refuses_every_split_once_the_catalogue_is_full(tiny_config) -> None:
    """Random play rarely reaches max_fragments, so drive it there directly."""
    env = FragAllocEnv(tiny_config)
    env.reset(seed=0)
    space, cat = env.sim.action_space, env.sim.catalog
    while cat.n_fragments < tiny_config.catalog.max_fragments:
        widest = int(np.argmax(cat.sizes_cells))
        assert space.apply(cat, space._split_base + widest, env.sim.topology.rtt).applied
    mask = env.action_masks()
    assert not mask[space._split_base:space.noop_index].any()
    for a in range(space.n):
        applied = space.apply(cat.copy(), a, env.sim.topology.rtt).applied
        assert mask[a] == (True if a == space.noop_index else applied), space.describe(a)


def test_mask_has_the_action_space_shape_and_never_empties(tiny_config) -> None:
    for sim, mask in _states(tiny_config, n_episodes=2):
        assert mask.shape == (sim.action_space.n,) and mask.dtype == bool
        assert mask[sim.action_space.noop_index]


def test_masked_dqn_only_ever_picks_applicable_actions(tiny_config) -> None:
    pytest.importorskip("stable_baselines3")
    from fragalloc.agent.masked_dqn import MaskedDQN

    env = FragAllocEnv(tiny_config)
    model = MaskedDQN("MlpPolicy", env, learning_starts=50, buffer_size=500,
                      exploration_fraction=0.5, seed=0, device="cpu")
    model.learn(total_timesteps=200)      # covers warm-up, epsilon and greedy branches

    env.reset(seed=123)
    for deterministic in (True, False):
        for _ in range(tiny_config.episode.windows_per_episode - 1):
            mask = env.action_masks()
            obs = env._observe()
            action, _ = model.predict(obs, deterministic=deterministic, action_masks=mask)
            assert mask[int(action)], env.sim.action_space.describe(int(action))
            env.step(int(action))
        env.reset(seed=124)


class _RecordingEnv(FragAllocEnv):
    """Records, before each step, whether the chosen action was in the mask."""

    def __init__(self, config) -> None:
        super().__init__(config)
        self.in_mask: list[bool] = []

    def step(self, action):
        self.in_mask.append(bool(self.action_masks()[int(action)]))
        return super().step(action)


def test_every_action_taken_during_training_is_in_the_mask(tiny_config) -> None:
    """Warm-up, epsilon and greedy branches alike: no step is spent on a refusal."""
    pytest.importorskip("stable_baselines3")
    from fragalloc.agent.masked_dqn import MaskedDQN

    env = _RecordingEnv(tiny_config)
    model = MaskedDQN("MlpPolicy", env, learning_starts=50, buffer_size=500,
                      exploration_fraction=0.5, seed=1, device="cpu")
    model.learn(total_timesteps=300)
    assert len(env.in_mask) == 300
    assert all(env.in_mask)
