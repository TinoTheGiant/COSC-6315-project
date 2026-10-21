"""The geographically drifting request stream.

Model
-----
The keyspace is cut into ``n_cells`` atomic cells. Each cell ``k`` carries a
fixed angular position ``psi_k`` on the unit circle and a fixed popularity
``p_k``. Regions sit on the same circle at their longitudes. At window ``t`` the
whole angular field is rotated by ``theta(t)``, and the intensity of traffic
from region ``r`` to cell ``k`` is

    lambda(k, r, t)  proportional to  p_k * exp(kappa * cos(psi_k + theta(t) - phi_r)) * s(r, t)

where ``kappa`` is the von Mises concentration and ``s(r, t)`` is a localized
spike multiplier. Rotation gives the diurnal cycle; the spikes give the abrupt
localized events. The two together are what a fixed placement cannot track.

Cell angles follow a random walk along the keyspace rather than being drawn
independently. That is the load-bearing modelling choice: adjacent cells have
similar but not identical angles, so a wide fragment genuinely spans divergent
geographic affinities and splitting it is genuinely worth something. With i.i.d.
cell angles, every fragment would look alike and the fragmentation action would
be noise.

Requests come in two classes:

* single-key operations, counted in ``reads`` and ``writes`` as ``(cell, origin)``
  matrices;
* multi-fragment transactions, counted in ``txn_counts`` as ``(template, origin)``.
  A template is a fixed set of co-accessed cells with fixed read/write roles,
  drawn once at episode start, standing in for a TPC-C-style transaction class.

Transactions are counted as whole requests, not decomposed into the single-key
matrices, so that no request is charged twice in the latency distribution.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from fragalloc.config import WorkloadConfig
from fragalloc.topology import Topology

TWO_PI = 2.0 * np.pi


@dataclass(frozen=True)
class WorkloadWindow:
    """One decision window's worth of demand.

    Attributes
    ----------
    index:
        Absolute window number since the episode began, warmup included.
    reads, writes:
        ``(n_cells, n_regions)`` single-key request counts, indexed
        ``[cell, origin_region]``.
    txn_counts:
        ``(n_templates, n_regions)`` transaction counts by template and origin.
    centroid_angle:
        The rotation applied to the angular field this window, in radians.
        Diagnostic only; the agent never sees it.
    spike_multiplier:
        ``(n_regions,)`` multiplier in force this window. 1.0 means quiescent.
    """

    index: int
    reads: np.ndarray
    writes: np.ndarray
    txn_counts: np.ndarray
    centroid_angle: float
    spike_multiplier: np.ndarray

    @property
    def total_requests(self) -> float:
        return float(self.reads.sum() + self.writes.sum() + self.txn_counts.sum())


class WorkloadGenerator:
    """Produces :class:`WorkloadWindow` values for a fixed seed and horizon.

    The generator is pure with respect to the window index: ``window(t)`` for a
    given ``t`` always returns the same counts for a given generator instance.
    All randomness is drawn once, at construction, from the supplied
    ``Generator``. Nothing about the placement feeds back into the workload,
    which is a deliberate limitation recorded in ADR-0006.
    """

    def __init__(
        self,
        cfg: WorkloadConfig,
        topology: Topology,
        rng: np.random.Generator,
        horizon: int,
    ) -> None:
        self.cfg = cfg
        self.topology = topology
        self.horizon = int(horizon)
        self._rng = rng

        k = cfg.n_cells
        n_regions = topology.n_regions

        # --- cell angular positions: correlated random walk along the keyspace
        walk = rng.normal(0.0, cfg.cell_angle_walk_sigma, size=k).cumsum()
        sweep = np.linspace(0.0, TWO_PI, k, endpoint=False)
        self.cell_angles = np.mod(walk + sweep, TWO_PI)

        # --- cell popularity: Zipf weights assigned to a random permutation of
        # cells, so hot cells are scattered through the keyspace rather than
        # sitting at low keys where a range partitioner would trivially isolate
        # them.
        zipf = 1.0 / np.arange(1, k + 1, dtype=np.float64) ** cfg.zipf_s
        self.cell_popularity = np.empty(k, dtype=np.float64)
        self.cell_popularity[rng.permutation(k)] = zipf
        self.cell_popularity /= self.cell_popularity.sum()

        # --- transaction templates
        self.template_cells, self.template_is_write = self._draw_templates(rng)
        self.template_popularity = self.cell_popularity[self.template_cells].sum(axis=1)
        self.template_popularity /= self.template_popularity.sum()
        self.template_angles = _circular_mean(self.cell_angles[self.template_cells], axis=1)

        # --- spike schedule, precomputed over the horizon for reproducibility
        self.spike_multipliers = self._draw_spikes(rng, n_regions)

    # ------------------------------------------------------------------ setup

    def _draw_templates(self, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
        cfg = self.cfg
        k, t, a = cfg.n_cells, cfg.n_txn_templates, cfg.txn_arity
        span = max(1, int(cfg.txn_locality_cells))

        anchors = rng.choice(k, size=t, p=self.cell_popularity)
        cells = np.empty((t, a), dtype=np.int64)
        for i in range(t):
            # Sample without replacement from a local neighbourhood so a
            # transaction is plausibly local in the keyspace but need not be.
            lo = anchors[i] - span
            pool = np.mod(np.arange(lo, lo + 2 * span + 1), k)
            pool = np.unique(pool)
            if pool.size < a:  # pragma: no cover - only for pathological configs
                pool = np.arange(k)
            cells[i] = rng.choice(pool, size=a, replace=False)

        is_write = rng.random((t, a)) > cfg.read_fraction
        return cells, is_write

    def _draw_spikes(self, rng: np.random.Generator, n_regions: int) -> np.ndarray:
        cfg = self.cfg
        mult = np.ones((self.horizon + 1, n_regions), dtype=np.float64)
        if cfg.volatility <= 0.0:
            return mult

        prob = min(1.0, cfg.spike_probability * cfg.volatility)
        magnitude = 1.0 + (cfg.spike_magnitude - 1.0) * cfg.volatility
        duration = max(1, int(round(cfg.spike_duration_windows)))

        starts = rng.random(self.horizon + 1) < prob
        for t in np.flatnonzero(starts):
            region = int(rng.integers(n_regions))
            end = min(self.horizon + 1, t + duration)
            mult[t:end, region] *= magnitude
        return mult

    # ------------------------------------------------------------- generation

    def rotation(self, t: int) -> float:
        """Angular offset of the workload field at window ``t``."""
        cfg = self.cfg
        laps = cfg.drift_laps_per_period * cfg.volatility
        return float(TWO_PI * laps * (t / cfg.diurnal_period_windows))

    def window(self, t: int) -> WorkloadWindow:
        """Demand for window ``t``. Deterministic for a given generator."""
        cfg = self.cfg
        if not 0 <= t <= self.horizon:
            raise IndexError(f"window {t} outside precomputed horizon [0, {self.horizon}]")

        theta = self.rotation(t)
        spike = self.spike_multipliers[t]

        # (cells, regions) intensity field
        delta = self.cell_angles[:, None] + theta - self.topology.angles[None, :]
        intensity = self.cell_popularity[:, None] * np.exp(cfg.origin_concentration * np.cos(delta))
        intensity *= spike[None, :]
        intensity /= intensity.sum()

        # (templates, regions) intensity field
        t_delta = self.template_angles[:, None] + theta - self.topology.angles[None, :]
        t_intensity = self.template_popularity[:, None] * np.exp(
            cfg.origin_concentration * np.cos(t_delta)
        )
        t_intensity *= spike[None, :]
        t_intensity /= t_intensity.sum()

        n_single = cfg.ops_per_window * (1.0 - cfg.txn_fraction)
        n_txn = cfg.ops_per_window * cfg.txn_fraction

        if cfg.stochastic_counts:
            single = self._rng.multinomial(int(round(n_single)), intensity.ravel())
            single = single.reshape(intensity.shape).astype(np.float64)
            read_mask = self._rng.random(single.shape) < cfg.read_fraction
            reads = np.where(read_mask, single, 0.0)
            writes = single - reads
            txn_counts = self._rng.multinomial(int(round(n_txn)), t_intensity.ravel())
            txn_counts = txn_counts.reshape(t_intensity.shape).astype(np.float64)
        else:
            reads = intensity * (n_single * cfg.read_fraction)
            writes = intensity * (n_single * (1.0 - cfg.read_fraction))
            txn_counts = t_intensity * n_txn

        return WorkloadWindow(
            index=t,
            reads=reads,
            writes=writes,
            txn_counts=txn_counts,
            centroid_angle=theta,
            spike_multiplier=spike.copy(),
        )


def _circular_mean(angles: np.ndarray, axis: int) -> np.ndarray:
    """Mean of angles on the circle, which the arithmetic mean gets wrong at the wrap."""
    return np.mod(
        np.arctan2(np.sin(angles).mean(axis=axis), np.cos(angles).mean(axis=axis)),
        TWO_PI,
    )
