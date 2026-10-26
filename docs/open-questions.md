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

---

## The headroom problem, 20 October 2026

**Experiments #1**, commit `a9d1045`, 8 seeds, 200 windows, volatility 1.0, on a
GitHub runner. Simulator only.

| Policy | Mean latency (ms) | 95% CI | GB moved |
|---|---|---|---|
| Static hash | 156.11 | [148.92, 164.33] | 0.0 |
| Random | 158.02 | [150.98, 165.63] | 204.8 |
| Follow traffic | 98.66 | [89.49, 106.58] | 785.2 |
| Best per window (fixed shards) | 93.66 | [86.60, 99.63] | 0.0 |

Following the traffic beats static hashing by **36.8%**, which is the project's
central claim and it holds with a comfortable margin.

**The problem is the next line down.** Follow traffic sits **5.00 ms** above the
fixed-shard bound, which is 5.1% of its own mean, and the two confidence
intervals overlap heavily. At volatility 1.0, a myopic one-shard-per-window
heuristic is already close to the best that lease movement alone can achieve.
There is almost nothing left on the latency axis for a learned policy to win.

### What this does and does not mean

It does not invalidate the project. It relocates the contribution. Three places
where room remains, in the order they should be tested:

1. **Movement cost.** Follow traffic pays 785 GB per episode to reach 98.66 ms.
   An agent reaching comparable latency for a fraction of that bandwidth is a
   defensible result, and it is what the reward's migration term already asks
   for. This is the most likely place the thesis survives.
2. **Volatility.** Reacting one window late should cost more as the workload
   drifts faster. If the follow-to-bound gap widens with volatility, the latency
   story returns at the top of the sweep. **Untested. This is the next run.**
3. **Splitting.** The bound holds the shard boundaries the episode started with,
   so it is not a global optimum. A policy that splits a wide shard spanning
   divergent traffic angles can sit below the line. The per-cell against
   per-fragment concentration gap recorded earlier, 53% against 41%, is the
   quantity that says how much is there.

### What must not happen

The temptation is to report the 36.8% figure and leave the 5 ms unmentioned. A
reviewer computing the second number from the first table will find it in
seconds, and finding it unacknowledged is worse than the number itself. It goes
in the Evaluation section as stated, with the three directions above as the
response.

---

## The agent does not work yet, 20 October 2026

**Train agent #1**, commit `4447fdf`. 300,000 steps in 26 minutes on a 2-core
runner, then evaluated on seeds 2000 to 2007, which it never trained on.

| Policy | Mean latency (ms) | 95% CI | GB moved |
|---|---|---|---|
| Learned policy | 146.55 | [141.48, 151.72] | 53.2 |
| Static hash | 151.19 | [145.35, 157.01] | 0.0 |
| Follow traffic | 90.76 | [83.55, 101.06] | 752.6 |
| Best per window (fixed shards) | 85.77 | [79.48, 94.40] | 0.0 |

The agent beats doing nothing by 3.1% and loses to the hand-written heuristic by
a wide margin. Best evaluation during training was 138.24 ms at step 160,000, so
it was not still improving when the budget ran out.

### The diagnosis I believe, and the experiment that tests it

The agent moved **53 GB where follow traffic moved 753**. It did not fail to find
good placements so much as learn not to move at all. That is the signature of a
credit assignment failure rather than a tuning failure: the migration penalty is
immediate and certain, the latency benefit is delayed and spread over many
windows, and a Q-function trained for 1,500 episodes on a 261-action space
resolves that disagreement by sitting still.

The arithmetic says the economics do favor moving. Relocating one of six shards
costs 0.30 in reward; the latency gain from 151 ms to 91 ms is 0.59 per window
thereafter. So the penalty is not too large in expectation. It is too large *at
the moment the action is taken*, which is a different problem and a familiar one.

**The test:** train once at `w_migration = 0.0`. If the agent then approaches
follow traffic, the diagnosis holds and the fix is reward shaping, a longer
exploration schedule, or n-step returns. If it still fails with no migration
penalty at all, the problem is exploration or representation instead, and the
261-action space with a two-step relocation sequence is the first suspect:
reaching a new region requires `MOVE_REPLICA_TO` and then `MOVE_LEASE` in
consecutive windows, and epsilon-greedy exploration almost never produces that
pair by chance.

