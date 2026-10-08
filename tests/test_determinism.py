"""Reproduction from a seed, which Objective 2 promises.

A result nobody can rerun is not a result, and a non-deterministic environment
makes an RL debugging session unfalsifiable: you can never tell a bad change
from a bad roll.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from shardmind.config import ShardMindConfig
from shardmind.env import ShardMindEnv
from shardmind.simulator import ClusterSimulator


def _trajectory(cfg: ShardMindConfig, seed: int, actions: list[int]):
    env = ShardMindEnv(cfg)
    obs, _ = env.reset(seed=seed)
    observations, rewards = [obs.copy()], []
    for action in actions:
        obs, reward, _, truncated, _ = env.step(action)
        observations.append(obs.copy())
        rewards.append(reward)
        if truncated:
            break
    return np.array(observations), np.array(rewards)


@pytest.fixture
def actions(tiny_config) -> list[int]:
    rng = np.random.default_rng(123)
    n = ShardMindEnv(tiny_config).action_space.n
    return [int(a) for a in rng.integers(n, size=tiny_config.episode.windows_per_episode)]


def test_the_same_seed_reproduces_the_episode_exactly(tiny_config, actions) -> None:
    obs_a, rew_a = _trajectory(tiny_config, 42, actions)
    obs_b, rew_b = _trajectory(tiny_config, 42, actions)
    assert np.array_equal(obs_a, obs_b)
    assert np.array_equal(rew_a, rew_b)


def test_a_different_seed_gives_a_different_episode(tiny_config, actions) -> None:
    _, rew_a = _trajectory(tiny_config, 42, actions)
    _, rew_b = _trajectory(tiny_config, 43, actions)
    assert not np.allclose(rew_a, rew_b)


def test_reset_restores_the_initial_catalogue(tiny_config, actions) -> None:
    sim = ClusterSimulator(tiny_config)
    initial = sim.catalog.boundaries.copy()
    for action in actions:
        if sim.last.done:
            break
        sim.step(action)
    sim.reset(seed=tiny_config.seed)
    assert np.array_equal(sim.catalog.boundaries, initial)
    assert sim.progress == 0.0
    assert np.all(sim.churn_history == 0.0)


def test_the_configured_seed_is_used_when_reset_is_given_none(tiny_config) -> None:
    a = ClusterSimulator(tiny_config)
    b = ClusterSimulator(replace(tiny_config, seed=tiny_config.seed))
    assert np.array_equal(a.last.window.reads, b.last.window.reads)

    c = ClusterSimulator(replace(tiny_config, seed=tiny_config.seed + 1))
    assert not np.allclose(a.last.window.reads, c.last.window.reads)


def test_two_simulators_stay_in_step_under_the_same_actions(tiny_config, actions) -> None:
    a, b = ClusterSimulator(tiny_config), ClusterSimulator(tiny_config)
    a.reset(seed=5)
    b.reset(seed=5)
    for action in actions:
        if a.last.done:
            break
        ra, rb = a.step(action), b.step(action)
        assert ra.cost.mean_latency_ms == rb.cost.mean_latency_ms
        assert ra.bytes_moved == rb.bytes_moved
    assert np.array_equal(a.catalog.boundaries, b.catalog.boundaries)
