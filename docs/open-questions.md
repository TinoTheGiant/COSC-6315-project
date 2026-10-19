# Open questions and calibration items

**Date:** 2026-09-20
**Status:** this is the week 3 agenda. Everything here is a known problem with a
proposed resolution, not a vague worry.

---

## 1. The volatility sweep does not move the static baseline

**The finding.** Volatility is the proposal's single primary sweep dimension
(Phase 4.1). Measured across it, the static baseline barely moves.

Six regions, twenty fragment cap, 100-window episodes, three seeds,
reproduced by `python scripts/volatility_probe.py`:

| volatility | static (ms) | follow (ms) | inst. best (ms) | tracking gap (ms) | GB moved / episode |
|-----------:|------------:|------------:|----------------:|------------------:|-------------------:|
| 0.0 | 174.98 | 85.08 | 82.82 | **+2.26** | 53.4 |
| 0.5 | 156.44 | 92.60 | 95.28 | -2.68 | 153.5 |
| 1.0 | 157.71 | 87.15 | 90.05 | -2.90 | 260.3 |
| 2.0 | 158.17 | 87.95 | 88.42 | -0.47 | 370.3 |
| 4.0 | 156.04 | 94.85 | 85.53 | **+9.32** | 387.2 |
| 8.0 | 155.58 | 95.04 | 70.04 | **+25.00** | 377.0 |

