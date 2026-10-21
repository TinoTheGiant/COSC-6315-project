"""Shared fixtures.

The suite works with a deliberately small configuration. Six regions are kept,
since the RTT table is built for them and the geography is the point, but the
keyspace, the fragment count and the episode length are all cut down so that the
whole suite runs in a couple of seconds. Anything that depends on the default
configuration says so explicitly.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from fragalloc.config import (
    CatalogConfig,
    EpisodeConfig,
    FragAllocConfig,
    WorkloadConfig,
)
from fragalloc.simulator import ClusterSimulator
from fragalloc.topology import build_topology
from fragalloc.workload import WorkloadGenerator, WorkloadWindow


@pytest.fixture
def tiny_config() -> FragAllocConfig:
    return FragAllocConfig(
        workload=WorkloadConfig(n_cells=32, n_txn_templates=12, txn_arity=3, txn_locality_cells=8),
        catalog=CatalogConfig(initial_fragments=4, max_fragments=8, min_replicas=2, max_replicas=3),
        episode=EpisodeConfig(windows_per_episode=12, warmup_windows=2, churn_history_windows=4),
        seed=7,
    )


@pytest.fixture
def default_config() -> FragAllocConfig:
    return FragAllocConfig()


@pytest.fixture
def sim(tiny_config: FragAllocConfig) -> ClusterSimulator:
    return ClusterSimulator(tiny_config)


@pytest.fixture
def topology(tiny_config: FragAllocConfig):
    return build_topology(tiny_config.topology, tiny_config.catalog.dataset_bytes)


@pytest.fixture
def generator(tiny_config: FragAllocConfig, topology) -> WorkloadGenerator:
    return WorkloadGenerator(
        tiny_config.workload, topology, np.random.default_rng(0), horizon=32
    )


def single_origin_window(
    cfg: FragAllocConfig, origin: int, index: int = 0
) -> WorkloadWindow:
    """A window in which every request originates in exactly one region.

    Hand-built rather than generated, so a test can state an expected latency in
    closed form instead of inferring it from the drift model.
    """
    k, r, t = cfg.workload.n_cells, cfg.n_regions, cfg.workload.n_txn_templates
    reads = np.zeros((k, r))
    writes = np.zeros((k, r))
    txns = np.zeros((t, r))
    reads[:, origin] = 1.0
    writes[:, origin] = 1.0
    txns[:, origin] = 1.0
    return WorkloadWindow(
        index=index,
        reads=reads,
        writes=writes,
        txn_counts=txns,
        centroid_angle=0.0,
        spike_multiplier=np.ones(r),
    )
