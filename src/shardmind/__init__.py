"""Reinforcement Learning for Dynamic Data Fragmentation and Allocation.

A simulated multi-region database cluster, and an RL control problem over it.

The package separates three concerns deliberately:

* ``simulator`` -- a pure-NumPy model of the cluster with no RL vocabulary in it.
  It knows about regions, fragments, workloads and latency. It has no notion of
  an observation, a reward or an episode.
* ``env`` -- a thin Gymnasium adapter over the simulator. It owns the encoding of
  state into a vector, the decoding of an integer into a placement action, and
  the scalarization of the cost vector into a reward.
* ``policies`` -- anything that chooses actions, learned or otherwise.

Keeping the first two apart means the cost model can be unit-tested and the
baselines evaluated without Gymnasium, PyTorch or Stable-Baselines3 in the loop.
"""

from shardmind.config import (
    CatalogConfig,
    CostConfig,
    RewardConfig,
    ShardMindConfig,
    TopologyConfig,
    WorkloadConfig,
)

__version__ = "0.1.0"

__all__ = [
    "CatalogConfig",
    "CostConfig",
    "RewardConfig",
    "ShardMindConfig",
    "TopologyConfig",
    "WorkloadConfig",
    "__version__",
]