### What this costs the midterm

Nothing. The rubric awards no points for the agent beating the baseline. The
submission reports a wired, trained agent, a held-out evaluation, a negative
result and a diagnosis, which is what an honest progress report looks like at
50 to 60 percent. The risk is spending the remaining days chasing it instead of
writing.

---

## The sweep answers the headroom question, 20 October 2026

**Sweep #1**, commit `5f1b671`, 8 seeds per value, 200 windows. Simulator only.
This supersedes the reading recorded above, which was taken at volatility 1.0
alone and was therefore misleading.

| volatility | static hash | follow traffic | bound | headroom | follow's advantage |
|---|---|---|---|---|---|
| 0.5 | 156.27 | 94.31 | 93.87 | 0.44 ms | 39.7% |
| 1.0 | 156.11 | 98.66 | 93.66 | 5.00 ms | 36.8% |
| 2.0 | 155.37 | 125.37 | 89.47 | 35.90 ms | 19.3% |
| 4.0 | 155.77 | 139.58 | 82.38 | 57.20 ms | 10.4% |

GB moved by follow traffic: 405, 785, 1057, 1115.

**The headroom opens from 0.4 ms to 57.2 ms**, which is 41% of the heuristic's
own latency at volatility 4. The premise holds, and more strongly than the
volatility-1.0 reading suggested.

Three things in the table are worth stating separately in the paper.

**Static hashing is flat.** 156.27, 156.11, 155.37, 155.77. It does not degrade
with volatility because it was never tracking anything in the first place. The
advantage column therefore falls because the heuristic gets worse, not because
the baseline gets better.

**The bound improves with volatility**, 93.87 down to 82.38. Sharper traffic
concentration means a well-chosen placement does better. So the achievable
optimum rises whilst the reactive heuristic falls, and the widening gap between
them is the finding.

**The heuristic pays more and gets less.** Movement rises by a factor of 2.75
whilst the advantage falls from 39.7% to 10.4%. Under fast drift a reactive
rule is buying churn.

### What this changes

**Train at volatility 2 to 4, not 1.0.** Both agent runs so far trained at
volatility 1.0, where the entire available prize is 5 ms. The agent was asked
to win a contest with almost nothing in it. That is the most likely single
reason the learned policy looks so weak, and it is a mistake in the experiment
design rather than in the agent.

The earlier entry's conclusion, that the contribution must move to movement
cost, is withdrawn. Movement cost remains a real second axis, but the latency
story is intact at the volatilities where the problem is actually hard.

---

## Removing the migration penalty helps, but does not close the gap

**Train agent #2**, commit `5f1b671`, identical to run 1 except
`w_migration = 0.0`. Evaluated on held-out seeds 2000 to 2007.

| | latency | GB moved |
|---|---|---|
| run 1, `w_migration = 0.30` | 146.55 ms | 53.2 |
| run 2, `w_migration = 0.00` | 135.57 ms | 192.8 |
| follow traffic | 90.76 ms | 752.6 |

Movement rose by a factor of 3.6 and latency improved by 11 ms. So the
migration penalty was suppressing movement, as the diagnosis predicted, and it
was not the only thing.

Two further facts point at what else is wrong. Run 2's held-out evaluation was
**127.66 ms at the final training step** and still falling, where run 1
plateaued at 138 ms by step 160,000: the budget ran out before convergence. And
both runs trained at volatility 1.0, where the sweep above shows only 5 ms of
headroom exists at all.

The next experiment is therefore not another tuning pass. It is training at
volatility 2 to 4, for longer, and that is post-midterm work.

---

## All eight training runs, 23 October 2026

Every run at commit `f459c44`, 200 windows, evaluated on held-out seeds 2000 to
2007. The six long runs used 1,000,000 steps; runs 1 and 2 used 300,000.

