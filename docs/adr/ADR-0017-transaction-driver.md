# ADR-0017: How the harness drives and times transactions

**Status:** Proposed; implemented, awaiting Cluster pilot #5
**Date:** 2026-11-14
**Deciders:** Tino Kaseke

## Context

Step 7 of the step protocol (docs/harness-architecture.md) drives `N`
transactions per step and times them. The reward is built from those times, so
every choice here is a choice about what the paper measures. Section 5 of the
design fixes the method for `N` (bootstrap the p95 at fixed placement) and two
confounds (gateway placement, concurrency). Four questions were still open:
open or closed loop, how a transaction is shaped, what a retry costs, and how
concurrency relates to the runner.

The last one has a history. Pilot 2 timed 200 transactions on 2 cores; pilot 3
timed 1000 on 4. The co-located arm slowed by 62% between them. N and cores
changed together, so either could be the cause.

## Decision

`fragalloc.harness.driver`:

1. **Closed loop, fixed concurrency per region.** `concurrency` workers per
   region (default 2), each with its own connection to that region's node,
   checked with `SHOW node_id`. The number is a stated parameter, identical
   across baselines and agent runs, and not derived from the runner's cores.
2. **Requests sampled from the window in proportion.** Single-key reads and
   writes run as autocommit statements. Template transactions run as `BEGIN`,
   one statement per member cell in template order, `COMMIT`; `BEGIN
   TRANSACTION READ ONLY` when no member writes. Sequential statements match
   the simulator, which charges a transaction the sum of its members.
3. **A retry costs what the client sees.** `40001` retries the whole unit with
   capped exponential backoff and jitter. Latency runs from the first attempt
   to success, and retries are counted. Other errors are failures, recorded and
   never retried. A lost connection aborts the drive.
4. **Suspend detection.** Boot clock against monotonic clock on Linux, wall
   clock elsewhere. A drive that spans a sleep is marked suspect.
5. **Cores decoupled from N in the pilot.** A `cluster_cores` input pins all
   six nodes to the first k CPUs (`docker update --cpuset-cpus`), a sampler
   records per-node CPU by phase, and the gate reports p50 by fifth of each
   arm, so time-in-run and hardware can be told apart on one runner.

## Options Considered

### Open loop (fixed arrival rate) instead of closed loop

| Dimension | Assessment |
|-----------|------------|
| Fidelity | Closer to real traffic; queueing shows up as latency |
| Risk | Latency then depends on the rate chosen, and ADR-0004 and the design doc exclude throughput and queueing |
| Cost | A rate per region to justify, and coordinated omission to handle |

Rejected: the paper makes no throughput claim, so fixing concurrency keeps
queueing constant across conditions, which is what the design asks for.

### One CTE statement per transaction

The benchmarking guidance shows single-statement CTEs cut retries under
contention. Rejected for the reward signal: it changes the round-trip
structure the simulator models, so the two environments would be measuring
different things. Worth stating in the paper as a limitation, not adopting.

### Timing only the successful attempt

Lower numbers, but not what a client experiences, and it would hide exactly
the contention that bad placement causes. Rejected.

## Consequences

- Easier: one driver for the gate, `N` selection and the environment; 20 tests
  with fake gateways, every one of nine code mutations caught.
- Harder: sequential statements mean CockroachDB's write pipelining and
  parallel commits still shorten real transactions relative to the model. That
  difference is a finding, not an error, and the paper should say so.
- Revisit: if pilot #5 shows a single region's queue dominating wall time,
  consider concurrency proportional to demand, applied identically to every
  condition.

## Action Items

1. [x] `driver.py`, `measure_n.py`, tests.
2. [x] Pilot inputs `cluster_cores`, `concurrency`, `measure_transactions`.
3. [ ] Cluster pilot #5: confirm `BEGIN TRANSACTION READ ONLY` and
       `SHOW node_id` on v25.3 (both documented; the read-only grammar was
       read from the parameter table, not a worked example).
4. [ ] Record N and its standard error in results-log.md and the methods.
5. [ ] The 2x2: transactions 200 and 1000, cluster_cores 2 and all.
