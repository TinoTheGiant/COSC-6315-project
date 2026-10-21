"""The Deep Q-Network agent, and everything needed to train and evaluate it.

This package is deliberately thin. Stable-Baselines3 provides the DQN; what
lives here is the three things SB3 does not know about this project:

* :mod:`fragalloc.agent.config` -- the hyperparameters, as a frozen dataclass
  that round-trips through JSON, so a trained model is never separated from the
  settings that produced it;
* :mod:`fragalloc.agent.train` -- the training loop, its callbacks and the
  artefacts it writes;
* :mod:`fragalloc.agent.policy` -- a wrapper that makes a trained model satisfy
  the same ``Policy`` protocol as the hand-written baselines, so the agent and
  the baselines are measured by one evaluation path rather than two.

The import of torch is deferred into the modules that need it. Importing
``fragalloc`` must stay cheap for the simulator-only code paths and for the
test suite, which runs without torch installed.
"""

from fragalloc.agent.config import DQNConfig

__all__ = ["DQNConfig"]