| # | Volatility | Migration weight | Learner seed | Agent latency (ms) | Agent GB | Inapplicable | Split share |
|---|---|---|---|---|---|---|---|
| 1 | 1.0 | 0.30 | 0 | 146.55 | 53.2 | not recorded | not recorded |
| 2 | 1.0 | 0.00 | 0 | 135.57 | 192.8 | not recorded | not recorded |
| 3 | 4.0 | 0.30 | 0 | 139.91 | 62.7 | 84.7% | 11.6% |
| 4 | 4.0 | below 0.30 | 0 | 136.94 | 123.7 | 82.8% | 11.4% |
| 5 | 4.0 | 0.30 | 0 | 139.91 | 62.7 | 84.7% | 11.6% |
| 6 | 2.0 | below 0.30 | 0 | 129.24 | 311.9 | 79.9% | 16.8% |
| 7 | 4.0 | 0.30 | **1** | 144.61 | 44.5 | 89.8% | 21.7% |
| 8 | 2.0 | 0.30 | 0 | 129.64 | 177.3 | 85.4% | 5.4% |

Reference points, for the three volatilities:

| Volatility | Static hash | Follow traffic | Follow's movement | Fixed-shard bound |
|---|---|---|---|---|
| 1.0 | 151.19 | 90.76 | 752.6 GB | 85.77 |
| 2.0 | 151.67 | 114.57 | 1048.5 GB | 80.71 |
| 4.0 | 150.12 | 129.04 | 1086.5 GB | 71.84 |

Runs 4 and 6 carry a migration weight below 0.30 that is recorded in their
`config.json` and has not been transcribed here. Do not quote a weight for them
from memory.

### Run 5 is a duplicate, and that is a reproducibility result

Runs 3 and 5 share the environment digest `60276db3` and agree to every printed
decimal, including the training evaluation at `136.5997700938358`. The learner
seed did not change between them, so run 5 repeated run 3 rather than
replicating it.

It cost 83 minutes and it establishes something worth one sentence in the paper:
**training is bit-reproducible.** The same configuration and the same seed give
an identical model. Most papers assert reproducibility; this demonstrates it.

### The learner seed matters more than the migration weight

Runs 3 and 7 differ in the learner seed alone.

| | Latency | GB moved | Split share |
|---|---|---|---|
| seed 0 | 139.91 | 62.7 | 11.6% |
| seed 1 | 144.61 | 44.5 | 21.7% |

**4.70 ms of spread from the seed**, and the share of windows spent splitting
nearly doubles. Set that against the difference between runs 3 and 4, which is
2.97 ms and is the only evidence available for an effect of the migration
weight at volatility 4.

**The seed spread exceeds the weight effect, so no claim about the migration
weight at volatility 4 survives this data.** Without run 7 that claim would have
been made, and it would have been wrong. The paper should say so plainly: it is
the single clearest argument for the experimental method used here, and the
nearest comparable work, RLRP, never repeats a configuration at all.

Two seeds is still two. The honest statement is that the spread is at least this
large, not that it is exactly 4.70 ms.

### The framing that survives the evidence

An earlier entry in this file argued from the volatility-1.0 runs that the
contribution had to move from latency to movement cost, and a later reading of
run 3 alone suggested the agent beat follow traffic on the reward. **Both are
withdrawn.** The first was drawn from one volatility; the second does not
survive run 7, and it also omitted the load-imbalance term, which is the same
order as the gap it claimed.

What survives rests only on measured quantities, with no reward weighting
required of the reader. Express the agent's result as the share of the available
latency improvement it captures, where available means the distance from static
hashing to follow traffic, against the share of follow traffic's movement it
pays for that.

At the stated objective, migration weight 0.30:

| Volatility | Share of the gain captured | Share of the movement paid |
|---|---|---|
| 1.0 | 7.7% | 7.1% |
| 2.0 | **59.4%** | 16.9% |
| 4.0 | 26.1 to 48.4% | 4.1 to 5.8% |

At the lower weight:

| Volatility | Share of the gain captured | Share of the movement paid |
|---|---|---|
| 1.0 | 25.8% | 25.6% |
| 2.0 | 60.5% | 29.7% |
| 4.0 | **62.5%** | 11.4% |

Two things to read off these.

**The agent is a low-movement policy, consistently.** Every run pays a smaller
share of the movement than the share of the improvement it captures, except at
volatility 1.0 where the two are equal and the improvement is small anyway. That
is the characterization to report, and it is what the reward asks for.

**The agent does best at volatility 2, not at 4.** The pattern is not monotone:
volatility 1.0 offers almost nothing to win, volatility 4.0 appears too chaotic
to learn in a million steps, and 2.0 sits between them. A monotone story would
have been tidier and is not what the data says.

### The caveat that goes with all of it

