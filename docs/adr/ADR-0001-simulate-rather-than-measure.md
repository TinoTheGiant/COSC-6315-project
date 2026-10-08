# ADR-0001: Simulate the cluster rather than measure a real one

**Status:** Accepted
**Date:** 2026-09-20
**Deciders:** Tinotenda Kaseke (solo project, COSC 6315)

## Context

The research question asks how a learned policy behaves under continuously
migrating workloads. Answering it requires tens of thousands of episodes across
a volatility sweep, a migration-cost sweep and an ablation set. The resources
available are one laptop, eight weeks, no cloud budget and no GPU.

A real geo-distributed cluster would settle the question most convincingly, but
one training episode on a real cluster is minutes of wall clock and its cost
model cannot be swept. At a thousand episodes it is a week of compute for one
point on one curve.

There is also a credibility cost running the other way. A simulator is only as
persuasive as its fidelity, and a result that exists only inside a model the
author wrote is the standard objection to this class of paper. Lion [1] and
GeoTP [2] both report measurements on real systems.

## Decision

The core deliverable is a pure-NumPy simulator of an N-region cluster. Real
cluster measurement is a stretch goal, scoped as *validation of the simulator's
ordering* rather than as a second set of results.

## Options Considered

### Option A: Pure simulation

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low: a few matrix operations per step |
| Cost | Zero |
| Throughput | ~2000 decision windows per second on one CPU core |
| Sweep feasibility | Complete: every parameter is a config field |
| External credibility | Weakest on its own |

**Pros:** the sweeps in Objectives 5 and 6 are actually reachable; every result
reproduces from a seed; debugging an RL agent against a deterministic
environment is tractable.
**Cons:** no queueing, no failures, no real network variance; the reviewer's
first question is whether the model is a toy.

### Option B: Real cluster only

| Dimension | Assessment |
|-----------|------------|
| Complexity | High: Docker, MongoDB zone sharding, latency injection, orchestration |
| Cost | Free locally, but weeks of wall clock for training |
| Sweep feasibility | Effectively none |
| External credibility | Strongest |

**Pros:** results mean what they say.
**Cons:** the eight-week schedule cannot absorb it, and without sweeps there is
no characterization, only an anecdote.

### Option C: Simulate to train, validate on a real cluster

| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium-high; the validation harness is its own project |
| Cost | Free, bounded wall clock |
| Sweep feasibility | Complete |
| External credibility | Good: the fidelity objection gets an answer |

**Pros:** answers the fidelity objection at a bounded cost, because validation
needs a handful of placements ranked, not a training run.
**Cons:** the harness is real work and can eat the buffer week.

## Trade-off Analysis

The decisive observation is that validation and training have different
requirements. Training needs throughput; validation needs only that the
simulator ranks a small set of candidate placements in the same order a real
cluster does. Ranking agreement over, say, a dozen placements is a few hours of
Docker work, not a second experiment.

That reframes the stretch goal from "reproduce the results on real hardware",
which is infeasible here, to "show the model is not lying about which placement
is better", which is both feasible and the thing a reviewer actually doubts.

## Consequences

- Sweeps, ablations and seeds become cheap, so the characterization in
  Objectives 3, 5 and 6 is reachable.
- Every claim must be stated as a claim about the model until the validation
  harness exists. The paper says "in simulation" in the abstract.
- The cost model's omissions become load-bearing and must be documented, not
  buried. See ADR-0004 and `docs/open-questions.md`.
- If the validation harness slips, the contribution narrows to a formulation
  plus a characterized simulator plus baselines, which is still a reportable
  result. This is the fallback the risk table already names.

## Action Items

1. [x] Build the simulator with a seeded, reproducible interface.
2. [ ] Write `docs/validation-plan.md`: which placements get ranked, on what
   MongoDB topology, under what Toxiproxy latencies, and what agreement
   statistic counts as a pass (Spearman rank correlation, with a threshold
   fixed in advance).
3. [ ] Decide the go/no-go date for the harness. Week 6 is the last point at
   which it can start without eating the writing weeks.

## References

[1] Zheng et al., "Lion: Minimizing Distributed Transactions Through Adaptive
Replica Provision," ICDE 2024.
[2] Zhuang et al., "GeoTP: Latency-Aware Geo-Distributed Transaction Processing
in Database Middlewares," ICDE 2025.
