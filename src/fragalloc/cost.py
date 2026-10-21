"""Turning a placement and a window of demand into latency, load and tail.

The model is analytic, not discrete-event. For a given placement every request
class has a closed-form latency, and a window of demand is a weighted count over
those classes. One evaluation is a handful of matrix operations over arrays of
shape ``(fragments, regions)``, which is what lets an episode of two hundred
windows finish in milliseconds.

Charges
-------
read
    ``rtt[origin, s]`` where ``s`` is the nearest region holding a replica, or
    the primary under ``read_consistency="primary_only"``.
write
    ``rtt[origin, primary]`` to reach the leader, plus the replication term: the
    slowest acknowledgement under ``write_ack="all"``, the quorum-th fastest
    under ``"majority"``, nothing under ``"primary"``.
transaction
    the sum of its member operations' latencies, plus, when the primaries of the
    fragments it touches span more than one region, a two-phase commit charge of
    ``rtt[origin, c] + 2 * max_p rtt[c, p]`` over participant regions ``p``,
    minimized over the choice of coordinator ``c``. A transaction whose
    participants all sit in one region commits locally and pays nothing extra,
    which is precisely the effect Lion exploits and the reason fragmentation
    granularity matters here.

What is deliberately absent
---------------------------
Queueing, and therefore congestion collapse. Load appears only as an imbalance
term in the reward, never as a latency penalty. The model is a latency model,
not a throughput model, and results should be read as such. ADR-0004 records why.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from fragalloc.config import CostConfig
from fragalloc.catalog import FragmentCatalog
from fragalloc.topology import Topology
from fragalloc.workload import WorkloadGenerator, WorkloadWindow


@dataclass(frozen=True)
class CostBreakdown:
    """Every quantity one window of demand produces under one placement."""

    mean_latency_ms: float
    tail_latency_ms: float
    mean_read_latency_ms: float
    mean_write_latency_ms: float
    mean_txn_latency_ms: float
    total_requests: float
    #: Fraction of transaction requests whose participants span >1 region.
    cross_region_txn_fraction: float
    #: ``(R,)`` operations served by each region, replication included.
    ops_per_region: np.ndarray
    #: ``(R,)`` bytes stored in each region.
    storage_bytes_per_region: np.ndarray
    #: Coefficient of variation of ``ops_per_region``. 0 is perfectly even.
    load_imbalance: float
    #: Coefficient of variation of ``storage_bytes_per_region``.
    storage_imbalance: float


def read_latency(catalog: FragmentCatalog, topology: Topology, cfg: CostConfig) -> np.ndarray:
    """``(F, R)`` read latency by fragment and origin region."""
    if cfg.read_consistency == "primary_only":
        return topology.rtt[:, catalog.primary].T.copy()
    masked = np.where(catalog.replicas[:, None, :], topology.rtt[None, :, :], np.inf)
    return masked.min(axis=2)


def read_serving_region(
    catalog: FragmentCatalog, topology: Topology, cfg: CostConfig
) -> np.ndarray:
    """``(F, R)`` region that actually serves a read, by fragment and origin."""
    if cfg.read_consistency == "primary_only":
        return np.broadcast_to(catalog.primary[:, None], (catalog.n_fragments, topology.n_regions))
    masked = np.where(catalog.replicas[:, None, :], topology.rtt[None, :, :], np.inf)
    return masked.argmin(axis=2)


def replication_term(catalog: FragmentCatalog, topology: Topology, cfg: CostConfig) -> np.ndarray:
    """``(F,)`` time the leader waits for acknowledgements before committing."""
    f = catalog.n_fragments
    term = np.zeros(f, dtype=np.float64)
    if cfg.write_ack == "primary":
        return term

    for i in range(f):
        primary = int(catalog.primary[i])
        followers = np.flatnonzero(catalog.replicas[i])
        followers = followers[followers != primary]
        if followers.size == 0:
            continue
        acks = np.sort(topology.rtt[primary, followers])
        if cfg.write_ack == "all":
            term[i] = acks[-1]
        else:  # majority, counting the leader's own vote
            n_replicas = followers.size + 1
            needed = (n_replicas // 2 + 1) - 1  # follower acks required
            term[i] = acks[needed - 1] if needed > 0 else 0.0
    return term


def write_latency(catalog: FragmentCatalog, topology: Topology, cfg: CostConfig) -> np.ndarray:
    """``(F, R)`` write latency by fragment and origin region."""
    to_leader = topology.rtt[:, catalog.primary].T  # (F, R)
    return to_leader + replication_term(catalog, topology, cfg)[:, None]


def transaction_latency(
    catalog: FragmentCatalog,
    generator: WorkloadGenerator,
    topology: Topology,
    cfg: CostConfig,
    read_lat: np.ndarray,
    write_lat: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """``(T, R)`` transaction latency and ``(T,)`` cross-region participation mask."""
    cell_to_frag = catalog.cell_to_fragment()
    member_frag = cell_to_frag[generator.template_cells]  # (T, A)
    is_write = generator.template_is_write[:, :, None]  # (T, A, 1)

    member_lat = np.where(is_write, write_lat[member_frag], read_lat[member_frag])
    total = member_lat.sum(axis=1)  # (T, R)

    n_templates = member_frag.shape[0]
    participants = np.zeros((n_templates, topology.n_regions), dtype=bool)
    participants[np.arange(n_templates)[:, None], catalog.primary[member_frag]] = True
    multi_region = participants.sum(axis=1) > 1

    if cfg.two_phase_commit and np.any(multi_region):
        # farthest[t, c]: slowest participant as seen from candidate coordinator c
        farthest = np.max(
            np.where(participants[:, None, :], topology.rtt[None, :, :], -np.inf), axis=2
        )
        # cost[t, o, c] = reach the coordinator, then prepare and commit rounds
        cost = topology.rtt[None, :, :] + 2.0 * farthest[:, None, :]
        cost = np.where(participants[:, None, :], cost, np.inf)
        coordination = cost.min(axis=2)  # (T, R)
        total = total + np.where(multi_region[:, None], coordination, 0.0)

    return total, multi_region


def evaluate(
    catalog: FragmentCatalog,
    window: WorkloadWindow,
    generator: WorkloadGenerator,
    topology: Topology,
    cfg: CostConfig,
) -> CostBreakdown:
    """Score one placement against one window of demand."""
    read_lat = read_latency(catalog, topology, cfg)
    write_lat = write_latency(catalog, topology, cfg)
    txn_lat, multi_region = transaction_latency(
        catalog, generator, topology, cfg, read_lat, write_lat
    )

    frag_reads = catalog.aggregate_cells(window.reads)
    frag_writes = catalog.aggregate_cells(window.writes)
    txn_counts = window.txn_counts

    read_total = float(frag_reads.sum())
    write_total = float(frag_writes.sum())
    txn_total = float(txn_counts.sum())
    requests = read_total + write_total + txn_total
    if requests <= 0.0:
        raise ValueError("workload window contains no requests")

    read_ms = float((frag_reads * read_lat).sum())
    write_ms = float((frag_writes * write_lat).sum())
    txn_ms = float((txn_counts * txn_lat).sum())

    values = np.concatenate([read_lat.ravel(), write_lat.ravel(), txn_lat.ravel()])
    weights = np.concatenate([frag_reads.ravel(), frag_writes.ravel(), txn_counts.ravel()])

    ops_per_region = _ops_per_region(
        catalog, generator, topology, cfg, frag_reads, frag_writes, txn_counts
    )
    storage = catalog.storage_bytes_per_region()

    cross_region = float((txn_counts.sum(axis=1) * multi_region).sum())

    return CostBreakdown(
        mean_latency_ms=(read_ms + write_ms + txn_ms) / requests,
        tail_latency_ms=weighted_percentile(values, weights, cfg.tail_percentile),
        mean_read_latency_ms=read_ms / read_total if read_total > 0 else 0.0,
        mean_write_latency_ms=write_ms / write_total if write_total > 0 else 0.0,
        mean_txn_latency_ms=txn_ms / txn_total if txn_total > 0 else 0.0,
        total_requests=requests,
        cross_region_txn_fraction=cross_region / txn_total if txn_total > 0 else 0.0,
        ops_per_region=ops_per_region,
        storage_bytes_per_region=storage,
        load_imbalance=coefficient_of_variation(ops_per_region),
        storage_imbalance=coefficient_of_variation(storage),
    )


def _ops_per_region(
    catalog: FragmentCatalog,
    generator: WorkloadGenerator,
    topology: Topology,
    cfg: CostConfig,
    frag_reads: np.ndarray,
    frag_writes: np.ndarray,
    txn_counts: np.ndarray,
) -> np.ndarray:
    """Work landing on each region: reads at their serving replica, writes everywhere."""
    n_regions = topology.n_regions
    ops = np.zeros(n_regions, dtype=np.float64)

    serving = read_serving_region(catalog, topology, cfg)  # (F, R)
    np.add.at(ops, serving.ravel(), frag_reads.ravel())

    # A write is applied by every replica, not only the leader.
    ops += catalog.replicas.T.astype(np.float64) @ frag_writes.sum(axis=1)

    # Transaction members land the same way as their single-key counterparts.
    cell_to_frag = catalog.cell_to_fragment()
    member_frag = cell_to_frag[generator.template_cells]  # (T, A)
    per_template = txn_counts.sum(axis=1)  # (T,)
    for a in range(member_frag.shape[1]):
        frags = member_frag[:, a]
        writes = generator.template_is_write[:, a]
        # reads: attribute to the serving replica for the template's modal origin
        modal_origin = txn_counts.argmax(axis=1)
        read_targets = serving[frags, modal_origin]
        np.add.at(ops, read_targets[~writes], per_template[~writes])
        if np.any(writes):
            ops += catalog.replicas[frags[writes]].T.astype(np.float64) @ per_template[writes]
    return ops


def coefficient_of_variation(values: np.ndarray) -> float:
    """Standard deviation over mean. Scale-free, and 0 when perfectly even."""
    mean = float(np.mean(values))
    if mean <= 0.0:
        return 0.0
    return float(np.std(values) / mean)


def weighted_percentile(values: np.ndarray, weights: np.ndarray, percentile: float) -> float:
    """Exact percentile of a discrete weighted distribution.

    Every request class has a known latency and a known count, so the latency
    distribution is discrete and its quantiles are exact. No sampling required.
    """
    if not 0.0 <= percentile <= 100.0:
        raise ValueError("percentile must lie in [0, 100]")
    finite = np.isfinite(values) & (weights > 0.0)
    if not np.any(finite):
        return 0.0
    v, w = values[finite], weights[finite]
    order = np.argsort(v, kind="stable")
    v, w = v[order], w[order]
    cumulative = np.cumsum(w)
    threshold = (percentile / 100.0) * cumulative[-1]
    return float(v[int(np.searchsorted(cumulative, threshold, side="left"))])
