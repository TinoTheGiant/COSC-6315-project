"""The reward, defined once for the simulator and the cluster.

``fragalloc.env`` (simulator) and ``fragalloc.harness.env`` (CockroachDB) both
call :func:`reward`. One definition, because a reward that drifts between the
two environments makes every pre-trained Q-value wrong by an unknown amount.
The only difference between them is where ``mean_latency_ms`` and
``load_imbalance`` come from: the cost model, or the cluster.

    r = -( w_latency   * mean_latency_ms / latency_scale_ms
         + w_migration * bytes_moved / (dataset_bytes * migration_scale_fraction)
         + w_imbalance * load_imbalance
         + inapplicable_action_cost  if a non-NOOP action changed nothing )

Migration is a fraction of the dataset, never raw bytes (ADR-0010). NOOP is
never charged (ADR-0013).
"""

from __future__ import annotations

from fragalloc.config import FragAllocConfig


def reward(cfg: FragAllocConfig, *, mean_latency_ms: float, bytes_moved: float,
           load_imbalance: float, applied: bool, is_noop: bool) -> float:
    w = cfg.reward
    latency_term = mean_latency_ms / w.latency_scale_ms
    migration_term = bytes_moved / (cfg.catalog.dataset_bytes * w.migration_scale_fraction)
    penalty = 0.0 if applied or is_noop else w.inapplicable_action_cost
    return float(-(w.w_latency * latency_term
                   + w.w_migration * migration_term
                   + w.w_imbalance * load_imbalance
                   + penalty))
