"""Configuration validation and serialization."""

from __future__ import annotations

from dataclasses import replace

import pytest

from shardmind.config import CatalogConfig, ShardMindConfig, TopologyConfig, WorkloadConfig


def test_defaults_are_valid(default_config: ShardMindConfig) -> None:
    assert default_config.n_regions == 6
    assert default_config.catalog.initial_fragments <= default_config.catalog.max_fragments


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"workload": WorkloadConfig(read_fraction=1.5)}, "read_fraction"),
        ({"workload": WorkloadConfig(txn_arity=1)}, "txn_arity"),
        ({"workload": WorkloadConfig(volatility=-1.0)}, "volatility"),
        ({"catalog": CatalogConfig(initial_fragments=99)}, "initial_fragments"),
        ({"catalog": CatalogConfig(min_replicas=4, max_replicas=2)}, "min_replicas"),
        ({"topology": TopologyConfig(region_longitudes_deg=(0.0,))}, "same length"),
    ],
)
def test_invalid_configurations_are_rejected(kwargs, message) -> None:
    with pytest.raises(ValueError, match=message):
        ShardMindConfig(**kwargs)


def test_n_cells_must_admit_max_fragments() -> None:
    with pytest.raises(ValueError, match="n_cells"):
        ShardMindConfig(
            workload=WorkloadConfig(n_cells=4), catalog=CatalogConfig(max_fragments=20)
        )


def test_json_round_trip(tmp_path, default_config: ShardMindConfig) -> None:
    path = tmp_path / "cfg.json"
    default_config.save(path)
    restored = ShardMindConfig.load(path)
    assert restored == default_config


def test_evolve_replaces_only_named_fields(default_config: ShardMindConfig) -> None:
    changed = default_config.evolve(
        workload=replace(default_config.workload, volatility=4.0), seed=99
    )
    assert changed.workload.volatility == 4.0
    assert changed.seed == 99
    assert changed.catalog == default_config.catalog
    assert default_config.workload.volatility == 1.0, "the original must not be mutated"
