"""Configuration objects for every tunable in the simulator.

Every parameter the experiments sweep lives here, in a frozen dataclass, so a
run is fully described by one ``ShardMindConfig`` value. ``to_dict`` and
``from_dict`` round-trip through plain JSON, which keeps the experiment records
in ``results/`` readable without importing the package.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class TopologyConfig:
    """The cluster's regions and the latency between them."""

    region_names: tuple[str, ...] = (
        "us-east-1",
        "us-west-2",
        "eu-west-1",
        "eu-central-1",
        "ap-southeast-1",
        "ap-northeast-1",
    )
    #: Longitude of each region in degrees, used to place regions on the circle
    #: around which the workload centroid drifts.
    region_longitudes_deg: tuple[float, ...] = (-77.5, -122.7, -6.3, 8.7, 103.8, 139.7)
    #: Round-trip time charged for a request served inside its own region.
    intra_region_rtt_ms: float = 1.0
    #: Optional explicit RTT matrix in milliseconds. ``None`` uses the built-in
    #: table in :mod:`shardmind.topology`.
    rtt_matrix_ms: tuple[tuple[float, ...], ...] | None = None
    #: Per-region storage capacity as a multiple of an even share of the dataset.
    #: 2.0 means any one region may hold twice its fair share before it is full.
    storage_capacity_factor: float = 3.0


@dataclass(frozen=True)
class WorkloadConfig:
    """The geographically drifting request stream.

    The keyspace is divided into ``n_cells`` atomic cells. A cell is the finest
    unit the agent can move; a fragment is a contiguous run of cells. Each cell
    has an angular position on the same circle as the regions, so a cell's
    traffic originates predominantly from whichever regions sit near its angle.
    The whole angular field rotates over the diurnal period, which is what makes
    a placement chosen at time t wrong at time t + k.
    """

    n_cells: int = 256
    #: Total requests modelled per decision window.
    ops_per_window: float = 10_000.0
    #: Fraction of single-key operations that are reads (0.5 ~ YCSB-A, 0.95 ~ YCSB-B).
    read_fraction: float = 0.8
    #: Fraction of requests that are multi-fragment transactions rather than
    #: single-key operations. These are the requests that can incur 2PC.
    txn_fraction: float = 0.2
    #: Cells touched by one transaction.
    txn_arity: int = 3
    #: Number of distinct transaction templates drawn at episode start.
    n_txn_templates: int = 64
    #: How tightly a transaction's cells cluster in the keyspace. Smaller means
    #: more local transactions, which are easier to keep inside one region.
    txn_locality_cells: int = 16
    #: Zipf exponent governing how skewed cell popularity is.
    zipf_s: float = 0.9
    #: von Mises concentration: how tightly a cell's traffic clusters around its
    #: angle. 0 is uniform over all regions, large values are single-region.
    origin_concentration: float = 2.5
    #: Windows in one full diurnal cycle.
    diurnal_period_windows: int = 96
    #: Complete revolutions of the angular field per diurnal period.
    drift_laps_per_period: float = 1.0
    #: Standard deviation, in radians, of the random walk that gives adjacent
    #: cells correlated but non-identical angular positions. This is what makes
    #: splitting a fragment worthwhile: a wide fragment spans divergent angles.
    cell_angle_walk_sigma: float = 0.30
    #: Per-window probability that a localized spike begins in some region.
    spike_probability: float = 0.03
    #: Multiplier applied to an affected region's traffic during a spike.
    spike_magnitude: float = 5.0
    #: Windows a spike lasts.
    spike_duration_windows: int = 6
    #: Primary sweep dimension. Scales drift speed, spike rate and spike size
    #: together, so one number moves the environment from placid to violent.
    volatility: float = 1.0
    #: If True, window counts are multinomial samples around the intensity
    #: field. If False, the expected intensities are used directly, which
    #: removes sampling noise from the reward signal.
    stochastic_counts: bool = False


@dataclass(frozen=True)
class CatalogConfig:
    """Fragment granularity and replication limits."""

    initial_fragments: int = 6
    max_fragments: int = 20
    min_replicas: int = 2
    max_replicas: int = 4
    #: Total logical dataset size. Migration cost is expressed as a fraction
    #: of this, never in bytes, so that a 60 GB simulator and a 1 GB cluster
    #: produce rewards on the same scale. See :class:`RewardConfig`.
    dataset_bytes: float = 6.0e10
    #: How the initial fragments are placed: ``"hash"`` spreads primaries round
    #: robin over regions, as a consistent-hash partitioner would;
    #: ``"single_region"`` puts everything in region 0.
    initial_placement: Literal["hash", "single_region"] = "hash"


