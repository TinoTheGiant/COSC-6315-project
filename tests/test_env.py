"""The Gymnasium adapter: interface conformance, reward shape, episode shape."""

from __future__ import annotations

from dataclasses import replace

import gymnasium as gym
import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env

from fragalloc.actions import ActionKind, ActionSpace
from fragalloc.config import RewardConfig, FragAllocConfig
from fragalloc.env import ENV_ID, FragAllocEnv


@pytest.fixture
def env(tiny_config) -> FragAllocEnv:
    return FragAllocEnv(tiny_config)


def test_passes_the_gymnasium_conformance_check(tiny_config) -> None:
    check_env(FragAllocEnv(tiny_config), skip_render_check=True)


def test_spaces_have_the_declared_shape(env, tiny_config) -> None:
    assert isinstance(env.action_space, gym.spaces.Discrete)
    assert env.action_space.n == ActionSpace(
        tiny_config.catalog.max_fragments, tiny_config.n_regions
    ).n
    assert env.observation_space.shape == (env.encoder.dim,)
    assert env.observation_space.dtype == np.float32


def test_observations_stay_inside_the_declared_box(env, tiny_config) -> None:
    obs, _ = env.reset(seed=0)
    assert env.observation_space.contains(obs)
    for _ in range(tiny_config.episode.windows_per_episode):
        obs, _, _, _, _ = env.step(env.action_space.sample())
        assert env.observation_space.contains(obs)
        assert np.all(np.isfinite(obs))


def test_the_environment_is_registered(tiny_config) -> None:
    assert ENV_ID in gym.registry
    made = gym.make(ENV_ID, config=tiny_config)
    made.reset(seed=1)
    made.close()


def test_an_episode_truncates_rather_than_terminating(env, tiny_config) -> None:
    env.reset(seed=0)
    steps = 0
    while True:
        _, _, terminated, truncated, _ = env.step(env.sim.action_space.noop_index)
        steps += 1
        assert not terminated, "the control problem has no absorbing state"
        if truncated:
            break
    assert steps == tiny_config.episode.windows_per_episode


def test_stepping_past_the_horizon_is_an_error(env, tiny_config) -> None:
    env.reset(seed=0)
    for _ in range(tiny_config.episode.windows_per_episode):
        env.step(env.sim.action_space.noop_index)
    with pytest.raises(RuntimeError, match="reset"):
        env.step(env.sim.action_space.noop_index)


def test_reward_is_finite_and_non_positive(env, tiny_config) -> None:
    env.reset(seed=0)
    for _ in range(tiny_config.episode.windows_per_episode):
        _, reward, _, _, _ = env.step(env.action_space.sample())
        assert np.isfinite(reward)
        assert reward <= 0.0, "every term in the reward is a cost"


def test_info_carries_the_diagnostics_the_experiments_need(env) -> None:
    _, info = env.reset(seed=0)
    for key in ("mean_latency_ms", "tail_latency_ms", "bytes_moved", "n_fragments"):
        assert key in info
    _, _, _, _, info = env.step(env.action_space.sample())
    assert "action_applied" in info and "reward" in info


def test_an_inapplicable_action_is_charged_a_small_fixed_cost(tiny_config) -> None:
    cfg = replace(
        tiny_config,
        reward=RewardConfig(w_latency=0.0, w_migration=0.0, w_imbalance=0.0,
                            inapplicable_action_cost=0.05),
    )
    env = FragAllocEnv(cfg)
    env.reset(seed=0)
    _, reward, _, _, info = env.step(env.sim.action_space.noop_index)
    assert not info["action_applied"]
    assert reward == pytest.approx(-0.05)


def test_migration_weight_penalizes_moving_data(tiny_config) -> None:
    cfg = replace(
        tiny_config,
        reward=RewardConfig(w_latency=0.0, w_migration=1.0, w_imbalance=0.0,
                            inapplicable_action_cost=0.0, migration_scale_fraction=1.0 / 6.0),
    )
    env = FragAllocEnv(cfg)
    env.reset(seed=0)
    space = env.sim.action_space
    target = int(np.flatnonzero(~env.sim.catalog.replicas[0])[0])
    _, reward, _, _, info = env.step(space.encode(ActionKind.MOVE_REPLICA_TO, 0, target))
    assert info["action_applied"]
    unit = cfg.catalog.dataset_bytes / 6.0
    assert reward == pytest.approx(-info["bytes_moved"] / unit)


def test_migration_cost_is_a_dataset_fraction_not_a_byte_count(tiny_config) -> None:
    """The same physical move must score the same in a big and a small cluster.

    This is the property the whole sim-to-real transfer rests on. The simulator
    holds 60 GB and the cluster will hold one or two; if migration were charged
    in bytes, a pre-trained Q-function would arrive on the cluster believing
    every move was almost free. ADR-0010.
    """
    reward_cfg = RewardConfig(w_latency=0.0, w_migration=1.0, w_imbalance=0.0,
                              inapplicable_action_cost=0.0)
    rewards = []
    for dataset_bytes in (6.0e10, 1.0e9):
        cfg = replace(
            tiny_config,
            reward=reward_cfg,
            catalog=replace(tiny_config.catalog, dataset_bytes=dataset_bytes),
        )
        env = FragAllocEnv(cfg)
        env.reset(seed=0)
        space = env.sim.action_space
        target = int(np.flatnonzero(~env.sim.catalog.replicas[0])[0])
        _, reward, _, _, info = env.step(
            space.encode(ActionKind.MOVE_REPLICA_TO, 0, target))
        assert info["action_applied"]
        rewards.append(reward)

    assert rewards[0] == pytest.approx(rewards[1], rel=1e-9)


def test_a_policy_that_follows_the_traffic_beats_one_that_does_not(default_config) -> None:
    """End to end: the reward signal has to point somewhere.

    If a myopic tracker cannot beat doing nothing, no learned policy will, and
    the fault is in the reward rather than in the agent. This is the check the
    week 3 tabular sanity harness generalizes.
    """
    from fragalloc.policies import FollowTrafficPolicy, StaticHashPolicy, rollout
    from fragalloc.simulator import ClusterSimulator

    cfg = replace(default_config, episode=replace(default_config.episode, windows_per_episode=60))
    sim = ClusterSimulator(cfg)
    space = sim.action_space

    static = rollout(sim, StaticHashPolicy(space), seed=0)
    tracking = rollout(sim, FollowTrafficPolicy(space), seed=0)

    static_latency = float(np.mean([r["mean_latency_ms"] for r in static]))
    tracking_latency = float(np.mean([r["mean_latency_ms"] for r in tracking]))
    assert tracking_latency < static_latency


def test_render_returns_text(tiny_config) -> None:
    env = FragAllocEnv(tiny_config, render_mode="ansi")
    env.reset(seed=0)
    text = env.render()
    assert "fragments" in text and "mean" in text
