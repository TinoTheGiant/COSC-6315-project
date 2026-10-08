# ADR-0004: An analytic expected-cost model, not a discrete-event simulation

**Status:** Accepted
**Date:** 2026-09-20
**Deciders:** Tinotenda Kaseke

## Context

The simulator must turn "this placement, this window of demand" into a latency
number, tens of millions of times over the course of the experiments.

Two traditions are available. A discrete-event simulator (SimPy and its kin)
models individual requests moving through queues and gives throughput,
saturation and congestion collapse for free. An analytic model computes the
expected latency of each request class in closed form and weights by demand.

## Decision

Compute latency analytically. Every request class has a closed-form latency
given the placement, and a window is a weighted count over classes. One window
evaluation is a handful of operations on `(fragments, regions)` arrays.

## Options Considered

### Option A: Discrete-event simulation

| Dimension | Assessment |
|-----------|------------|
| Complexity | High: generators, queues, service disciplines, calibration |
| Speed | Order 10^3 to 10^4 events per second |
| Fidelity | Captures queueing and saturation |
| Determinism | Achievable but fiddly |

**Pros:** load becomes a latency effect rather than a separate metric, which is
how it behaves in reality; throughput claims become possible.
**Cons:** roughly a thousand times slower per window, which removes the sweeps;
introduces service-time distributions that would themselves need calibrating
against nothing, adding unfalsifiable parameters.

### Option B: Analytic expected cost (chosen)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Speed | ~0.5 ms per window measured, ~2000 windows per second |
| Fidelity | Latency only; no queueing, no saturation |
| Determinism | Exact |

**Pros:** the sweeps are affordable; the latency distribution is discrete and
known, so percentiles are exact rather than sampled; every number is traceable
to an equation, which makes the cost model reviewable.
**Cons:** the model cannot say anything about throughput or overload, and load
imbalance has to enter the reward as a separate term because it cannot enter
through latency.

## Trade-off Analysis

The exact-percentile property deserves emphasis, because it is not obvious. In a
discrete-event simulator the p95 latency is a sample statistic and needs many
requests before it stabilizes, which makes the reward noisy exactly where
Objective 4's headline metric lives. Here, each `(fragment, origin)` pair has one
known latency and one known count, so the latency distribution is a discrete
weighted distribution whose quantiles are computed, not estimated. The p95 that
Objective 4 reports is exact for the model.

The cost is real and must be stated plainly: **this is a latency model, not a
throughput model.** A placement that concentrates all traffic in one region is
charged an imbalance penalty but is never charged the latency that real
queueing would impose. Results must not be read as throughput claims, and the
paper should say so.

## Consequences

- Sweeps over volatility, migration weight and region count are affordable.
- Load imbalance appears as a reward term with a weight (`w_imbalance`, default
  0.10) rather than as an emergent effect. That weight is a modelling choice
  with no measured ground truth and should be swept, not trusted.
- Migration is instantaneous: the placement changes at the window boundary and
  the next window is served entirely under the new layout. A real cluster serves
  degraded traffic during the copy, so the model understates migration cost.
  The `w_migration` byte charge is the only thing standing in for that.
- The model cannot express failure, partition or repair.
- The MongoDB validation harness (ADR-0001) is the mitigation: it tests whether
  the analytic ordering matches a real cluster's ordering, which is the property
  the results actually rest on.

## Action Items

1. [x] Implement exact weighted percentiles instead of sampling.
2. [ ] State the latency-not-throughput limitation in the paper's threats to
   validity.
3. [ ] Sweep `w_imbalance` alongside `w_migration` in Objective 5 rather than
   fixing it at its default.
