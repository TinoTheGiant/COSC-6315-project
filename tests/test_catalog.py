"""Fragment catalogue invariants and the cost of each mutation."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from shardmind.catalog import FragmentCatalog, _even_boundaries
from shardmind.config import CatalogConfig


@pytest.fixture
def catalog(tiny_config):
    return FragmentCatalog(tiny_config.catalog, tiny_config.workload.n_cells, tiny_config.n_regions)


def test_fragments_partition_the_keyspace(catalog) -> None:
    assert catalog.boundaries[0] == 0
    assert catalog.boundaries[-1] == catalog.n_cells
    assert np.all(np.diff(catalog.boundaries) >= 1)
    assert catalog.sizes_cells.sum() == catalog.n_cells
    assert len(catalog.cell_to_fragment()) == catalog.n_cells


def test_initial_hash_placement_spreads_primaries(catalog) -> None:
    assert len(set(catalog.primary.tolist())) == min(catalog.n_fragments, catalog.n_regions)
    catalog.validate()


def test_single_region_placement_puts_everything_in_region_zero(tiny_config) -> None:
    cfg = replace(tiny_config.catalog, initial_placement="single_region")
    cat = FragmentCatalog(cfg, tiny_config.workload.n_cells, tiny_config.n_regions)
    assert np.all(cat.primary == 0)


def test_sizes_in_bytes_sum_to_the_dataset(catalog, tiny_config) -> None:
    assert catalog.sizes_bytes.sum() == pytest.approx(tiny_config.catalog.dataset_bytes)


def test_aggregate_cells_sums_each_fragments_rows(catalog) -> None:
    per_cell = np.arange(catalog.n_cells * catalog.n_regions, dtype=float)
    per_cell = per_cell.reshape(catalog.n_cells, catalog.n_regions)
    aggregated = catalog.aggregate_cells(per_cell)
    assert aggregated.shape == (catalog.n_fragments, catalog.n_regions)
    assert aggregated.sum() == pytest.approx(per_cell.sum())
    lo, hi = catalog.boundaries[1], catalog.boundaries[2]
    assert np.allclose(aggregated[1], per_cell[lo:hi].sum(axis=0))


def test_aggregate_rejects_a_mismatched_array(catalog) -> None:
    with pytest.raises(ValueError, match="leading axis"):
        catalog.aggregate_cells(np.zeros((catalog.n_cells + 1, catalog.n_regions)))


# --------------------------------------------------------------------- split


def test_split_is_free_and_preserves_placement(catalog) -> None:
    before = catalog.n_fragments
    primary, replicas = int(catalog.primary[1]), catalog.replicas[1].copy()

    result = catalog.split(1)

    assert result.applied and result.bytes_moved == 0.0
    assert catalog.n_fragments == before + 1
    assert catalog.primary[1] == primary and catalog.primary[2] == primary
    assert np.array_equal(catalog.replicas[1], replicas)
    assert np.array_equal(catalog.replicas[2], replicas)
    catalog.validate()


def test_split_refuses_a_single_cell_fragment(tiny_config) -> None:
    cfg = replace(tiny_config.catalog, initial_fragments=8, max_fragments=32)
    cat = FragmentCatalog(cfg, 8, tiny_config.n_regions)
    assert cat.split(0).reason == "fragment is a single cell"


def test_split_refuses_at_the_fragment_cap(tiny_config) -> None:
    cfg = replace(tiny_config.catalog, initial_fragments=4, max_fragments=4)
    cat = FragmentCatalog(cfg, tiny_config.workload.n_cells, tiny_config.n_regions)
    assert not cat.split(0).applied
    assert cat.n_fragments == 4


# --------------------------------------------------------------------- merge


def test_merge_recombines_adjacent_fragments(catalog) -> None:
    before = catalog.n_fragments
    lo, hi = int(catalog.boundaries[1]), int(catalog.boundaries[3])
    assert catalog.merge(1).applied
    assert catalog.n_fragments == before - 1
    assert (int(catalog.boundaries[1]), int(catalog.boundaries[2])) == (lo, hi)
    catalog.validate()


def test_merge_charges_for_data_the_left_replica_set_must_acquire(catalog) -> None:
    right_bytes = float(catalog.sizes_bytes[2])
    newly_covered = int(np.count_nonzero(catalog.replicas[1] & ~catalog.replicas[2]))
    result = catalog.merge(1)
    assert result.bytes_moved == pytest.approx(right_bytes * newly_covered)


def test_merge_is_free_when_both_halves_already_agree(catalog) -> None:
    catalog.split(0)
    assert catalog.merge(0).bytes_moved == 0.0


def test_merge_refuses_the_last_fragment(catalog) -> None:
    assert catalog.merge(catalog.n_fragments - 1).reason == "no right neighbour"


def test_split_then_merge_restores_the_catalogue(catalog) -> None:
    boundaries = catalog.boundaries.copy()
    primary = catalog.primary.copy()
    replicas = catalog.replicas.copy()

    catalog.split(2)
    catalog.merge(2)

    assert np.array_equal(catalog.boundaries, boundaries)
    assert np.array_equal(catalog.primary, primary)
    assert np.array_equal(catalog.replicas, replicas)


# ----------------------------------------------------------------- placement


def test_ensure_replica_costs_the_fragment_size(catalog) -> None:
    target = int(np.flatnonzero(~catalog.replicas[0])[0])
    result = catalog.ensure_replica(0, target)
    assert result.applied
    assert result.bytes_moved == pytest.approx(catalog.sizes_bytes[0])
    assert catalog.replicas[0, target]


def test_ensure_replica_is_idempotent(catalog) -> None:
    held = int(catalog.primary[0])
    result = catalog.ensure_replica(0, held)
    assert not result.applied and result.bytes_moved == 0.0


def test_ensure_replica_refuses_beyond_max_replicas(tiny_config) -> None:
    cfg = replace(tiny_config.catalog, min_replicas=1, max_replicas=1)
    cat = FragmentCatalog(cfg, tiny_config.workload.n_cells, tiny_config.n_regions)
    target = int(np.flatnonzero(~cat.replicas[0])[0])
    assert cat.ensure_replica(0, target).reason == "at max_replicas"


def test_drop_replica_is_free(catalog) -> None:
    catalog.ensure_replica(0, int(np.flatnonzero(~catalog.replicas[0])[0]))
    victim = int(np.flatnonzero(catalog.replicas[0] & (np.arange(catalog.n_regions) != catalog.primary[0]))[0])
    result = catalog.drop_replica(0, victim)
    assert result.applied and result.bytes_moved == 0.0


def test_drop_replica_refuses_the_primary(catalog) -> None:
    assert catalog.drop_replica(0, int(catalog.primary[0])).reason == "cannot drop the primary"


def test_drop_replica_refuses_at_min_replicas(tiny_config) -> None:
    cfg = replace(tiny_config.catalog, min_replicas=2, max_replicas=3)
    cat = FragmentCatalog(cfg, tiny_config.workload.n_cells, tiny_config.n_regions)
    non_primary = int(np.flatnonzero(cat.replicas[0])[-1])
    if non_primary == cat.primary[0]:
        non_primary = int(np.flatnonzero(cat.replicas[0])[0])
    assert cat.drop_replica(0, non_primary).reason == "at min_replicas"


def test_set_primary_to_a_region_already_holding_a_replica_is_free(catalog) -> None:
    others = np.flatnonzero(catalog.replicas[0] & (np.arange(catalog.n_regions) != catalog.primary[0]))
    if others.size == 0:
        pytest.skip("fragment has a single replica under this configuration")
    result = catalog.set_primary(0, int(others[0]))
    assert result.applied and result.bytes_moved == 0.0
    assert catalog.primary[0] == others[0]


def test_set_primary_to_a_fresh_region_costs_a_copy(catalog) -> None:
    target = int(np.flatnonzero(~catalog.replicas[0])[0])
    result = catalog.set_primary(0, target)
    assert result.bytes_moved == pytest.approx(catalog.sizes_bytes[0])
    assert catalog.primary[0] == target and catalog.replicas[0, target]
    catalog.validate()


def test_set_primary_at_max_replicas_evicts_the_outgoing_leader(tiny_config) -> None:
    cfg = replace(tiny_config.catalog, min_replicas=2, max_replicas=2)
    cat = FragmentCatalog(cfg, tiny_config.workload.n_cells, tiny_config.n_regions)
    old = int(cat.primary[0])
    target = int(np.flatnonzero(~cat.replicas[0])[0])

    assert cat.set_primary(0, target).applied
    assert not cat.replicas[0, old], "the demoted leader's replica makes room for the new one"
    assert cat.replica_counts[0] == 2
    cat.validate()


def test_set_primary_is_idempotent(catalog) -> None:
    assert not catalog.set_primary(0, int(catalog.primary[0])).applied


# --------------------------------------------------------------------- fuzz


def test_invariants_survive_a_long_random_mutation_sequence(tiny_config) -> None:
    cat = FragmentCatalog(
        tiny_config.catalog, tiny_config.workload.n_cells, tiny_config.n_regions
    )
    rng = np.random.default_rng(0)
    ops = ["split", "merge", "set_primary", "ensure_replica", "drop_replica"]

    for _ in range(2000):
        op = ops[rng.integers(len(ops))]
        fragment = int(rng.integers(cat.n_fragments))
        if op in ("split", "merge"):
            getattr(cat, op)(fragment)
        else:
            getattr(cat, op)(fragment, int(rng.integers(cat.n_regions)))
        cat.validate()


def test_out_of_range_indices_raise(catalog) -> None:
    with pytest.raises(IndexError):
        catalog.set_primary(catalog.n_fragments, 0)
    with pytest.raises(IndexError):
        catalog.ensure_replica(0, catalog.n_regions)


def test_copy_is_independent(catalog) -> None:
    clone = catalog.copy()
    clone.split(0)
    assert clone.n_fragments == catalog.n_fragments + 1


def test_even_boundaries_are_balanced() -> None:
    b = _even_boundaries(100, 7)
    assert b[0] == 0 and b[-1] == 100
    assert np.diff(b).max() - np.diff(b).min() <= 1
