"""The transaction cost model.

Most of these are property tests rather than fixed-number tests. The absolute
latency a placement produces is a modelling choice and will change as the model
is calibrated; the orderings asserted here are the model's meaning and must not.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from fragalloc.catalog import FragmentCatalog
from fragalloc.config import CatalogConfig, CostConfig
from fragalloc.cost import (
    coefficient_of_variation,
    evaluate,
    read_latency,
    replication_term,
    weighted_percentile,
    write_latency,
)
from fragalloc.topology import build_topology
from fragalloc.workload import WorkloadGenerator

from conftest import single_origin_window


@pytest.fixture
def catalog(tiny_config):
    return FragmentCatalog(tiny_config.catalog, tiny_config.workload.n_cells, tiny_config.n_regions)


def _collapse_to_region(catalog, region: int) -> None:
    """Put every fragment's primary and every replica in one region."""
    for f in range(catalog.n_fragments):
        catalog.set_primary(f, region)
        for r in range(catalog.n_regions):
            if r != region:
                catalog.drop_replica(f, r)


# ------------------------------------------------------------------ latency


def test_a_read_is_served_by_the_nearest_replica(catalog, topology, tiny_config) -> None:
    lat = read_latency(catalog, topology, tiny_config.cost)
    for f in range(catalog.n_fragments):
        replicas = np.flatnonzero(catalog.replicas[f])
        for origin in range(topology.n_regions):
            assert lat[f, origin] == pytest.approx(topology.rtt[origin, replicas].min())


def test_primary_only_reads_are_never_faster_than_nearest_replica(catalog, topology, tiny_config) -> None:
    nearest = read_latency(catalog, topology, tiny_config.cost)
    strict = read_latency(catalog, topology, replace(tiny_config.cost, read_consistency="primary_only"))
    assert np.all(strict >= nearest - 1e-9)


def test_write_acknowledgement_modes_are_ordered(catalog, topology) -> None:
    cfgs = {m: CostConfig(write_ack=m) for m in ("primary", "majority", "all")}
    terms = {m: replication_term(catalog, topology, c) for m, c in cfgs.items()}
    assert np.all(terms["primary"] == 0.0)
    assert np.all(terms["majority"] <= terms["all"] + 1e-9)
    assert np.all(terms["primary"] <= terms["majority"] + 1e-9)


def test_a_write_reaches_the_leader_before_replicating(catalog, topology, tiny_config) -> None:
    lat = write_latency(catalog, topology, tiny_config.cost)
    for f in range(catalog.n_fragments):
        primary = int(catalog.primary[f])
        for origin in range(topology.n_regions):
            assert lat[f, origin] >= topology.rtt[origin, primary] - 1e-9


def test_a_fully_collocated_cluster_costs_intra_region_latency(tiny_config, topology, generator) -> None:
    cfg = replace(
        tiny_config,
        catalog=replace(tiny_config.catalog, min_replicas=1, max_replicas=1),
        cost=CostConfig(write_ack="all"),
    )
    catalog = FragmentCatalog(cfg.catalog, cfg.workload.n_cells, cfg.n_regions)
    _collapse_to_region(catalog, 3)
    window = single_origin_window(cfg, origin=3)

    result = evaluate(catalog, window, generator, topology, cfg.cost)
    intra = cfg.topology.intra_region_rtt_ms

    assert result.cross_region_txn_fraction == 0.0, "one region cannot need two-phase commit"
    assert result.mean_read_latency_ms == pytest.approx(intra)
    assert result.mean_write_latency_ms == pytest.approx(intra)
    assert result.mean_txn_latency_ms == pytest.approx(intra * cfg.workload.txn_arity)


def test_distance_from_the_traffic_costs_latency(tiny_config, topology, generator) -> None:
    cfg = replace(tiny_config, catalog=replace(tiny_config.catalog, min_replicas=1, max_replicas=1))
    window = single_origin_window(cfg, origin=0)

    latencies = []
    for region in range(cfg.n_regions):
        catalog = FragmentCatalog(cfg.catalog, cfg.workload.n_cells, cfg.n_regions)
        _collapse_to_region(catalog, region)
        latencies.append(evaluate(catalog, window, generator, topology, cfg.cost).mean_latency_ms)

    assert int(np.argmin(latencies)) == 0, "the region the traffic comes from must win"
    ordering = np.argsort(topology.rtt[0])
    assert list(np.argsort(latencies)) == list(ordering)