The agent's chosen actions are inapplicable in 80 to 90% of windows across every
run. Random's figure is 80.4%. So the agent's low movement is substantially a
failure to act rather than restraint, and the policy has not learned which
actions are legal in which state.

Combined with the seed spread, the position to take is that the policy has not
converged on a strategy. Two seeds under identical settings differ by a factor
of two in how often they split a shard. That is not a tuned agent being
outperformed; it is an agent that has not settled.

### What would be tried next, in order

1. **Action masking or an applicability-shaped penalty.** Eighty percent waste
   is the largest single inefficiency on the board.
2. **More seeds per configuration**, since two is enough to show the spread
   exists and not enough to size it.
3. **A convergence-based stopping rule** rather than a fixed step budget. RLRP
   trains until the placement is balanced enough, repeatedly, which is a
   property of the result rather than a step count. Runs 4, 6, 7 and 8 all
   recorded their best evaluation well before the budget ran out.
4. Longer training at volatility 2, where the agent is already strongest.

---

## The two verifications, 26 October 2026

### Migration weights on runs 4 and 6: settled

Recovered without opening the artifacts, by reconstructing the configuration
digest from candidate parameters and matching it against the digest each run
recorded. Every one of the six digests resolves uniquely:

| Digest | Volatility | Migration weight |
|---|---|---|
| `caf3851b` | 1.0 | 0.30 |
| `c5251ea9` | 1.0 | 0.00 |
| `68ac0947` | 2.0 | 0.30 |
| `803933af` | 2.0 | **0.00** |
| `60276db3` | 4.0 | 0.30 |
| `1690898f` | 4.0 | **0.10** |

So run 4 is volatility 4.0 at weight 0.10 and run 6 is volatility 2.0 at weight
0.00. This is stronger evidence than reading the config files would have been,
because it also demonstrates that the digest is reproducible from the stated
parameters, which is what makes it usable as a run identifier at all.

Note what it does to the frontier. At volatility 4 there is no zero-weight run,
only 0.10 and 0.30. At volatility 2 there is no 0.10 run, only 0.00 and 0.30.
The frontier is two points at each volatility, not three, and they are not the
same two.

### Load imbalance: baselines measured, agent still outstanding

Re-ran the baselines locally at volatility 2.0 and 4.0 on the same held-out
seeds 2000 to 2007. The digests and every latency reproduce the CI runs exactly,
so this is the same measurement rather than a similar one.

| Volatility | | Latency | Load imbalance |
|---|---|---|---|
| 2.0 | static hash | 151.67 | 0.501 |
| | random | 152.20 | 0.648 |
| | follow traffic | 114.57 | **0.945** |
| | bound | 80.71 | 0.782 |
| 4.0 | static hash | 150.12 | 0.561 |
| | random | 151.64 | 0.709 |
| | follow traffic | 129.04 | **1.003** |
| | bound | 71.84 | 0.945 |

**Follow traffic has roughly twice the load imbalance of static hashing.** It
buys its latency by concentrating work, which is precisely the behaviour the
imbalance term was put in the reward to penalize, and precisely what cluster
pilot 3 caught happening on real hardware when the co-located arm saturated.
Three independent things now agree: the reward's design, the simulator's
measurement, and the cluster's timing.

That is reportable on its own and it needs no agent data.

The agent's own imbalance is not yet measured, so the reward comparison stays
open. What can be stated is the threshold at which each agent run would tie
follow traffic on total reward cost, holding the measured baselines fixed:

| Run | Volatility | Weight | Ties follow traffic at imbalance |
|---|---|---|---|
| 3 | 4.0 | 0.30 | 1.452 |
| 7 | 4.0 | 0.30 | 1.009 |
| 4 | 4.0 | 0.10 | 1.781 |
| 8 | 2.0 | 0.30 | 0.745 |
| 6 | 2.0 | 0.00 | 1.051 |

Every observed imbalance in this project falls between 0.50 and 1.01. So runs 3,
4 and 6 would need an imbalance beyond anything yet measured in order to lose,
whilst runs 7 and 8 sit inside the observed range and genuinely could go either
way.

**Do not make a reward-based claim until the agent's imbalance is read from each
run's `summary.csv`.** The latency-and-movement framing recorded above needs
none of this and should carry the paper regardless.
