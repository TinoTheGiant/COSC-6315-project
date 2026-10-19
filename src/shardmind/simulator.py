"""The cluster simulator: the model, with no reinforcement learning in it.

``ClusterSimulator`` owns the topology, the workload generator, the fragment
catalogue and the clock. It applies an action and advances one decision window.
It knows nothing about observations, rewards or Gymnasium; that translation
lives in :mod:`shardmind.env`. The separation is what lets the cost model and
the baselines be tested without importing an RL stack, and is recorded in
ADR-0005.

Timing convention
-----------------
An action is taken at a window boundary and takes effect immediately; the
following window of demand is then served under the new placement. So the
placement the agent chooses at step ``t`` is the one evaluated against
window ``t + 1``. Migration is modelled as instantaneous but not free: its cost
is charged in bytes, not in latency. A real cluster would serve degraded traffic
during the copy, and ADR-0006 records that omission.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from shardmind.actions import ActionSpace
from shardmind.catalog import FragmentCatalog, MutationResult
from shardmind.config import ShardMindConfig
from shardmind.cost import CostBreakdown, evaluate
from shardmind.topology import Topology, build_topology
from shardmind.workload import WorkloadGenerator, WorkloadWindow


@dataclass(frozen=True)
class StepResult:
    """Everything one simulated window produced."""

    window: WorkloadWindow
    cost: CostBreakdown
    mutation: MutationResult
    bytes_moved: float
    step_index: int
    done: bool


class ClusterSimulator:
    """A seeded, reproducible multi-region cluster under drifting demand."""

    def __init__(self, config: ShardMindConfig | None = None) -> None:
        self.cfg = config or ShardMindConfig()
        self.topology: Topology = build_topology(self.cfg.topology, self.cfg.catalog.dataset_bytes)
        self.action_space = ActionSpace(self.cfg.catalog.max_fragments, self.cfg.n_regions)

        self.generator: WorkloadGenerator
        self.catalog: FragmentCatalog
        self.churn_history: np.ndarray
        self._t = 0
        self._steps_taken = 0
        self._last: StepResult | None = None

        self.reset()

    # ------------------------------------------------------------------ life

    def reset(self, seed: int | None = None) -> StepResult:
        """Start a fresh episode. Identical seeds give identical episodes."""
        cfg = self.cfg
        rng = np.random.default_rng(cfg.seed if seed is None else seed)

        horizon = cfg.episode.warmup_windows + cfg.episode.windows_per_episode + 1
        self.generator = WorkloadGenerator(cfg.workload, self.topology, rng, horizon)
        self.catalog = FragmentCatalog(cfg.catalog, cfg.workload.n_cells, cfg.n_regions)
        self.churn_history = np.zeros(cfg.episode.churn_history_windows, dtype=np.float64)

        self._t = cfg.episode.warmup_windows
        self._steps_taken = 0

        window = self.generator.window(self._t)
        cost = evaluate(self.catalog, window, self.generator, self.topology, cfg.cost)
        self._last = StepResult(
            window=window,
            cost=cost,
            mutation=MutationResult(False, 0.0, "reset"),
            bytes_moved=0.0,
            step_index=0,
            done=False,
        )
        return self._last

    def step(self, action_index: int) -> StepResult:
        """Apply one action, then serve the next window of demand."""
        if self._last is not None and self._last.done:
            raise RuntimeError("episode is finished; call reset()")

        mutation = self.action_space.apply(self.catalog, action_index, self.topology.rtt)
        self.catalog.validate()

        self._t += 1
        self._steps_taken += 1

        self.churn_history = np.roll(self.churn_history, 1)
        self.churn_history[0] = mutation.bytes_moved

        window = self.generator.window(self._t)
        cost = evaluate(self.catalog, window, self.generator, self.topology, self.cfg.cost)

        self._last = StepResult(
            window=window,
            cost=cost,
            mutation=mutation,
            bytes_moved=mutation.bytes_moved,
            step_index=self._steps_taken,
            done=self._steps_taken >= self.cfg.episode.windows_per_episode,
        )
        return self._last

    # ------------------------------------------------------------------ view

    @property
    def window_index(self) -> int:
        """Absolute window number, warmup included."""
        return self._t

    @property
    def progress(self) -> float:
        """Fraction of the episode elapsed, in ``[0, 1]``."""
        return self._steps_taken / max(1, self.cfg.episode.windows_per_episode)

    @property
    def last(self) -> StepResult:
        assert self._last is not None
        return self._last

    def snapshot(self) -> dict[str, float]:
        """Flat, JSON-friendly record of the current step, for experiment logs."""
        c = self.last.cost
        return {
            "window": float(self._t),
            "step": float(self._steps_taken),
            "n_fragments": float(self.catalog.n_fragments),
            "mean_latency_ms": c.mean_latency_ms,
            "tail_latency_ms": c.tail_latency_ms,
            "mean_read_latency_ms": c.mean_read_latency_ms,
            "mean_write_latency_ms": c.mean_write_latency_ms,
            "mean_txn_latency_ms": c.mean_txn_latency_ms,
            "cross_region_txn_fraction": c.cross_region_txn_fraction,
            "load_imbalance": c.load_imbalance,
            "storage_imbalance": c.storage_imbalance,
            "bytes_moved": self.last.bytes_moved,
        }
