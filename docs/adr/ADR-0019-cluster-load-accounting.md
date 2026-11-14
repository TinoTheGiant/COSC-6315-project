# ADR-0019: Where the cluster environment's load imbalance comes from

**Status:** Proposed; implemented in `fragalloc.harness.env`
**Date:** 2026-11-14
**Deciders:** Tino Kaseke

## Context

The reward has an imbalance term, `w_imbalance * load_imbalance`, and the
observation carries operations per region. In the simulator both come from the
cost model's accounting: each request is charged to the regions that serve it
under the current placement. The cluster environment must fill the same fields,
and the harness may not import the cost model (its dependency rule, now
enforced by `tests/test_harness_dependency_rule.py`).

Pilots 2 and 3 are the reason this matters: the co-located arm slowed as cores
doubled, consistent with one node saturating. Load is real on the cluster, so
how it is measured is a choice the paper must state.

## Decision (proposed)

**Count it from the requests actually sent, against the read-back placement.**
`fragalloc.harness.env.account` charges each sent read to its serving region
(the leaseholder, or under follower reads the nearest replica, never inside a
read-write transaction) and each write to every replica, the simulator's rule
applied to real requests on the real placement. Storage per region is the
catalogue's account in both environments.

## Options Considered

### A: counted from sent requests (proposed)

| Dimension | Assessment |
|-----------|------------|
| Fidelity to the simulator | Exact: same rule, same units, so the term means the same on both sides |
| Fidelity to the cluster | Counts work, not its cost; a hot node's queueing shows in latency, not here |
| Noise | Sampling noise of N requests only |
| Cost | None: no extra queries |

### B: measured from CockroachDB store metrics

`crdb_internal.kv_store_status` exposes per-store load metrics (queries per
second used by the rebalancer). Real, but averaged over a window that does not
align with a step, internal (the cockroachdb skills mark `crdb_internal`
tables as not for production use), and on a different scale from the
simulator's count, so a pre-trained Q-function would see a shifted input.

### C: drop the term on the cluster

Changes the reward between environments, which ADR-0010's whole argument for
dataset-fraction migration cost exists to prevent. Rejected.

## Consequences

- The imbalance term stays comparable between simulator and cluster, which is
  what fine-tuning needs.
- What it cannot see, CPU saturation on one node, still reaches the reward
  through measured latency, and the pilot's per-node CPU sampler records it
  for the paper.
- Revisit: if the CPU sampler shows saturation the count does not predict,
  report B alongside A as a diagnostic, not as the reward.