@dataclass(frozen=True)
class CostConfig:
    """How a placement is turned into latency."""

    #: ``"nearest_replica"`` lets a read be served by any replica, which is the
    #: optimistic case and the one that rewards replication. ``"primary_only"``
    #: forces linearizable reads through the primary.
    read_consistency: Literal["nearest_replica", "primary_only"] = "nearest_replica"
    #: ``"majority"`` waits for a quorum of replicas to acknowledge a write,
    #: ``"all"`` for every replica, ``"primary"`` for none (asynchronous).
    write_ack: Literal["majority", "all", "primary"] = "majority"
    #: Charge two-phase commit for transactions whose participants' primaries
    #: span more than one region.
    two_phase_commit: bool = True
    #: Latency percentile reported alongside the mean.
    tail_percentile: float = 95.0


@dataclass(frozen=True)
class RewardConfig:
    """Scalarization of the cost vector into a single reward.

    The three weights are the sweep that Objective 5 traces: raising
    ``w_migration`` buys stability at the price of responsiveness.
    """

    w_latency: float = 1.0
    w_migration: float = 0.30
    w_imbalance: float = 0.10
    #: Divisors that put each term on a comparable scale before weighting.
    latency_scale_ms: float = 100.0
    #: Migration is charged as ``bytes_moved / (dataset_bytes * this)``, that
    #: is, as a fraction of the whole dataset rather than in bytes. The
    #: simulator holds 60 GB and the CockroachDB cluster will hold one or two;
    #: in bytes the same physical move would score sixty times differently in
    #: the two environments, and a pre-trained Q-function would have to unlearn
    #: the difference during fine-tuning. That is precisely the transfer
    #: failure ADR-0009 chose CockroachDB to avoid. The default divisor of
    #: 1/6 sets the unit of migration cost at one sixth of the dataset, which
    #: is one fragment at the default granularity, so a reward of -1 in this
    #: term means "a typical fragment moved".
    migration_scale_fraction: float = 1.0 / 6.0
    #: Cost charged when an action is inapplicable in the current state and
    #: resolves to a no-op. Small, per the declarative action semantics: an
    #: inapplicable action should be uninteresting, not catastrophic.
    inapplicable_action_cost: float = 0.02


@dataclass(frozen=True)
class EpisodeConfig:
    """Episode shape."""

    #: Decision windows per episode. One action is taken per window.
    windows_per_episode: int = 200
    #: Windows simulated before the agent's first action, so the observation at
    #: t = 0 already reflects a real workload rather than an empty one.
    warmup_windows: int = 4
    #: Windows of migration volume kept in the observation's churn feature.
    churn_history_windows: int = 8


@dataclass(frozen=True)
class ShardMindConfig:
    """The complete description of one experimental configuration."""

    topology: TopologyConfig = field(default_factory=TopologyConfig)
    workload: WorkloadConfig = field(default_factory=WorkloadConfig)
    catalog: CatalogConfig = field(default_factory=CatalogConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    reward: RewardConfig = field(default_factory=RewardConfig)
    episode: EpisodeConfig = field(default_factory=EpisodeConfig)
    seed: int = 0

    def __post_init__(self) -> None:
        t, w, c = self.topology, self.workload, self.catalog
        if len(t.region_names) != len(t.region_longitudes_deg):
            raise ValueError("region_names and region_longitudes_deg must be the same length")
        if len(t.region_names) < 2:
            raise ValueError("at least two regions are required")
        if not 0.0 <= w.read_fraction <= 1.0:
            raise ValueError("read_fraction must lie in [0, 1]")
        if not 0.0 <= w.txn_fraction <= 1.0:
            raise ValueError("txn_fraction must lie in [0, 1]")
        if w.txn_arity < 2:
            raise ValueError("txn_arity must be at least 2 for a transaction to be distributed")
        if w.n_cells < c.max_fragments:
            raise ValueError("n_cells must be at least max_fragments; a fragment holds >= 1 cell")
        if not 1 <= c.initial_fragments <= c.max_fragments:
            raise ValueError("initial_fragments must lie in [1, max_fragments]")
        if not 1 <= c.min_replicas <= c.max_replicas <= len(t.region_names):
            raise ValueError("require 1 <= min_replicas <= max_replicas <= n_regions")
        if w.volatility < 0.0:
            raise ValueError("volatility must be non-negative")

    @property
    def n_regions(self) -> int:
        return len(self.topology.region_names)

    def evolve(self, **changes: Any) -> "ShardMindConfig":
        """Return a copy with top-level fields replaced.

        Nested changes are expressed by passing a whole replacement sub-config::

            cfg.evolve(workload=replace(cfg.workload, volatility=2.0))
        """
        return replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShardMindConfig":
        def tup(x: Any) -> Any:
            return tuple(tup(i) for i in x) if isinstance(x, list) else x

        return cls(
            topology=TopologyConfig(**{k: tup(v) for k, v in data.get("topology", {}).items()}),
            workload=WorkloadConfig(**data.get("workload", {})),
            catalog=CatalogConfig(**data.get("catalog", {})),
            cost=CostConfig(**data.get("cost", {})),
            reward=RewardConfig(**data.get("reward", {})),
            episode=EpisodeConfig(**data.get("episode", {})),
            seed=data.get("seed", 0),
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "ShardMindConfig":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
