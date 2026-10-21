"""The learner's configuration, tested without importing torch.

These are cheap invariants, but they are the ones that silently ruin a training
run: an evaluation set that overlaps the training seeds reports recall as
generalization, and an exploration schedule that is accidentally inverted
produces a curve that looks like learning and is not.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from fragalloc.agent.config import DQNConfig


def test_the_default_configuration_is_valid() -> None:
    DQNConfig()


def test_evaluation_seeds_may_not_overlap_training_seeds() -> None:
    with pytest.raises(ValueError, match="overlap"):
        DQNConfig(train_seeds=2_000, eval_seed_start=1_000)


def test_exploration_must_anneal_downwards() -> None:
    with pytest.raises(ValueError):
        DQNConfig(exploration_initial_eps=0.1, exploration_final_eps=0.9)


def test_learning_cannot_start_after_the_budget_is_spent() -> None:
    with pytest.raises(ValueError):
        DQNConfig(total_timesteps=1_000, learning_starts=1_000)


def test_the_configuration_round_trips_through_json(tmp_path) -> None:
    """A saved model that cannot be matched to its hyperparameters is not a result."""
    original = replace(DQNConfig(), total_timesteps=12_345, net_arch=(64, 64))
    path = tmp_path / "agent.json"
    original.save(path)
    assert DQNConfig.load(path) == original
    # And the file is plain JSON, readable without importing the package.
    assert json.loads(path.read_text())["total_timesteps"] == 12_345


def test_the_sb3_keyword_set_is_exactly_what_dqn_accepts() -> None:
    """Guards against a hyperparameter that is recorded but never applied.

    A field added to DQNConfig and forgotten in to_sb3_kwargs would be written
    into the manifest, read by a reviewer as the setting used, and have had no
    effect on the run. The names are checked against the DQN signature when
    Stable-Baselines3 is installed, and the shape of the dict otherwise.
    """
    kwargs = DQNConfig().to_sb3_kwargs()
    assert kwargs["policy_kwargs"] == {"net_arch": [256, 256]}
    assert kwargs["exploration_final_eps"] <= kwargs["exploration_initial_eps"]

    sb3 = pytest.importorskip("stable_baselines3")
    import inspect

    accepted = set(inspect.signature(sb3.DQN.__init__).parameters)
    assert set(kwargs) <= accepted, set(kwargs) - accepted


def test_every_hyperparameter_reaches_either_sb3_or_the_training_loop() -> None:
    """No field may be decorative.

    Each DQNConfig field is either passed to Stable-Baselines3 or consumed by
    fragalloc.agent.train. This test names the second group explicitly, so
    adding a field without wiring it up fails here rather than in a silent run.
    """
    consumed_by_training_loop = {
        "total_timesteps", "net_arch", "eval_every_steps", "eval_episodes",
        "train_seeds", "eval_seed_start",
    }
    fields = set(DQNConfig().to_dict())
    unaccounted = fields - set(DQNConfig().to_sb3_kwargs()) - consumed_by_training_loop
    assert not unaccounted, f"hyperparameters that do nothing: {unaccounted}"
