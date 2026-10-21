"""A trained model, wearing the same interface as the hand-written baselines.

The point of this module is one sentence: **the agent and the baselines must be
measured by the same code**. If the agent were evaluated inside a Gymnasium
loop and the baselines inside ``rollout``, any difference between the two loops
-- a warmup window counted differently, an off-by-one in when the cost is read
-- would land in the headline result and be indistinguishable from learning.

So :class:`LearnedPolicy` satisfies the ``Policy`` protocol in
:mod:`fragalloc.policies`: it takes a :class:`~fragalloc.simulator.ClusterSimulator`
and returns an action index. ``scripts/run_experiment.py`` then treats it as one
more entry in the policy table.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from fragalloc.config import FragAllocConfig
from fragalloc.env import observe
from fragalloc.observation import ObservationEncoder
from fragalloc.simulator import ClusterSimulator


class LearnedPolicy:
    """Wraps a saved Stable-Baselines3 model as a simulator policy.

    ``deterministic`` defaults to True: reported results come from the greedy
    policy the Q-function induces, not from an epsilon-greedy sample. Training
    uses exploration; evaluation should not, and mixing the two is a classic
    way to report a worse agent than you have.
    """

    def __init__(
        self,
        model_path: str | Path,
        config: FragAllocConfig,
        deterministic: bool = True,
    ) -> None:
        from stable_baselines3 import DQN  # deferred: torch is a heavy import

        self.config = config
        self.deterministic = deterministic
        # ``DQN.load`` validates the observation and action spaces against the
        # ones recorded in the archive and raises on a mismatch. That check is
        # the mechanism ADR-0009's parity requirement is enforced by, so the
        # exception is allowed to propagate rather than being caught here.
        self.model = DQN.load(str(model_path), device="cpu")
        self._encoder: ObservationEncoder | None = None
        self._encoder_for: int | None = None

    def _encoder_for_sim(self, sim: ClusterSimulator) -> ObservationEncoder:
        if self._encoder is None or self._encoder_for != id(sim.topology):
            self._encoder = ObservationEncoder(self.config, sim.topology)
            self._encoder_for = id(sim.topology)
        return self._encoder

    def act(self, sim: ClusterSimulator) -> int:
        obs = observe(self._encoder_for_sim(sim), sim)
        action, _ = self.model.predict(obs, deterministic=self.deterministic)
        return int(action)

    def reset(self) -> None:
        return None

    @property
    def metadata(self) -> dict[str, Any]:
        """What went into the model, for the run manifest."""
        return {
            "observation_dim": int(np.prod(self.model.observation_space.shape)),
            "n_actions": int(self.model.action_space.n),
            "policy_class": type(self.model.policy).__name__,
            "deterministic": self.deterministic,
        }