"Inst. best" re-optimizes every primary every window for free, allocation only
(see the docstring in `scripts/volatility_probe.py`; it is a moving reference,
not an upper bound, which is why the tracking gap goes slightly negative where
the follow-traffic policy's replica placement happens to beat it).

**Why it happens, and why it is not a bug.** Volatility rotates the angular
demand field faster. A hash placement is roughly uniform across regions, and
rotating a field past a uniform placement leaves it about as wrong as it was.
Over an episode the mismatch time-averages to nearly the same number whatever
the rotation speed. Volatility does not make standing still worse; it makes
*tracking* harder.

The v = 0 row makes the same point from the other side. With no rotation at all
the static baseline is its *worst* (175 ms), because the initial placement is
stuck against one fixed demand field with no time-averaging to smooth it.
Plotting static latency against volatility therefore produces a flat line with
an odd bump at the origin, which is not a result.

**What does respond.** Two things, both strongly:

- **Tracking gap.** The follow-traffic policy sits within 3 ms of the instantaneous
  best up to volatility 2, then falls behind: +9 ms at 4, +25 ms at 8. This is
  the quantity the research question is actually about.
- **Migration volume.** 53 GB per episode at v = 0, rising to 387 GB by v = 4,
  a factor of seven, before saturating as the tracker hits its one-action-per-
  window rate limit.

**Proposed resolution.** Report the volatility sweep on three axes rather than
one: mean latency (which will show the static baseline flat and the learned
policy's advantage widening), tracking gap against the instantaneous best, and
migration volume. The headline claim becomes "the learned policy tracks where
heuristics fall behind, at lower churn", which is both more defensible and a
better match to Objective 5 than "volatility makes everything worse".

**Also worth trying.** Concentrating spikes so they hit the regions currently
holding primaries would make volatility hurt a static placement directly.
That is a workload-model change and needs justifying as realistic rather than
convenient, so it is a second option rather than the first.

**Priority:** high. It affects the shape of the paper's main figure.

---

## 2. The value of the fragmentation action is bounded by one parameter

`cell_angle_walk_sigma` (default 0.30 rad) controls how much adjacent keyspace
cells differ in geographic affinity. Splitting a fragment can only pay off to
the extent that its two halves serve different populations, so this parameter
sets a ceiling on what the project's novelty claim can possibly be worth. At
sigma = 0 every fragment is a scaled copy of the global demand field and the
split action is pure noise.

**Proposed resolution.** Objective 6's ablation must sweep sigma, not fix it.
The deliverable is the marginal value of `SPLIT` and `MERGE` as a function of
how heterogeneous the keyspace is. If the fragmentation action adds nothing even
at high sigma, that is a finding and should be reported as one rather than
buried. Recorded in ADR-0006.

**Priority:** high, and it is cheap. Do it in week 3 before committing to the
joint-action framing in the paper.

---

## 3. The latency matrix has no citable provenance

`topology.DEFAULT_RTT_MS` holds representative inter-region RTTs chosen to match
commonly observed figures. They are not from a published dataset, and the
constant says so.

**Proposed resolution.** Before any reported number, replace it with a measured
matrix from a citable source, or a measurement campaign of your own, and record
the collection date. Pass it via `TopologyConfig.rtt_matrix_ms` rather than
editing the constant, so the synthetic default stays clearly marked.

**Priority:** medium. It does not affect any ordering, but a reviewer will ask.

---

## 4. `w_imbalance` is a free parameter with no ground truth

The analytic cost model has no queueing (ADR-0004), so load imbalance cannot
express itself as latency and instead enters the reward with a weight, default
0.10. That number was chosen for scale, not measured.

**Proposed resolution.** Sweep it alongside `w_migration` in Objective 5, or
set it to zero and report what changes. A weight nobody has justified should not
sit silently in a headline result.

**Priority:** medium.

---

## 5. The agent cannot anticipate, only react

The observation contains the current window's demand and the recent churn, but
not the rotation phase or any demand history. A vanilla DQN over a single
window therefore reacts to drift after it has happened. Lion's reported ~4x
faster adaptation comes specifically from its LSTM *anticipating* the shift.

**Proposed resolution.** Name it in the paper as a limitation and as the obvious
next step: frame stacking is a one-line change in Stable-Baselines3
(`VecFrameStack`) and would be the cheapest thing to try if week 8's buffer
survives. Building a predictor is out of scope for eight weeks.

**Priority:** low for the code, high for the write-up. The comparison against
Lion is not honest without it.

---

## 6. About half the action space changes nothing in the initial state

Measured, per `test_actions.py`: of actions addressing a fragment that exists,
about 54% apply on a freshly built catalogue. `DROP_REPLICA` is entirely dead,
because a new catalogue sits exactly at `min_replicas`. Applicability rises as
the agent splits and over-replicates.

The proposal's phrasing, "the proportion of inapplicable actions is near zero",
overstates this. The property DQN actually requires is that every action is
*defined* in every state, which does hold and is proved by exhaustive fuzz test.

**Proposed resolution.** Restate the claim in the paper's method section using
the measured table in ADR-0002, and log the applied-action fraction during
training as a diagnostic.

**Priority:** medium, and it is a write-up fix rather than a code fix.

---

## 7. Internal consistency is not validity, and this is now required

Every cost-model test checks that the model agrees with itself. Nothing checks
that it agrees with a database.

**Status changed on 23 September.** The instructor has said the project should
involve a real database, naming Cassandra or CockroachDB. This moves the
validation harness from stretch goal to requirement, and changes the target
database. ADR-0007 worked through the options and recommended CockroachDB.

**Status changed a third time on 7 October**, and this is the settled one. The
instructor has approved **pre-training in the simulator and fine-tuning on the
real cluster**. That makes cost-model parity between the two halves decisive,
because a pre-trained network only transfers if the observation space, the action
space and the cost structure agree. Citus at replication factor 1 cannot provide
it: with one copy per shard, `cost.read_serving_region` and
`cost.replication_term` describe nothing the cluster does.
[ADR-0009](adr/ADR-0009-cockroachdb-for-sim-to-real-parity.md) therefore reverses
to **CockroachDB at fixed replication factor 3, six regions, six nodes**, and the
simulator keeps its cost model and its measured results. The three-reading
question below is answered: reading 1, results produced on a real cluster, with
pre-training permitted.

**Status changed on 29 September.** The instructor has since required that
the project run on a real database rather than a simulator, and has not
restricted the choice. Two of ADR-0007's central claims also turned out to be
false, so the choice was reopened and twenty-one systems were screened against
eight criteria. [ADR-0008](adr/ADR-0008-database-selection.md) records the result
and selects **Citus**, AGPL-3.0, one coordinator plus one Postgres worker per
region, with CockroachDB retained as the named fallback. Only five of the
twenty-one have a verified synchronous targeted placement command, and three of
those five fail elsewhere: ScyllaDB and HBase have no cross-shard transactions
for the reward to measure, and MongoDB is SSPL with an eleven-to-thirteen-process
footprint. The cost of choosing Citus is that the action space narrows to move and
split, which ADR-0008 argues is both consistent with the project's title and a
better-conditioned learning problem than the 401 actions this project started
with. **Settled on 19 October**, though not in Citus's favor: the action space is
now 261 actions over `MOVE_LEASE`, `MOVE_REPLICA_TO` and `SPLIT`, measured 29.2
percent applicable against 22.1 percent for the old five-kind space at fixed
replication factor. The amendment to
[ADR-0002](adr/ADR-0002-flat-declarative-action-space.md) records the
measurement.

**The question that blocks everything else.** "Should have a real database" has
three readings, and they differ by weeks:

1. results must be produced on a real cluster;
2. the project must demonstrate that the simulator's conclusions hold on one;
3. the action space must be shown to map onto a real system's primitives.

Reading 1 is not achievable. CockroachDB carries out a placement change through
background queues whose cadence is minutes, and no public API forces them to
run, so a training run of tens of thousands of steps cannot happen against a
real cluster in five weeks. Readings 2 and 3 are achievable, and 2 contains 3.

**Proposed resolution.** Ask the instructor which reading is meant, this week,
before any Docker work starts. Raise the Cassandra fit problem in the same
conversation: Cassandra places data by consistent hashing with no per-key-range
placement control and no two-phase commit, so the project's central mechanism
has no counterpart in it. That is a fit problem, not a difficulty problem, and
it is better discovered in week 3 than week 7.

**Priority:** highest open item in the project.
