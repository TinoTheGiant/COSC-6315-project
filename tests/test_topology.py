"""The latency matrix and the geographic circle."""

from __future__ import annotations

import numpy as np
import pytest

from shardmind.config import TopologyConfig
from shardmind.topology import DEFAULT_RTT_MS, build_topology


def test_matrix_is_symmetric_with_intra_region_diagonal(topology) -> None:
    assert np.allclose(topology.rtt, topology.rtt.T)
    assert np.allclose(np.diag(topology.rtt), 1.0)
    assert np.all(topology.rtt > 0.0)


def test_asymmetric_input_is_symmetrized() -> None:
    raw = np.array(DEFAULT_RTT_MS, dtype=float)
    raw[0, 1] = 200.0  # deliberately inconsistent with raw[1, 0] == 65.0
    topo = build_topology(
        TopologyConfig(rtt_matrix_ms=tuple(map(tuple, raw))), dataset_bytes=1.0
    )
    assert topo.rtt[0, 1] == topo.rtt[1, 0]
    assert topo.rtt[0, 1] == pytest.approx((200.0 + 65.0) / 2)


def test_cross_region_is_always_slower_than_intra_region(topology) -> None:
    off_diagonal = topology.rtt[~np.eye(topology.n_regions, dtype=bool)]
    assert off_diagonal.min() > topology.rtt[0, 0]


def test_european_regions_are_closer_to_each_other_than_to_asia(topology) -> None:
    eu_west, eu_central, ap_southeast = 2, 3, 4
    assert topology.rtt[eu_west, eu_central] < topology.rtt[eu_west, ap_southeast]


def test_nearest_picks_the_lowest_rtt_candidate(topology) -> None:
    candidates = np.array([4, 3, 1])
    assert topology.nearest(3, candidates) == 3
    assert topology.nearest(0, np.array([4, 5])) == 5


def test_missing_table_for_unusual_region_count_is_an_error() -> None:
    cfg = TopologyConfig(region_names=("a", "b", "c"), region_longitudes_deg=(0.0, 10.0, 20.0))
    with pytest.raises(ValueError, match="no built-in RTT table"):
        build_topology(cfg, dataset_bytes=1.0)


def test_explicit_table_of_matching_size_is_accepted() -> None:
    cfg = TopologyConfig(
        region_names=("a", "b", "c"),
        region_longitudes_deg=(0.0, 10.0, 20.0),
        rtt_matrix_ms=((1.0, 10.0, 20.0), (10.0, 1.0, 30.0), (20.0, 30.0, 1.0)),
    )
    topo = build_topology(cfg, dataset_bytes=3.0)
    assert topo.n_regions == 3
    assert topo.storage_capacity_bytes == pytest.approx(3.0 * 3.0 / 3)


def test_rtt_matrix_is_immutable(topology) -> None:
    with pytest.raises(ValueError):
        topology.rtt[0, 0] = 5.0
