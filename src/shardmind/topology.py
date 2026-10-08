"""Regions, the inter-region latency matrix, and the circle the workload drifts around."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from shardmind.config import TopologyConfig

#: Representative inter-region round-trip times in milliseconds for the six
#: default regions, in the order given by ``TopologyConfig.region_names``.
#:
#: PROVENANCE. These are order-of-magnitude figures chosen to match the RTTs
#: commonly observed between these public-cloud regions: single-digit
#: milliseconds within a region, ~20 ms between two European regions, ~65-90 ms
#: across North America or the North Atlantic, and 150-230 ms on
#: trans-Pacific and Europe-Asia paths. They are NOT drawn from a specific
#: published dataset.
#:
#: TODO(paper): before any reported result, replace this table with a measured
#: matrix from a citable source (a continuous measurement service such as
#: cloudping, or a one-off measurement campaign of your own) and record the
#: collection date. Pass it through ``TopologyConfig.rtt_matrix_ms`` rather than
#: editing this constant, so the default stays clearly marked as synthetic.
DEFAULT_RTT_MS: tuple[tuple[float, ...], ...] = (
    #  use     usw     euw     euc     aps     apn
    (  1.0,   65.0,   68.0,   88.0,  215.0,  145.0),  # us-east-1
    ( 65.0,    1.0,  125.0,  145.0,  165.0,   95.0),  # us-west-2
    ( 68.0,  125.0,    1.0,   20.0,  180.0,  200.0),  # eu-west-1
    ( 88.0,  145.0,   20.0,    1.0,  155.0,  225.0),  # eu-central-1
    (215.0,  165.0,  180.0,  155.0,    1.0,   70.0),  # ap-southeast-1
    (145.0,   95.0,  200.0,  225.0,   70.0,    1.0),  # ap-northeast-1
)


@dataclass(frozen=True)
class Topology:
    """An immutable view of the cluster's geography.

    Attributes
    ----------
    names:
        Region names, indexed by region id.
    rtt:
        ``(R, R)`` round-trip times in milliseconds. Symmetric, with the
        configured intra-region RTT on the diagonal.
    angles:
        ``(R,)`` angular position of each region in radians, derived from
        longitude. The workload centroid travels around this same circle.
    storage_capacity_bytes:
        Per-region storage ceiling, used for the load-balance term.
    """

    names: tuple[str, ...]
    rtt: np.ndarray
    angles: np.ndarray
    storage_capacity_bytes: float

    @property
    def n_regions(self) -> int:
        return len(self.names)

    @property
    def max_rtt(self) -> float:
        return float(self.rtt.max())

    def nearest(self, origin: int, candidates: np.ndarray) -> int:
        """Return the candidate region with the lowest RTT from ``origin``."""
        cand = np.asarray(candidates)
        return int(cand[np.argmin(self.rtt[origin, cand])])


def build_topology(cfg: TopologyConfig, dataset_bytes: float) -> Topology:
    """Construct a :class:`Topology` from configuration.

    The RTT matrix is symmetrized and its diagonal overwritten with the
    configured intra-region RTT, so a hand-written table cannot silently
    introduce an asymmetry the cost model would then depend on.
    """
    n = len(cfg.region_names)

    if cfg.rtt_matrix_ms is not None:
        rtt = np.asarray(cfg.rtt_matrix_ms, dtype=np.float64)
    elif n == len(DEFAULT_RTT_MS):
        rtt = np.asarray(DEFAULT_RTT_MS, dtype=np.float64)
    else:
        raise ValueError(
            f"no built-in RTT table for {n} regions; supply TopologyConfig.rtt_matrix_ms"
        )

    if rtt.shape != (n, n):
        raise ValueError(f"rtt_matrix_ms must be ({n}, {n}), got {rtt.shape}")
    if np.any(rtt < 0.0):
        raise ValueError("rtt_matrix_ms must be non-negative")

    rtt = 0.5 * (rtt + rtt.T)
    np.fill_diagonal(rtt, cfg.intra_region_rtt_ms)
    rtt.flags.writeable = False

    angles = np.deg2rad(np.asarray(cfg.region_longitudes_deg, dtype=np.float64))
    angles.flags.writeable = False

    capacity = cfg.storage_capacity_factor * dataset_bytes / n

    return Topology(
        names=tuple(cfg.region_names),
        rtt=rtt,
        angles=angles,
        storage_capacity_bytes=float(capacity),
    )