def test_moving_the_primary_toward_the_traffic_lowers_latency(tiny_config, topology, generator) -> None:
    cfg = replace(tiny_config, catalog=replace(tiny_config.catalog, min_replicas=1, max_replicas=1))
    window = single_origin_window(cfg, origin=4)

    catalog = FragmentCatalog(cfg.catalog, cfg.workload.n_cells, cfg.n_regions)
    _collapse_to_region(catalog, 0)
    before = evaluate(catalog, window, generator, topology, cfg.cost).mean_latency_ms

    catalog.set_primary(0, 4)
    after = evaluate(catalog, window, generator, topology, cfg.cost).mean_latency_ms
    assert after < before


def test_two_phase_commit_can_be_switched_off(tiny_config, topology, generator, catalog) -> None:
    window = single_origin_window(tiny_config, origin=0)
    with_2pc = evaluate(catalog, window, generator, topology, CostConfig(two_phase_commit=True))
    without = evaluate(catalog, window, generator, topology, CostConfig(two_phase_commit=False))
    assert with_2pc.mean_txn_latency_ms > without.mean_txn_latency_ms
    assert with_2pc.cross_region_txn_fraction == without.cross_region_txn_fraction


def test_scattered_primaries_make_transactions_cross_region(catalog, topology, tiny_config, generator) -> None:
    window = single_origin_window(tiny_config, origin=0)
    scattered = evaluate(catalog, window, generator, topology, tiny_config.cost)
    assert scattered.cross_region_txn_fraction > 0.0

    collapsed = catalog.copy()
    _collapse_to_region(collapsed, 0)
    single = evaluate(collapsed, window, generator, topology, tiny_config.cost)
    assert single.cross_region_txn_fraction == 0.0
    assert single.mean_txn_latency_ms < scattered.mean_txn_latency_ms


# ----------------------------------------------------------- load and tails


def test_served_operations_are_conserved(catalog, topology, tiny_config, generator) -> None:
    window = single_origin_window(tiny_config, origin=2)
    result = evaluate(catalog, window, generator, topology, tiny_config.cost)
    assert result.ops_per_region.sum() > 0.0
    assert np.all(result.ops_per_region >= 0.0)


def test_storage_accounting_matches_the_replica_matrix(catalog, topology, tiny_config, generator) -> None:
    window = single_origin_window(tiny_config, origin=1)
    result = evaluate(catalog, window, generator, topology, tiny_config.cost)
    assert result.storage_bytes_per_region.sum() == pytest.approx(
        float((catalog.replicas.T * catalog.sizes_bytes).sum())
    )


def test_the_tail_is_never_below_the_mean_by_much(catalog, topology, tiny_config, generator) -> None:
    window = single_origin_window(tiny_config, origin=0)
    result = evaluate(catalog, window, generator, topology, tiny_config.cost)
    assert result.tail_latency_ms >= result.mean_latency_ms


def test_an_empty_window_is_rejected(catalog, topology, tiny_config, generator) -> None:
    window = single_origin_window(tiny_config, origin=0)
    empty = replace(window, reads=window.reads * 0, writes=window.writes * 0, txn_counts=window.txn_counts * 0)
    with pytest.raises(ValueError, match="no requests"):
        evaluate(catalog, empty, generator, topology, tiny_config.cost)


@pytest.mark.parametrize(
    "weights, percentile, expected",
    [
        # Definition: the smallest value whose cumulative weight reaches the
        # requested share. Half the mass sits exactly at 1.0, so the median is
        # 1.0, not 2.0.
        ([50.0, 40.0, 10.0], 0.0, 1.0),
        ([50.0, 40.0, 10.0], 50.0, 1.0),
        ([50.0, 40.0, 10.0], 51.0, 2.0),
        ([50.0, 40.0, 10.0], 95.0, 3.0),
        ([50.0, 40.0, 10.0], 100.0, 3.0),
        ([10.0, 40.0, 50.0], 50.0, 2.0),
        ([0.0, 0.0, 1.0], 95.0, 3.0),
    ],
)
def test_weighted_percentile_matches_hand_calculation(weights, percentile, expected) -> None:
    values = np.array([1.0, 2.0, 3.0])
    assert weighted_percentile(values, np.array(weights), percentile) == expected


def test_weighted_percentile_ignores_zero_weight_and_infinities() -> None:
    values = np.array([1.0, np.inf, 5.0])
    weights = np.array([1.0, 100.0, 0.0])
    assert weighted_percentile(values, weights, 99.0) == 1.0


def test_weighted_percentile_rejects_a_bad_percentile() -> None:
    with pytest.raises(ValueError, match="percentile"):
        weighted_percentile(np.array([1.0]), np.array([1.0]), 101.0)


def test_coefficient_of_variation_is_zero_when_even() -> None:
    assert coefficient_of_variation(np.array([4.0, 4.0, 4.0])) == 0.0
    assert coefficient_of_variation(np.zeros(3)) == 0.0
    assert coefficient_of_variation(np.array([0.0, 0.0, 9.0])) > 0.0
