"""The cluster as a Gymnasium environment, interchangeable with the simulator's.

Harness piece 4 (docs/harness-architecture.md, step protocol). Same observation
space, same action space, same reward function (``fragalloc.reward``), same
workload generator and seeds. What differs is where latency comes from: the
cost model in ``fragalloc.env``, CockroachDB here. A model trained on one loads
and runs on the other with no adapter, which ``tests/test_harness_env.py``
checks against the simulator environment directly.

One step:

1-5. the executor plans the action with the simulator's own ``ActionSpace``,
     runs it, reads placement back and reconciles (``Executor.step``);
6.   the workload advances one window, open loop (ADR-0006);
7.   the driver samples ``N`` requests from that window and times them on the
     cluster (``Driver``, ADR-0017);
8.   the reward is ``fragalloc.reward.reward`` over the measured mean latency
     and the load the requests put on each region;
9.   the observation is the unchanged ``ObservationEncoder`` over the
     reconciled catalogue and a :class:`MeasuredCost`;
10.  ``info`` carries the outcome class, any divergence, and the drive summary.

Load per region is counted, not measured: each request that was actually sent
is attributed to the regions that served it under the read-back placement
(reads at the leaseholder, or the nearest replica under follower reads; writes
at every replica). That is the simulator's accounting rule applied to real
requests on the real placement, so the imbalance term means the same thing on
both sides. Storage per region is the catalogue's account, as in the simulator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from fragalloc.actions import ActionSpace
from fragalloc.catalog import FragmentCatalog
from fragalloc.config import FragAllocConfig
from fragalloc.harness.cluster import converge_replication
from fragalloc.harness.driver import READ, READ_MODES, TXN, Driver, Request, percentile, \
    sample_requests
from fragalloc.harness.executor import APPLIED, Executor
from fragalloc.harness.placement import Sql, StoreMap, TableLayout, create_table
from fragalloc.observation import ObservationEncoder
from fragalloc.reward import reward
from fragalloc.topology import Topology, build_topology
from fragalloc.workload import WorkloadGenerator


@dataclass(frozen=True)
class MeasuredCost:
    """The fields ``ObservationEncoder`` reads, filled from the cluster.

    Named apart from the cost model's ``CostBreakdown`` so a measured number
    can never be mistaken for a modelled one in a log or a figure.
    """

    mean_latency_ms: float
    tail_latency_ms: float
    cross_region_txn_fraction: float
    ops_per_region: np.ndarray
    storage_bytes_per_region: np.ndarray
    load_imbalance: float
    storage_imbalance: float
    n_requests: int


def coefficient_of_variation(values: np.ndarray) -> float:
    mean = float(np.mean(values))
    return 0.0 if mean <= 0.0 else float(np.std(values) / mean)


def serving_regions(catalog: FragmentCatalog, rtt: np.ndarray, follower: bool) -> np.ndarray:
    """``(F, R)``: the region that serves a read of fragment f from origin r."""
    n_frag, n_reg = catalog.replicas.shape
    if not follower:
        return np.broadcast_to(catalog.primary[:, None], (n_frag, n_reg))
    masked = np.where(catalog.replicas[:, None, :], rtt[None, :, :], np.inf)
    return masked.argmin(axis=2)


def account(requests: list[Request], catalog: FragmentCatalog, rtt: np.ndarray,
            follower: bool) -> tuple[np.ndarray, float]:
    """Ops landing on each region, and the fraction of transactions spanning regions."""
    n_reg = catalog.replicas.shape[1]
    ops = np.zeros(n_reg)
    cell_to_frag = catalog.cell_to_fragment()
    serve = serving_regions(catalog, rtt, follower)
    lease = serving_regions(catalog, rtt, False)
    txns = cross = 0
    for req in requests:
        frags = [int(cell_to_frag[c]) for c in req.cells]
        for f, w in zip(frags, req.writes):
            if w:
                ops += catalog.replicas[f]
            else:
                # Only reads in read-only work can be follower reads.
                ok_follower = req.kind == READ or (req.kind == TXN and req.read_only)
                ops[(serve if ok_follower else lease)[f, req.origin]] += 1
        if req.kind == TXN:
            txns += 1
            cross += len({int(catalog.primary[f]) for f in frags}) > 1
    return ops, (cross / txns if txns else 0.0)


class ClusterFragAllocEnv(gym.Env):
    """``FragAlloc-v0`` with CockroachDB in place of the cost model."""

    metadata = {"render_modes": ["ansi"]}

    def __init__(self, config: FragAllocConfig, sql: Sql, stores: StoreMap,
                 connect: Callable[[int], Sql], *, n_transactions: int,
                 concurrency: int = 2, lease_source: str = "builtin",
                 layout: TableLayout | None = None, rebuild_table: bool = True,
                 executor_kwargs: dict | None = None) -> None:
        super().__init__()
        self.cfg = config
        self.sql, self.stores = sql, stores
        self.layout = layout or TableLayout.from_config(config)
        self.topology: Topology = build_topology(config.topology, config.catalog.dataset_bytes)
        self.encoder = ObservationEncoder(config, self.topology)
        self.space = ActionSpace(config.catalog.max_fragments, config.n_regions)
        self.observation_space = spaces.Box(0.0, 1.0, shape=(self.encoder.dim,),
                                            dtype=np.float32)
        self.action_space = spaces.Discrete(self.space.n)
        self.read_mode = READ_MODES[config.cost.read_consistency]
        self.n_transactions = int(n_transactions)
        self.rebuild_table = rebuild_table
        self.executor = Executor(sql, stores, self.layout, config, lease_source=lease_source,
                                 **(executor_kwargs or {}))
        self.driver = Driver(connect, stores, self.layout, concurrency=concurrency,
                             read_mode=self.read_mode)
        self.catalog: FragmentCatalog | None = None
        self.generator: WorkloadGenerator | None = None
        self.churn = np.zeros(config.episode.churn_history_windows)
        self._t = self._steps = 0
        self._rng = np.random.default_rng(0)
        self._last_cost: MeasuredCost | None = None

    # ------------------------------------------------------------------ core

    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None):
        super().reset(seed=seed)
        cfg = self.cfg
        s = cfg.seed if seed is None else seed
        horizon = cfg.episode.warmup_windows + cfg.episode.windows_per_episode + 1
        # The simulator's construction exactly: same seed, same generator draws.
        self.generator = WorkloadGenerator(cfg.workload, self.topology,
                                           np.random.default_rng(s), horizon)
        self._rng = np.random.default_rng((s, 7919))
        target = FragmentCatalog(cfg.catalog, cfg.workload.n_cells, cfg.n_regions)
        if self.rebuild_table:
            create_table(self.sql, self.layout, target.boundaries)
            converge_replication(self.sql, self.layout, int(target.replica_counts[0]))
        self.catalog = self.executor.place(target)
        self.churn = np.zeros(cfg.episode.churn_history_windows)
        self._t, self._steps = cfg.episode.warmup_windows, 0
        cost, drive = self._measure()
        info = {"reward": 0.0, "drive": drive.summary(), "window": self._t}
        return self._observe(cost), info

    def step(self, action: int):
        action = int(action)
        out = self.executor.step(self.catalog, action)
        self.catalog = out.catalog
        self.churn = np.roll(self.churn, 1)
        self.churn[0] = out.bytes_moved
        self._t += 1
        self._steps += 1
        cost, drive = self._measure()
        r = reward(self.cfg, mean_latency_ms=cost.mean_latency_ms, bytes_moved=out.bytes_moved,
                   load_imbalance=cost.load_imbalance, applied=out.outcome == APPLIED,
                   is_noop=action == self.space.noop_index)
        summary = drive.summary()
        info = {
            "reward": r, "window": self._t, "outcome": out.outcome, "detail": out.detail,
            "statements": out.statements, "divergences": [str(d) for d in out.divergences],
            "bytes_moved": out.bytes_moved, "step_seconds": out.elapsed_s,
            "drive": summary, "mean_latency_ms": cost.mean_latency_ms,
            "tail_latency_ms": cost.tail_latency_ms, "load_imbalance": cost.load_imbalance,
            # The drive is not evidence if the machine slept or a request stalled.
            "suspect": bool(summary["suspended"] or summary["stalls"] or summary["failures"]),
            "action_mask": self.action_masks(),
        }
        truncated = self._steps >= self.cfg.episode.windows_per_episode
        return self._observe(cost), r, False, truncated, info

    def action_masks(self) -> np.ndarray:
        return self.space.applicable_mask(self.catalog)

    def close(self) -> None:
        self.driver.close()

    # ------------------------------------------------------------- internals

    @property
    def progress(self) -> float:
        return self._steps / max(1, self.cfg.episode.windows_per_episode)

    def _measure(self):
        window = self.generator.window(self._t)
        reqs = sample_requests(window, self.generator.template_cells,
                               self.generator.template_is_write, self.n_transactions, self._rng)
        drive = self.driver.drive(reqs)
        lat = drive.latencies()
        ops, cross = account(reqs, self.catalog, self.topology.rtt,
                             follower=self.read_mode == "follower")
        storage = self.catalog.storage_bytes_per_region()
        cost = MeasuredCost(
            mean_latency_ms=float(np.mean(lat)) if lat else float("nan"),
            tail_latency_ms=percentile(lat, self.cfg.cost.tail_percentile),
            cross_region_txn_fraction=cross, ops_per_region=ops,
            storage_bytes_per_region=storage,
            load_imbalance=coefficient_of_variation(ops),
            storage_imbalance=coefficient_of_variation(storage),
            n_requests=len(reqs))
        self._last_cost = cost
        self._window = window
        return cost, drive

    def _observe(self, cost: MeasuredCost) -> np.ndarray:
        return self.encoder.encode(catalog=self.catalog, window=self._window,
                                   generator=self.generator, cost=cost,
                                   churn_history=self.churn, progress=self.progress)
