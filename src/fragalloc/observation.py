"""Encoding cluster state into the fixed-length vector the agent sees.

Every block is normalized into ``[0, 1]`` and the whole vector is clipped, so
the observation space is a unit box and no feature can dominate the input layer
by virtue of its units. Fragment-indexed blocks are padded to ``max_fragments``
and accompanied by an explicit active mask, because the fragment count is itself
something the agent changes: the observation has to have a fixed width while the
catalogue does not.

The layout is published as :attr:`ObservationEncoder.layout`, a mapping from
block name to slice, so that tests, plots and the eventual paper can address
features by name instead of by offset.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from fragalloc.catalog import FragmentCatalog
from fragalloc.config import FragAllocConfig
from fragalloc.cost import CostBreakdown
from fragalloc.topology import Topology
from fragalloc.workload import WorkloadGenerator, WorkloadWindow

EPS = 1e-12


@dataclass(frozen=True)
class _Block:
    name: str
    size: int
    doc: str


class ObservationEncoder:
    """Builds the agent's observation vector.

    Blocks, in order:

    ``read_demand``, ``write_demand``, ``txn_demand``
        ``(max_fragments, n_regions)`` demand by fragment and origin region,
        each scaled by its own maximum. This is the geographic access
        distribution: the signal that tells the agent where the traffic is.
    ``replicas``
        ``(max_fragments, n_regions)`` replica indicator.
    ``primary``
        ``(max_fragments, n_regions)`` one-hot primary region.
    ``active``
        ``(max_fragments,)`` which fragment slots exist.
    ``fragment_size``
        ``(max_fragments,)`` share of the keyspace each fragment holds.
    ``region_ops``
        ``(n_regions,)`` share of served operations landing in each region.
    ``region_storage``
        ``(n_regions,)`` storage utilization against per-region capacity.
    ``churn``
        ``(churn_history_windows,)`` recent per-window migration volume, newest
        first, scaled by the reward's migration scale.
    ``rtt``
        ``(n_regions ** 2,)`` the latency matrix, scaled by its maximum. Constant
        within an episode; included so a policy can in principle transfer across
        topologies, and a natural candidate for an ablation.
    ``scalars``
        seven summary figures: mean and tail latency, cross-region transaction
        fraction, load and storage imbalance, fragment count, episode progress.
    """

    def __init__(self, cfg: FragAllocConfig, topology: Topology) -> None:
        self.cfg = cfg
        self.topology = topology
        f = cfg.catalog.max_fragments
        r = cfg.n_regions
        h = cfg.episode.churn_history_windows

        blocks = [
            _Block("read_demand", f * r, "read demand by fragment and origin"),
            _Block("write_demand", f * r, "write demand by fragment and origin"),
            _Block("txn_demand", f * r, "transaction demand attributed to fragments"),
            _Block("replicas", f * r, "replica placement indicator"),
            _Block("primary", f * r, "primary region one-hot"),
            _Block("active", f, "fragment slot occupancy"),
            _Block("fragment_size", f, "share of keyspace per fragment"),
            _Block("region_ops", r, "share of served operations per region"),
            _Block("region_storage", r, "storage utilization per region"),
            _Block("churn", h, "recent migration volume, newest first"),
            _Block("rtt", r * r, "normalized inter-region latency matrix"),
            _Block("scalars", 7, "summary statistics"),
        ]

        self.blocks = tuple(blocks)
        self.layout: dict[str, slice] = {}
        offset = 0
        for block in blocks:
            self.layout[block.name] = slice(offset, offset + block.size)
            offset += block.size
        self.dim = offset

        #: Latency normalizer. A transaction can chain several member operations
        #: plus a commit round, so the worst case is several times the worst RTT.
        self.latency_scale_ms = topology.max_rtt * (cfg.workload.txn_arity + 2)

    # ---------------------------------------------------------------- encode

    def encode(
        self,
        catalog: FragmentCatalog,
        window: WorkloadWindow,
        generator: WorkloadGenerator,
        cost: CostBreakdown,
        churn_history: np.ndarray,
        progress: float,
    ) -> np.ndarray:
        cfg = self.cfg
        f_max = cfg.catalog.max_fragments
        r = cfg.n_regions
        n_frag = catalog.n_fragments

        obs = np.zeros(self.dim, dtype=np.float32)

        frag_reads = catalog.aggregate_cells(window.reads)
        frag_writes = catalog.aggregate_cells(window.writes)
        frag_txn = _txn_demand_by_fragment(catalog, generator, window, n_frag, r)

        self._set_matrix(obs, "read_demand", frag_reads, f_max, r)
        self._set_matrix(obs, "write_demand", frag_writes, f_max, r)
        self._set_matrix(obs, "txn_demand", frag_txn, f_max, r)
        self._set_matrix(obs, "replicas", catalog.replicas.astype(np.float64), f_max, r, scale=1.0)

        primary_onehot = np.zeros((n_frag, r), dtype=np.float64)
        primary_onehot[np.arange(n_frag), catalog.primary] = 1.0
        self._set_matrix(obs, "primary", primary_onehot, f_max, r, scale=1.0)

        active = np.zeros(f_max, dtype=np.float64)
        active[:n_frag] = 1.0
        obs[self.layout["active"]] = active

        sizes = np.zeros(f_max, dtype=np.float64)
        sizes[:n_frag] = catalog.sizes_cells / cfg.workload.n_cells
        obs[self.layout["fragment_size"]] = sizes

        ops = cost.ops_per_region
        obs[self.layout["region_ops"]] = ops / (ops.sum() + EPS)
        obs[self.layout["region_storage"]] = np.clip(
            cost.storage_bytes_per_region / self.topology.storage_capacity_bytes, 0.0, 1.0
        )

        # Churn is a dataset fraction for the same reason the reward's
        # migration term is: the observation space must mean the same thing in
        # the simulator and on the cluster or the pre-trained weights do not
        # transfer. One unit is the whole dataset moved within the history
        # window, which saturates the feature.
        obs[self.layout["churn"]] = np.clip(
            churn_history / cfg.catalog.dataset_bytes, 0.0, 1.0
        )
        obs[self.layout["rtt"]] = (self.topology.rtt / self.topology.max_rtt).ravel()

        obs[self.layout["scalars"]] = np.clip(
            np.array(
                [
                    cost.mean_latency_ms / self.latency_scale_ms,
                    cost.tail_latency_ms / self.latency_scale_ms,
                    cost.cross_region_txn_fraction,
                    cost.load_imbalance / 2.0,
                    cost.storage_imbalance / 2.0,
                    n_frag / f_max,
                    progress,
                ],
                dtype=np.float64,
            ),
            0.0,
            1.0,
        )

        return np.clip(obs, 0.0, 1.0, out=obs)

    def _set_matrix(
        self,
        obs: np.ndarray,
        name: str,
        values: np.ndarray,
        f_max: int,
        r: int,
        scale: float | None = None,
    ) -> None:
        padded = np.zeros((f_max, r), dtype=np.float64)
        padded[: values.shape[0]] = values
        divisor = scale if scale is not None else float(padded.max()) + EPS
        obs[self.layout[name]] = (padded / divisor).ravel()

    def describe(self) -> str:
        lines = [f"observation dim = {self.dim}"]
        for block in self.blocks:
            s = self.layout[block.name]
            lines.append(f"  {block.name:<15s} [{s.start:>4d}:{s.stop:<4d}]  {block.doc}")
        return "\n".join(lines)


def _txn_demand_by_fragment(
    catalog: FragmentCatalog,
    generator: WorkloadGenerator,
    window: WorkloadWindow,
    n_frag: int,
    n_regions: int,
) -> np.ndarray:
    """``(F, R)`` transaction demand attributed to each fragment it touches."""
    member_frag = catalog.cell_to_fragment()[generator.template_cells]  # (T, A)
    demand = np.zeros((n_frag, n_regions), dtype=np.float64)
    for a in range(member_frag.shape[1]):
        np.add.at(demand, member_frag[:, a], window.txn_counts)
    return demand
