"""Evaluation must use the action rule the model was trained under.

Both mismatches are silent without these checks: a masked model evaluated
unmasked reports static hashing, and an unmasked model evaluated masked moves
two orders of magnitude more data than it did when its numbers were recorded.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("stable_baselines3")

from stable_baselines3 import DQN  # noqa: E402

from fragalloc.agent.masked_dqn import (  # noqa: E402
    MaskedDQN,
    resolve_eval_mode,
    trained_with_mask,
)
from fragalloc.agent.policy import LearnedPolicy  # noqa: E402
from fragalloc.agent.train import evaluate_greedy  # noqa: E402
from fragalloc.env import FragAllocEnv  # noqa: E402
from fragalloc.policies import rollout  # noqa: E402
from fragalloc.simulator import ClusterSimulator  # noqa: E402


@pytest.fixture
def masked_path(tiny_config, tmp_path):
    model = MaskedDQN("MlpPolicy", FragAllocEnv(tiny_config), learning_starts=20,
                      buffer_size=200, seed=0, device="cpu")
    model.learn(total_timesteps=60)
    model.save(tmp_path / "masked")
    return tmp_path / "masked.zip"


@pytest.fixture
def plain_path(tiny_config, tmp_path):
    model = DQN("MlpPolicy", FragAllocEnv(tiny_config), learning_starts=20,
                buffer_size=200, seed=0, device="cpu")
    model.learn(total_timesteps=60)
    model.save(tmp_path / "plain")
    return tmp_path / "plain.zip"


# ------------------------------------------------------------- the record


def test_a_masked_model_records_it_and_the_record_survives_save(masked_path) -> None:
    assert trained_with_mask(MaskedDQN.load(masked_path, device="cpu"))


def test_a_plain_dqn_archive_reads_as_unmasked(plain_path, tiny_config) -> None:
    loaded = MaskedDQN.load(plain_path, env=FragAllocEnv(tiny_config), device="cpu")
    assert not trained_with_mask(loaded)
    loaded.learn(total_timesteps=30)          # masked fine-tuning changes that
    assert trained_with_mask(loaded)


# ------------------------------------------------------------- the rule


def test_auto_follows_training_and_every_mismatch_is_refused(masked_path, plain_path) -> None:
    masked = MaskedDQN.load(masked_path, device="cpu")
    plain = MaskedDQN.load(plain_path, device="cpu")

    assert resolve_eval_mode(masked) == "mask"
    assert resolve_eval_mode(plain) == "none"
    assert resolve_eval_mode(plain, "collapse") == "collapse"
    assert resolve_eval_mode(masked, True) == "mask"
    assert resolve_eval_mode(plain, False) == "none"

    for mode in ("none", "collapse", False):
        with pytest.raises(ValueError, match="trained with action masking"):
            resolve_eval_mode(masked, mode)
    for mode in ("mask", True):
        with pytest.raises(ValueError, match="trained without action masking"):
            resolve_eval_mode(plain, mode)
    with pytest.raises(ValueError, match="must be one of"):
        resolve_eval_mode(masked, "masked")


def test_learned_policy_and_evaluate_greedy_apply_the_rule(
        masked_path, plain_path, tiny_config) -> None:
    assert LearnedPolicy(masked_path, tiny_config).mode == "mask"
    assert LearnedPolicy(plain_path, tiny_config).mode == "none"
    meta = LearnedPolicy(masked_path, tiny_config).metadata
    assert meta["trained_with_mask"] is True and meta["eval_mode"] == "mask"
    with pytest.raises(ValueError):
        LearnedPolicy(masked_path, tiny_config, mask=False)

    masked = MaskedDQN.load(masked_path, device="cpu")
    assert evaluate_greedy(masked, tiny_config, [0])["mean_latency_ms"] > 0
    with pytest.raises(ValueError):
        evaluate_greedy(masked, tiny_config, [0], mode="none")


# ---------------------------------------------------------- collapse mode


class _Spy:
    """Wraps a policy and records whether each chosen action was applicable."""

    def __init__(self, policy) -> None:
        self.policy, self.legal = policy, []

    def act(self, sim):
        a = self.policy.act(sim)
        self.legal.append(bool(sim.action_space.applicable_mask(sim.catalog)[a]))
        return a

    def reset(self):
        self.policy.reset()


def test_collapse_reproduces_the_unmasked_run_with_only_legal_actions(
        plain_path, tiny_config) -> None:
    runs = {}
    for mode in ("none", "collapse"):
        spy = _Spy(LearnedPolicy(plain_path, tiny_config, mask=mode))
        records = rollout(ClusterSimulator(tiny_config), spy, seed=3)
        runs[mode] = (records, spy.legal)

    none_records, none_legal = runs["none"]
    collapse_records, collapse_legal = runs["collapse"]
    assert not all(none_legal), "test needs the unmasked argmax to pick an inapplicable action"
    assert all(collapse_legal)
    for key in ("mean_latency_ms", "tail_latency_ms", "bytes_moved"):
        assert np.allclose([r[key] for r in none_records],
                           [r[key] for r in collapse_records]), key
