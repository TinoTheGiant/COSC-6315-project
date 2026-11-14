"""n-step returns in MaskedReplayBuffer and MaskedDQN (ADR-0014).

The buffer is checked on hand-built transitions whose rewards are known, so
every expected return is computed here by hand rather than by the code under
test.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("torch")
gym = pytest.importorskip("gymnasium")

from fragalloc.agent.masked_dqn import MaskedDQN, MaskedReplayBuffer  # noqa: E402
from fragalloc.env import FragAllocEnv  # noqa: E402

N_ACTIONS = 4
GAMMA = 0.5


def _buffer(size: int, n_steps: int) -> MaskedReplayBuffer:
    return MaskedReplayBuffer(
        size,
        gym.spaces.Box(-np.inf, np.inf, shape=(1,), dtype=np.float32),
        gym.spaces.Discrete(N_ACTIONS),
        device="cpu", n_steps=n_steps, gamma=GAMMA)


def _add(buf: MaskedReplayBuffer, t: int, *, done: bool = False,
         truncated: bool = False) -> None:
    """Transition t: obs t, next obs t + 0.5, reward t, next-state mask only t % 4."""
    mask = np.zeros(N_ACTIONS, dtype=bool)
    mask[t % N_ACTIONS] = True
    buf.add(np.array([[t]], dtype=np.float32),
            np.array([[t + 0.5]], dtype=np.float32),
            np.array([[0]]), np.array([float(t)]), np.array([done or truncated]),
            [{"action_mask": mask, "TimeLimit.truncated": truncated}])


def _sample(buf: MaskedReplayBuffer, index: int):
    s = buf._get_samples(np.array([index]))
    return (float(s.rewards[0, 0]), float(s.next_observations[0, 0]),
            int(s.next_action_masks[0].float().argmax()),
            float(s.dones[0, 0]), float(s.discounts[0, 0]))


def test_one_step_takes_the_original_path() -> None:
    buf = _buffer(8, n_steps=1)
    for t in range(4):
        _add(buf, t)
    s = buf._get_samples(np.array([1]))
    assert s.discounts is None
    assert float(s.rewards[0, 0]) == 1.0
    assert float(s.next_observations[0, 0]) == 1.5


def test_return_is_the_discounted_sum_and_the_target_moves_n_ahead() -> None:
    buf = _buffer(16, n_steps=3)
    for t in range(8):
        _add(buf, t)
    reward, next_obs, mask_at, done, discount = _sample(buf, 2)
    assert reward == pytest.approx(2 + GAMMA * 3 + GAMMA**2 * 4)
    assert next_obs == 4.5, "next observation is the one after the third step"
    assert mask_at == 4 % N_ACTIONS, "mask belongs to that same next state"
    assert done == 0.0
    assert discount == pytest.approx(GAMMA**3)


def test_a_truncation_ends_the_run_but_still_bootstraps() -> None:
    buf = _buffer(16, n_steps=3)
    _add(buf, 0)
    _add(buf, 1, truncated=True)
    for t in range(2, 6):
        _add(buf, t)
    reward, next_obs, _, done, discount = _sample(buf, 0)
    assert reward == pytest.approx(0 + GAMMA * 1), "rewards after the episode end are excluded"
    assert next_obs == 1.5
    assert done == 0.0, "a time limit is not a terminal state"
    assert discount == pytest.approx(GAMMA**2)


def test_a_termination_ends_the_run_and_stops_bootstrapping() -> None:
    buf = _buffer(16, n_steps=3)
    _add(buf, 0)
    _add(buf, 1, done=True)
    for t in range(2, 6):
        _add(buf, t)
    reward, _, _, done, _ = _sample(buf, 0)
    assert reward == pytest.approx(0 + GAMMA * 1)
    assert done == 1.0


def test_a_run_never_reads_past_the_newest_transition() -> None:
    buf = _buffer(16, n_steps=3)
    for t in range(3):
        _add(buf, t)
    reward, next_obs, _, _, discount = _sample(buf, 2)
    assert reward == 2.0, "unwritten slots must not contribute"
    assert next_obs == 2.5
    assert discount == pytest.approx(GAMMA)


def test_a_run_never_wraps_into_an_older_episode() -> None:
    buf = _buffer(4, n_steps=3)
    for t in range(6):          # slots hold t = 4, 5, 2, 3; newest is t = 5
        _add(buf, t)
    reward, next_obs, _, _, discount = _sample(buf, 1)   # t = 5
    assert reward == 5.0, "the slot after the newest is the oldest, t = 2"
    assert next_obs == 5.5
    assert discount == pytest.approx(GAMMA)
    reward, next_obs, _, _, _ = _sample(buf, 3)          # t = 3, 4, 5 wraps legally
    assert reward == pytest.approx(3 + GAMMA * 4 + GAMMA**2 * 5)
    assert next_obs == 5.5


def test_sampling_leaves_the_stored_timeouts_unchanged() -> None:
    buf = _buffer(8, n_steps=3)
    for t in range(5):
        _add(buf, t)
    before = buf.timeouts.copy()
    buf._get_samples(np.array([0, 1, 2, 3, 4]))
    assert np.array_equal(buf.timeouts, before)


def _model(tiny_config, n_steps: int) -> MaskedDQN:
    return MaskedDQN("MlpPolicy", FragAllocEnv(tiny_config), n_steps=n_steps,
                     gamma=0.9, learning_starts=20, buffer_size=200, batch_size=8,
                     policy_kwargs={"net_arch": [16]}, seed=0, verbose=0)


def test_masked_dqn_hands_n_and_gamma_to_its_buffer(tiny_config) -> None:
    model = _model(tiny_config, n_steps=3)
    assert isinstance(model.replay_buffer, MaskedReplayBuffer)
    assert model.replay_buffer.n_steps == 3
    assert model.replay_buffer.gamma == pytest.approx(0.9)


def test_n_step_survives_save_and_load(tiny_config, tmp_path) -> None:
    model = _model(tiny_config, n_steps=3)
    model.learn(total_timesteps=60)
    model.save(tmp_path / "m")
    loaded = MaskedDQN.load(tmp_path / "m", env=FragAllocEnv(tiny_config))
    assert loaded.n_step_returns == 3
    assert loaded.replay_buffer.n_steps == 3


def test_default_is_one_step(tiny_config) -> None:
    assert _model(tiny_config, n_steps=1).replay_buffer.n_steps == 1
    with pytest.raises(ValueError):
        _model(tiny_config, n_steps=0)
