"""The drifting demand model."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from shardmind.workload import TWO_PI, WorkloadGenerator


def _make(cfg, topology, seed=0, horizon=64, **workload_changes):
    workload = replace(cfg.workload, **workload_changes) if workload_changes else cfg.workload
    return WorkloadGenerator(workload, topology, np.random.default_rng(seed), horizon)


def test_same_seed_reproduces_the_window_exactly(tiny_config, topology) -> None:
    a = _make(tiny_config, topology, seed=3).window(11)
    b = _make(tiny_config, topology, seed=3).window(11)
    assert np.array_equal(a.reads, b.reads)
    assert np.array_equal(a.writes, b.writes)
    assert np.array_equal(a.txn_counts, b.txn_counts)


def test_different_seeds_give_different_workloads(tiny_config, topology) -> None:
    a = _make(tiny_config, topology, seed=3).window(11)
    b = _make(tiny_config, topology, seed=4).window(11)
    assert not np.allclose(a.reads, b.reads)


def test_repeated_calls_for_one_window_are_stable(generator) -> None:
    assert np.array_equal(generator.window(5).reads, generator.window(5).reads)


def test_request_counts_match_the_configured_volume(tiny_config, topology) -> None:
    window = _make(tiny_config, topology).window(0)
    assert window.total_requests == pytest.approx(tiny_config.workload.ops_per_window)


def test_read_write_split_follows_read_fraction(tiny_config, topology) -> None:
    cfg = tiny_config.workload
    window = _make(tiny_config, topology).window(0)
    single = window.reads.sum() + window.writes.sum()
    assert window.reads.sum() / single == pytest.approx(cfg.read_fraction)
    expected_single = cfg.ops_per_window * (1.0 - cfg.txn_fraction)
    assert single == pytest.approx(expected_single)


def test_traffic_moves_between_regions_over_a_diurnal_cycle(tiny_config, topology) -> None:
    gen = _make(tiny_config, topology)
    period = tiny_config.workload.diurnal_period_windows
    start = gen.window(0).reads.sum(axis=0)
    quarter = gen.window(period // 4).reads.sum(axis=0)
    start = start / start.sum()
    quarter = quarter / quarter.sum()
    assert np.abs(start - quarter).sum() > 0.05, "the centre of gravity should have moved"


def test_a_full_period_returns_the_field_to_its_starting_rotation(tiny_config, topology) -> None:
    period = tiny_config.workload.diurnal_period_windows
    gen = _make(tiny_config, topology, horizon=2 * period, spike_probability=0.0)
    assert gen.rotation(period) % TWO_PI == pytest.approx(0.0, abs=1e-9)
    assert np.allclose(gen.window(0).reads, gen.window(period).reads)


def test_zero_volatility_freezes_the_workload(tiny_config, topology) -> None:
    gen = _make(tiny_config, topology, volatility=0.0)
    assert np.allclose(gen.window(0).reads, gen.window(40).reads)
    assert np.allclose(gen.spike_multipliers, 1.0)


def test_volatility_accelerates_the_drift(tiny_config, topology) -> None:
    slow = _make(tiny_config, topology, volatility=1.0)
    fast = _make(tiny_config, topology, volatility=4.0)
    assert fast.rotation(10) == pytest.approx(4.0 * slow.rotation(10))


def test_spikes_raise_one_region_above_the_rest(tiny_config, topology) -> None:
    gen = _make(tiny_config, topology, spike_probability=1.0, spike_magnitude=10.0)
    first_window = gen.spike_multipliers[0]
    assert first_window.max() == pytest.approx(10.0), "the spike magnitude should be applied"
    assert first_window.min() == pytest.approx(1.0), "a spike should be localized, not global"
    assert np.count_nonzero(first_window > 1.0) == 1


def test_adjacent_cells_have_more_similar_angles_than_distant_ones(tiny_config, topology) -> None:
    gen = _make(tiny_config, topology, n_cells=256)
    angles = gen.cell_angles

    def circular_gap(a, b):
        d = np.abs(a - b) % TWO_PI
        return np.minimum(d, TWO_PI - d)

    neighbour = circular_gap(angles[:-1], angles[1:]).mean()
    shuffled = circular_gap(angles, np.roll(angles, 64)).mean()
    assert neighbour < shuffled, "the random walk must leave neighbouring cells correlated"


def test_popularity_is_skewed_not_uniform(generator) -> None:
    p = np.sort(generator.cell_popularity)[::-1]
    assert p.sum() == pytest.approx(1.0)
    top_decile = p[: max(1, len(p) // 10)].sum()
    assert top_decile > 0.10, "a Zipf keyspace should have hot cells"


def test_transaction_templates_touch_distinct_cells(generator, tiny_config) -> None:
    cells = generator.template_cells
    assert cells.shape == (
        tiny_config.workload.n_txn_templates,
        tiny_config.workload.txn_arity,
    )
    for row in cells:
        assert len(set(row.tolist())) == len(row), "a transaction cannot touch one cell twice"
    assert cells.min() >= 0 and cells.max() < tiny_config.workload.n_cells


def test_stochastic_counts_are_whole_requests(tiny_config, topology) -> None:
    gen = _make(tiny_config, topology, stochastic_counts=True)
    window = gen.window(0)
    total = window.reads + window.writes
    assert np.allclose(total, np.round(total))
    assert window.total_requests == pytest.approx(tiny_config.workload.ops_per_window, rel=0.01)


def test_requesting_a_window_beyond_the_horizon_is_an_error(tiny_config, topology) -> None:
    gen = _make(tiny_config, topology, horizon=10)
    with pytest.raises(IndexError, match="horizon"):
        gen.window(11)
