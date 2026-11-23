# Results log

Every real run against a real cluster, in order, with what it changed. A lab
notebook rather than a summary: entries are not edited once written, and a later
entry corrects an earlier one rather than rewriting it.

Simulator-only results are not recorded here. They live in `results/` and are
labelled as simulator throughout.

---

> **Correction, 14 November 2026.** Runs 1 to 3 below say "replication factor 3".
> That was the configuration's default, never a measurement: the pilot froze the
> rebalancer seconds after start-up without checking that up-replication had
> finished. Run 4, with the same start-up timing, read back two voters on every
> range of the harness table. The replica count in Runs 1 to 3 is therefore
> **unknown, most likely 2**, and every "replication factor 3" below should be
> read that way. From Run 5 the count is set and verified (ADR-0015).

## Run 1 — Cluster pilot #1, 8 October 2026

**Commit** `00eadd9`. GitHub Actions, `ubuntu-latest`, private repository, so a
**2-core / 7 GB** runner. Total duration 5m 22s. Six-node CockroachDB cluster,
replication factor 3, `netem` egress shaping.

First execution of any of the cluster code. Expected to fail; did not.

### What worked, first time

- **The Docker image built.** Moving the CockroachDB binary from its Red Hat base
  onto `debian:bookworm-slim` works, which was the single largest build risk.
- **The six-node cluster formed and initialized.**
- **The `netem` latency injection is accurate to 0.2 ms.** This is the headline
  engineering result and it retires the biggest technical risk in the project:

  | pair | configured | measured |
  |---|---|---|
  | us-east-1 -> us-west-2 | 65.0 | 65.1 |
  | us-east-1 -> eu-west-1 | 68.0 | 68.1 |
  | us-east-1 -> eu-central-1 | 88.0 | 88.2 |
  | us-east-1 -> ap-southeast-1 | 215.0 | 215.1 |
  | us-east-1 -> ap-northeast-1 | 145.0 | 145.1 |

  **This closes the `TODO(paper)` in `topology.py`.** On the cluster the RTT
  matrix is not an estimate of the world that needs a citation to defend; it is
  an experimental parameter, configured and then verified to a tenth of a
  millisecond. The paper still cites a public dataset for the *choice* of values.

### The gate: PASS

| placement | p50 | p95 | stdev |
|---|---|---|---|
| leaseholders co-located | 207.0 | 211.1 | 37.7 |
| leaseholders spread | 268.7 | 404.8 | 80.4 |

**p95 gap 193.7 ms, bootstrap 95% CI [190.8, 195.5].** The interval excludes zero
by two orders of magnitude.

**Placement measurably changes transaction latency on a real cluster.** The
reward signal the whole project depends on exists. The gate was scheduled for 12
October and cleared on the 8th.

### Two defects this run exposed

**1. Failure detection was broken.** `ALTER RANGE ... RELOCATE` reports `ok` or
the error text as a **column in its result set**, and `cockroach sql -e` exits 0
either way. The script checked only the return code, so it counted zero failures
whilst relocations were silently failing. Fixed: the result column is now parsed.

**2. `RELOCATE LEASE` can only target a store that already holds a replica.** The
run asked for leaseholders on all six regions and got two
(`['ap-southeast-1', 'us-east-1']`). With replication factor 3 across six nodes,
each range lives on three of them, so only three of the six stores are eligible
to take its lease. Round-robin lease placement therefore collapsed.

So **the gate's conclusion holds but the experiment was not the one described**:
it compared one region against two, not one against six. That the gap was still
194 ms makes the conclusion stronger rather than weaker, but the run must be
repeated honestly. Fixed: voters are moved before leases.

### One finding worth putting in the paper

**Co-locating the leaseholders still cost 207 ms at the median.** If all leases
sit in `us-east-1` and the client's gateway is `us-east-1`, a naive reading
expects single-digit latency. It is 207 ms because **writes need a quorum**, and
with replication factor 3 spread across continents, two of the three replicas are
far away. Every write pays a cross-region Raft round trip no matter where the
lease sits.

This is correct database behaviour and it is a useful result: **moving the lease
does not localize writes; the replicas have to move too.** It is a direct,
measured justification for the action space in
[ADR-0009](adr/ADR-0009-cockroachdb-for-sim-to-real-parity.md) carrying both
`MOVE_LEASE` and `MOVE_REPLICA` rather than leases alone, and it is the kind of
thing a reviewer asks about.

### Caveats on these numbers

- **2 cores.** Six CockroachDB nodes contending on two cores. The standard
  deviations, 37.7 and 80.4 ms, are high. The gap is roughly five times the
  larger of them, so the conclusion survives comfortably, but these are not
  publication-quality numbers. Re-run on a 4-core runner (public repository) for
  anything reported.
- **Transactions were issued serially**, so there is no queueing. Deliberate for
  a go/no-go, wrong for a headline measurement.
- **The client-to-gateway hop is unshaped.** The load generator runs on the host,
  not inside the network, so what is measured is cluster-internal cost. Worth one
  sentence in the methods section.
- `N` was 200 per case, chosen arbitrarily rather than by the standard-error
  procedure in [`harness-architecture.md`](harness-architecture.md) section 5.
  That procedure still needs running.

### What changes because of this run

1. The gate is cleared. Agent work is unblocked, four days early.
2. The `TODO(paper)` on the RTT matrix is answered by construction.
3. The action space must account for `MOVE_LEASE` being valid only to stores
   already holding a replica. See the amendment to
   [ADR-0009](adr/ADR-0009-cockroachdb-for-sim-to-real-parity.md).
4. Re-run the gate on the fixed script before any number from it is reported.

---

## Run 2 — Cluster pilot #2, 20 October 2026

**Commit** `a9d1045`. GitHub Actions, `ubuntu-latest`, private repository, so
again a **2-core / 7 GB** runner. Total duration 9m 18s. Six nodes, replication
factor 3, `netem` egress shaping, 6 ranges of 2,000 rows.

This is the re-run that run 1 required. Run 1 compared one region against two,
not one against six, because `RELOCATE LEASE` silently refused every move to a
store holding no voting replica and `cockroach sql -e` exited 0 regardless. Both
defects were fixed on 11 October. **This entry supersedes run 1's gate verdict.**

### The gate: PASS, and the real effect is seven times larger

| | p50 (ms) | p95 (ms) | stdev (ms) |
|---|---|---|---|
| leaseholders co-located in us-east-1 | 272.7 | 275.5 | 48.8 |
| leaseholders spread across all six regions | 1013.4 | 1648.0 | 302.0 |

**p95 gap 1372.5 ms**, 95% bootstrap CI [1218.6, 1373.8]. Run 1 reported 193.7 ms
on the same statistic. The difference is the defect, not variance.

Placement confirmation is now in the log rather than assumed: case A observed
`['us-east-1']`, case B observed all six region names. Store IDs were resolved
from `crdb_internal.kv_store_status` joined to `kv_node_status`, which matters
because node IDs are assigned in join order: this run's mapping was
`us-east-1: 1, us-west-2: 2, eu-central-1: 3, eu-west-1: 4, ap-northeast-1: 5,
ap-southeast-1: 6`, which is not the configuration order.

Latency injection remains accurate, now to 0.1 ms across the five measured pairs.

### Three things to be careful about when quoting this

**1. "Co-located" means the leases, not the data.** With replication factor 3
and one node per region, three voting replicas cannot fit in one region, so every
write pays a cross-region quorum acknowledgement even in case A. That is why the
co-located p50 is 272.7 ms rather than the single-digit figure an intra-region
RTT of 1 ms would suggest. The experiment therefore isolates the *leaseholder*
placement effect at fixed, spread replication. That is the right thing to
measure, because `MOVE_LEASE` is precisely the action it corresponds to, but the
paper must say so or the number reads as an error.

**2. The confidence interval is not a precision claim.** The point estimate of
1372.5 ms sits essentially on the interval's upper bound of 1373.8. A bootstrap
interval on a difference of p95s behaves this way when the p95 is close to the
largest observation, which is what happens at N = 200 transactions: the 95th
percentile is the 190th order statistic and a resample rarely exceeds it. The
verdict is safe regardless, because a 1,372 ms gap against a co-located standard
deviation of 48.8 ms is not a borderline call. But **N must be chosen by
measurement before any interval from this experiment goes in the paper**, which
is the open item the roadmap has carried since 7 October.

**3. Two cores, six nodes.** The workflow warns about this itself. Six
CockroachDB processes contending for two cores adds scheduling noise to the
quantity being measured, and it inflates both arms. A public repository would
get a 4-core / 16 GB runner at no cost. That is a decision about repository
visibility rather than a technical one, and it should be made before the final
measurements rather than after.

### Status

The gate is cleared properly. Placement measurably changes transaction latency on
a real six-region cluster, so the reward signal exists and the sim-to-real half of
the project is unblocked.

---

## Run 3 — Cluster pilot #3, 22 October 2026

**Commit** `f459c44`. GitHub Actions, `ubuntu-latest`, repository now **public**, so
a **4-core / 15 GB** runner. Total duration 27m 56s. Six nodes, replication
factor 3, **N = 1000 transactions per case**, up from 200.

Dispatched to settle the sample-size question the previous two runs left open.

### The gate still passes, and the interval halved

| | p50 (ms) | p95 (ms) | stdev (ms) |
|---|---|---|---|
| leaseholders co-located in us-east-1 | 441.5 | 446.6 | 78.4 |
| leaseholders spread across all six regions | 1015.3 | 1648.7 | 299.9 |

**p95 gap 1202.0 ms**, 95% bootstrap CI [1136.8, 1202.4].

Against run 2 at N = 200: the interval width fell from 155.2 ms to **65.6 ms**,
so quadrupling the sample more than halved it. That is the measurement the
limitations section of the midterm report promised and it can now be reported as
a methods result rather than as outstanding work. The point estimate still sits
at the interval's upper bound, so the degeneracy at the top is reduced rather
than removed: a difference of p95s remains a statistic whose upper tail resamples
poorly.

Latency injection accurate to 0.1 ms. Store mapping was again not the
configuration order (`us-west-2` came back as store 4 this time, store 2 last
time), which is the third run in a row confirming that node IDs follow join
order and must be resolved from the cluster.

### The finding is in the co-located arm, not the gap

The spread case is unchanged to within two milliseconds of run 2 on both
percentiles, 1015.3 against 1013.4 and 1648.7 against 1648.0. **The co-located
case got 62% slower**, 272.7 ms to 441.5 ms, despite twice the cores.

More cores and a slower result rules out CPU contention as the cause. What
changed is the offered load against one node: putting every lease in us-east-1
puts every write through one leaseholder, and at a thousand transactions that
node saturates in a way it did not at two hundred.

**This is the load-imbalance term in the reward, observed in a real system.**
Until now that term was justified by argument alone, namely that a policy could
cheat by piling all the work into one region. The cluster has now demonstrated
the cheat failing. It is a better result than the gap it was measured alongside
and it belongs in the paper ahead of it.

It also qualifies the simulator, whose analytic cost model has no queueing and
therefore cannot produce this effect. The simulator will understate the cost of
extreme concentration. Recorded in the threats to validity.


## Run 4 — Cluster pilot #4, 14 November 2026

**Run** `43565156341`, **commit** `df7a4bc`. GitHub Actions, 4 cores / 15 GB.
Six nodes, CockroachDB v25.3.0, `netem` shaping. Gate at N = 200 transactions per
case, 3 ranges touched per transaction. First run of harness pieces 1 and 2
(`scripts/placement_check.py`). Every number below is copied from the job log.

### The gate passes again

| | p50 (ms) | p95 (ms) | stdev (ms) |
|---|---|---|---|
| leaseholders co-located in us-east-1 | 213.8 | 216.0 | 38.3 |
| leaseholders spread across all six regions | 1002.4 | 1580.6 | 298.5 |

**p95 gap 1364.6 ms**, 95% bootstrap CI [1223.5, 1433.1].

### Harness pieces 1 and 2 pass on a real cluster

Read-back tracked every hand-issued move: a lease to another voter, a voter to an
empty region, a split. A lease to a region with no voter was refused by the
database ("lease target replica not found in RangeDescriptor"), as the
catalogue's `move_lease` rule assumes. The executor then ran 15 random legal agent
actions (seed 0); all 15 applied and the cluster matched the simulator's
catalogue after every one.

### Two findings that change the plan

**1. Every range of the harness table had two voters.** Raw `SHOW RANGES` rows
list two stores per range, for example `[1, 5]`. Nothing chose two.
`Claim: the harness table ran at 2 voters per range. Status: numerical.
Access: repository (job log). Not claimed: the cause, or the count on the gate's
own table, which this run did not print.` The likely cause, by reasoning only:
the replicate queue was frozen about ten seconds after `cockroach init`, before
up-replication from one replica had finished. Runs 1 to 3 used the same timing,
hence the correction at the top of this log. Fixed by
`fragalloc.harness.cluster.converge_replication`, which sets `num_replicas`,
waits until every range has exactly that many voters and no learners, then
freezes the rebalancer and reads each setting back (ADR-0015).

**2. Read-back is too slow for the step budget.** Median 5.397 s per read-back
(max 5.842 s, 5 reads); executor step median 16.10 s (max 18.95 s), rising as
the table split, against the 2 to 6 s budget in docs/harness-architecture.md.
`SHOW RANGES ... WITH DETAILS`, the only documented source of the leaseholder,
is documented as costly. Run 5 times it against
`crdb_internal.lease_holder(raw_start_key)` and requires the two to agree
(ADR-0016).

### Status

Pieces 1 and 2: pass, at an unintended replica count and too slowly. Run 5
repeats this at 3 voters (the paper's setting) and 2 voters (the second data
point), set explicitly.


## Training round, 14 November 2026: NOOP fix, and n-step returns

Eight Train agent runs on commit 70553b9: volatility 4.0, 1,000,000 steps,
w_migration 0.30, learner seeds 0 to 3, `n_steps` 1 and 3, evaluated on
held-out seeds 2000 to 2007. **RF 2 and nearest-replica reads**: these predate
ADR-0015 and ADR-0018 and are learner-side evidence, not headline results.
Numbers copied from each run's job summary (`gh run view --log`); imbalance is
not in the summary, so the objective below omits its term.

| seed | n=1 ms | n=1 GB | n=3 ms | n=3 GB |
|---|---|---|---|---|
| 0 | 142.04 | 396.0 | 134.98 | 333.0 |
| 1 | 151.15 | 336.2 | 138.87 | 418.5 |
| 2 | 141.28 | 285.7 | 142.83 | 300.2 |
| 3 | 145.50 | 364.1 | 141.65 | 206.2 |
| mean | 144.99 | 345.5 | 139.58 | 314.5 |

Baselines in the same runs: static 150.12 ms, follow 129.04 ms / 1086.5 GB,
random 151.64 ms / 184.2 GB. The masked agent before the NOOP fix: 144.96 ms,
414 GB (4 seeds).

- **The NOOP fix** (ADR-0013 amendment) left latency where it was (144.99
  against 144.96 ms) and cut data moved by about a sixth (345.5 against 414 GB).
- **n-step 3 against 1**, paired by learner seed: mean difference −5.41 ms
  (sd 5.80), 95% t-interval [−14.63, 3.81], paired t p = 0.16; Wilcoxon
  p = 0.25, which with four pairs cannot go below 0.125. Not distinguishable
  at this sample size. It is better on both latency and data moved in the
  point estimate, and costs nothing, so the RF 3 runs were meant to use n_steps 3.
  **Correction (22 November 2026):** only learner seed 1 (43674067630) did. The
  15 November runs for seeds 2 to 4 (43674455394, 43674558770, 43674597349) ran
  at the workflow default, n_steps 1. They were retrained at n_steps 3 on
  18 November; see "Retrain of learner seeds 2 to 4 at n_steps 3".
- Latency plus migration terms at w = 0.30 (imbalance omitted): n=1 1.502,
  n=3 1.443, follow 1.454, static 1.501. Not a claim of a win: the imbalance
  term is missing and the runs are RF 2.

### RF 3 baselines, both read paths (ADR-0018)

`scripts/run_experiment.py`, RF 3, volatility 4, 200 windows, seeds 2000 to
2007, policies static, random, follow and the new Lion-style co-location
baseline (`policies.LionStylePolicy`). Objective at w = 0.30 by
`score_objective.cost`, imbalance included.

| policy | nearest ms | nearest GB | nearest cost | strong ms | strong cost |
|---|---|---|---|---|---|
| static | 118.81 | 0.0 | 1.241 | 192.11 | 1.959 |
| random | 122.40 | 134.6 | 1.306 | 195.46 | 2.032 |
| follow | 93.50 | 867.7 | 1.148 | 148.81 | 1.712 |
| lion | 106.24 | 28.8 | **1.136** | 179.98 | 1.921 |

GB moved is identical under both read paths (the policies do not see reads
differently). Lion cuts cross-region transactions from 34% to 4% while moving
3% of follow's data; with nearest-replica reads it is the best baseline on the
objective, with strong reads follow is. Lion here omits its workload
prediction and, by design, has no term for client location.

## Run 5 — Cluster pilot #5, 14 November 2026

Five runs on commit 6babfc6 (Actions 43672955396, 43673069841, 43673170009,
43673237944, 43673292953), 4-core runners, RF 3. Four with strong reads, of
which two pinned to 2 CPUs; one with follower reads. A sixth, at RF 2
(43672996178), was still running when this was written. Numbers copied from
the job logs.

### The gate did not run, in any of the five

`converge_replication` timed out: `after 300 s, ranges not at 3 voters:
{74: 2}`. Cause, from the health snapshot taken 35 s after `cockroach init`:
node 1 held 74 replicas and the other five about 15 each, so the balancer was
frozen long before up-replication finished. Re-enabling the replicate queue
later left one node's queue to up-replicate the whole cluster, and range 74,
one of the gate table's ranges, was still at 2 when the wait expired. By the placement check,
five minutes on, every range was at 3. So **the 2 by 2 on N and cores has no
gate numbers yet.** Fixed: the pilot now waits until no range has fewer than 3
voters before freezing, and the timeout is 600 s.

### Pieces 1 to 4 pass on a real cluster

| check | result (range over five runs) |
|---|---|
| read-back and hand moves | pass |
| 15-step executor walk, cluster against the simulator's catalogue | all applied, all agree |
| lease source: DETAILS against the built-in | identical; 5.8 to 8.5 s against 0.87 to 1.42 s |
| executor step | median 2.22 to 3.58 s, maximum 5.56 s (budget 2 to 6 s) |
| driver, 2000 requests at fixed placement | 0 failures, 0 retries, gateways verified |
| episodes (static, follow, lion; 5 windows) | 0 suspect steps, 0 divergent steps |

`SHOW node_id`, `BEGIN TRANSACTION READ ONLY` and
`AS OF SYSTEM TIME follower_read_timestamp()` all work on v25.3.

### The cluster agrees with the simulator's RTT matrix

In run 43672955396 the leases sat in us-west-2 and 67% of requests came from
ap-southeast-1. Reads: p50 166.4 ms, p95 166.7 ms. The simulator's round trip
for that pair is 165 ms. With follower reads the read p50 is 0.65 ms.

### Episodes: five windows, one workload seed, volatility 4

| policy | strong reads, ms (4 runs) | follower reads, ms (1 run) | GB moved |
|---|---|---|---|
| static | 234.7 to 239.3 | 149.1 | 0.0 |
| follow | 145.7 to 148.6 | 98.9 | 19.9 |
| lion | 226.0 to 230.1 | 156.1 | 30.0 |

`Status: numerical. Not claimed:` a ranking. Five windows and one seed; the
ordering (follow well ahead of static, Lion close to static under strong
reads) matches the simulator's 200-window baselines in direction only.
Step time 7.8 to 12.4 s with strong reads, so a 200-window episode is roughly
26 to 41 minutes.

### Cores, from the steps that did run

Pinning all six nodes to 2 of 4 CPUs moved episode latency by under 2%
(static 234.8 against 239.3 ms, follow 146.0 against 146.0). No node averaged
above 20% of one core in any measured phase. At this load the cluster is not
CPU-bound, so the pilot 2 to pilot 3 slowdown is not reproduced here; the gate
re-run settles it.

### N

The p95 standard error never reached the target (42 ms at N = 2000 against
14.4). Latency is multimodal: reads about 166 ms, writes 428 ms, transactions
500 to 930 ms, so the p95 falls between modes. The reward uses the mean, so N
is now chosen on the standard error of the mean, with the p95 error still
reported. The raw latencies are in the run artifact, which could not be
downloaded here, so the mean-based N is read off the next run. A rough figure
from the per-kind summaries: standard deviation near 175 ms, so about 12 ms
at N = 200. `Status: conjectured` until that run.

## Run 5, continued: reruns and the RF 2 run (15 November 2026)

Four reruns on commit 532e3b0 (43677110819, 43677169901, 43677848382,
43677877555) and the RF 2 run from the first batch (43672996178).

- **Up-replication wait works**: every range had at least 3 voters after 43 to
  52 s, before the freeze.
- **The gate still did not run.** `after 600 s, ranges not at 3 voters:
  {74: 5}`. With the split queue frozen, the gate table's first range stays
  joined to the system range before it and keeps that range's five voters.
  Fixed: convergence now enables the split queue as well, and requires two
  consecutive clean polls. `Status: conjectured` until a run confirms it.
- **RF 2 is refused by CockroachDB** (ADR-0015 amendment). All six steps of
  that run failed on the zone configuration.
- **Lease transfers can be refused.** In three of four runs the follow
  heuristic's first action, `MOVE_LEASE(f3, r5)`, was rejected twice running,
  and follow then scored 221.6 to 225.8 ms over five windows instead of 146.1.
  The simulator allows that action. The refusal text was not logged; it is
  now. One run's Lion episode failed in `place` with "trying to add a voter to
  a store that already has a VOTER_FULL", a placement read taken whilst a
  relocation was still landing; `place` now re-reads and retries.
- **N.** Standard error of one step's mean latency at N = 200: 16.8 to 29.2 ms
  across four runs (it depends on where the leases sit). The per-step target
  of 14.4 ms needs N between 300 and 1000. Policies are compared on the mean
  over an episode, and 200 steps divide that error by about 14, to 1.2 to
  2.1 ms. **N = 200 stays** for evaluation; fine-tuning on the cluster would
  see the noisier per-step reward.
- **Cores.** Static episodes: 231.7 to 233.1 ms pinned to 2 CPUs, 232.4 ms on
  all 4. No effect at this load. The gate comparison is still outstanding.

## Training round, 15 November 2026: RF 3, strong reads (n_steps 3 for learner seed 1 only; seeds 2 to 4 ran at n_steps 1 and are superseded)

Four Train agent runs on commit 6babfc6 (43674067630, 43674455394,
43674558770, 43674597349): volatility 4.0, 1,000,000 steps, w_migration 0.30,
`read_consistency = primary_only`, held-out seeds 2000 to 2007. Numbers copied
from each job summary.

| policy | mean ms | GB moved |
|---|---|---|
| agent, four learner seeds | 163.18, 170.73, 162.74, 166.88 (mean 165.88) | 117.8, 278.1, 121.7, 216.7 (mean 183.6) |
| static | 192.11 | 0.0 |
| random | 195.46 | 134.6 |
| follow | 148.81 | 867.7 |
| Lion-style | 179.98 | 28.8 |
| best per window, fixed shards (bound) | 91.02 | 0.0 |

- The agent is 26.2 ms (13.7%) faster than static on every seed's 95%
  interval, 14.1 ms faster than Lion, and 17.1 ms slower than follow whilst
  moving 21% of follow's data.
- Latency plus migration at w = 0.30, imbalance omitted (not in the summary):
  agent 1.686, follow 1.618, Lion 1.804, static 1.921. With the baselines'
  imbalance terms (ADR-0018 table) follow is 1.712; the agent's needs its
  `summary.csv`. `Not claimed:` that the agent beats follow on the objective.
  On these numbers it does not.
- **Training has plateaued, not under-run.** Held-out latency sits between
  about 160 and 190 ms from step 50,000 to 1,000,000 with no downward trend,
  and the best checkpoint fell at steps 60,000, 110,000 and 170,000 in three
  of four runs. More steps are not the lever. The best checkpoint is chosen
  on three evaluation episodes, so the choice itself is noisy.
- 0.0% inapplicable actions on all four (masking); "Nothing" at most 1.2%.

## Run 6 — Cluster pilot, first fully clean run (15 November 2026)

Actions 43751092905, commit 18b0c0f, RF 3, strong reads, 4 cores, N = 200.

| gate arm | p50 ms | p95 ms |
|---|---|---|
| leaseholders co-located (us-east-1) | 293.6 | 441.7 |
| leaseholders spread over six regions | 1059.0 | 1779.5 |

p95 gap 1337.8 ms, 95% CI [1168.5, 1407.8]. Up-replication finished in 49 s;
table convergence took 3 s (the split-queue fix holds). Every harness, driver
and episode check passed; no lease move was refused.

The single-node saturation suggested by pilots 2 and 3 is not reproduced: in
the co-located arm the leaseholder node averaged 15.7% of one core (maximum
26.1%), and the arm's p50 by fifth of the run was 300.1, 290.5, 364.5, 294.9,
294.3 ms, with no drift. Pilots 2 and 3 ran on an under-replicated cluster.

## Cluster evaluation 1 — the trained agent on CockroachDB (15 November 2026)

Actions 43751004009, commit 18b0c0f. Model from Train agent run 43674558770
(simulator: 162.74 ms, 121.7 GB over seeds 2000 to 2007). One 200-window
episode per policy, workload seed 2000, volatility 4, RF 3, strong reads,
N = 200 requests per step, 2 workers per region. Numbers copied from the job
summary. Simulator columns: `run_experiment.py`, same seed and settings.

| policy | cluster ms | simulator ms | GB moved (cluster / sim) | imbalance (cluster / sim) | cluster cost, w = 0.30 |
|---|---|---|---|---|---|
| follow | 167.23 | 148.14 | 771.6 / 771.6 | 1.024 / 1.014 | 1.890 |
| agent | 192.79 | not run for this seed alone | 127.5 / n.a. | 0.801 / n.a. | 2.027 |
| Lion-style | 191.63 | 153.01 | 30.0 / 30.0 | 1.202 / 1.346 | 2.041 |
| static | 206.17 | 182.44 | 0.0 / 0.0 | 0.416 / 0.404 | 2.103 |

`Status: numerical.` One episode per policy and one workload seed, so no
interval across seeds. Within an episode the sampling error of the mean is
about 1 to 2 ms (Run 5), so agent against Lion (1.2 ms) is not a difference;
agent against static (13.4 ms) and against follow (25.6 ms) are.

- **The ranking on the objective carries over**: follow, agent, Lion, static,
  on the cluster as in the simulator.
- **The agent on the cluster** is 13.4 ms (6.5%) faster than static and
  25.6 ms slower than follow, moving 16.5% of follow's data. No action of
  the agent's was refused, and no step was suspect or divergent.
- **The cluster is slower than the model by a steady margin** for the
  policies whose actions all applied: static +23.7 ms (13.0%), follow
  +19.1 ms (12.9%). Data moved matches to the decimal.
- **Lion lost most in transfer** (+38.6 ms): 20 of its 200 actions were
  refused, all lease moves, all with `refusing to transfer lease ... because
  target may need a Raft snapshot: local replica not raft leader`. Lion moves
  a replica and then, in the next window, the lease onto it; CockroachDB will
  not hand a lease to a replica it cannot confirm has caught up. The
  simulator has no such rule. This also explains the refusals follow met in
  Run 5. `Not claimed:` that Lion is worse than the agent on a cluster; a
  Lion that retried a refused lease move would do better than this one.
- Step time 12.9 to 15.2 s; the whole run took 3 h 19 min.

## Volatility sweep at RF 3, strong reads (15 November 2026)

`scripts/run_experiment.py`, commit 18b0c0f, seeds 0 to 7, 200 windows,
`--read-consistency primary_only`, policies static, random, follow, lion,
best. Four runs, one per volatility, under `results/runs/20261116T032622Z-*`;
the table the paper uses is `results/recorded/sweep.csv`. Run in the sandbox,
not on Actions; the simulator is deterministic, so the manifests reproduce it.

| volatility | static | random | follow | Lion | bound | follow GB |
|---|---|---|---|---|---|---|
| 0.5 | 196.8 | 196.4 | 117.0 | 183.0 | 118.7 | 322.5 |
| 1 | 196.3 | 201.6 | 119.8 | 181.7 | 118.0 | 632.6 |
| 2 | 195.5 | 201.6 | 137.4 | 173.3 | 111.5 | 900.2 |
| 4 | 196.1 | 203.0 | 160.4 | 177.8 | 102.8 | 873.7 |

- The shape of the earlier sweep holds: static flat, bound improving, follow
  degrading, the follow-to-bound gap opening from -1.7 to 57.5 ms.
- Follow sits 1.7 ms *below* the bound at volatility 0.5: it moves replicas,
  the bound moves leases only.
- Retired: "at volatility 4 follow is indistinguishable from static under the
  objective". At RF 3 with strong reads, w = 0.30, follow scores 1.824 and
  static 2.002.
- Weight rescoring (paper Table IV): in simulation the agent is the cheapest
  policy for 0.50 < w < 1.82 (imbalance omitted); on the cluster's one seed it
  is never the cheapest (follow below w = 0.71, Lion above).

## Controls for the agent's trade, held-out seeds (16 November 2026)

`scripts/run_experiment.py`, run `20261116T225729Z-f4870a4f-controls-heldout-v4` (committed under `results/runs/`),
held-out seeds 2000 to 2007, volatility 4, 200 windows, `primary_only`.
Two new controls in `fragalloc.policies`: `ThrottledFollowPolicy` (follow
traffic that starts a move only every k windows and always finishes a
two-window relocation) and `ApplicableRandomPolicy` (uniform over applicable,
non-NOOP actions). Tests: `tests/test_control_policies.py`, both mutations
caught.

| policy | mean ms [95% CI] | GB moved | imbalance |
|---|---|---|---|
| follow | 148.81 [143.8, 153.7] | 867.7 | 0.935 |
| follow, every 2 | 157.18 [152.2, 162.0] | 696.3 | 0.907 |
| follow, every 4 | 171.82 [165.5, 178.1] | 405.1 | 0.794 |
| follow, every 8 | 185.84 [179.7, 192.4] | 157.6 | 0.746 |
| static | 192.11 | 0.0 | 0.382 |
| random (all actions) | 195.46 | 134.6 | 0.569 |
| random (applicable only) | 210.76 [206.7, 215.4] | 438.5 | 0.557 |
| agent, four learner seeds (Training round, 15 November) | 165.88 | 183.6 | not recorded |

- **Slowing the heuristic does not reproduce the agent's trade.** Every 4: the
  agent is 5.9 ms faster and moves less than half the data. Every 8: the agent
  is 20.0 ms faster for 26.0 GB more. `Not claimed:` an interval on the
  agent's side; its per-seed rows are in the training artifacts.
- **Undirected movement is harmful, not neutral.** Random over applicable moves
  is 18.7 ms slower than static hashing.
- Baseline rows (static, random, follow, Lion, oracle) reproduce
  `results/recorded/heldout-rf3.csv` exactly.

## Cluster evaluation 2 — workload seeds 2001 to 2003 (16 November 2026)

Actions 43954753671 (2001), 43954879894 (2002), 43954980773 (2003), commit
ac89a12, same model and settings as evaluation 1. All twelve episodes PASS,
no suspect or divergent step. Combined with evaluation 1 in
`results/recorded/cluster-eval.csv`; simulator columns for the baselines from
`run_experiment.py --seeds 3 --seed-start 2001` (sandbox, deterministic).

| seed | follow | agent | static | Lion | cost order (w = 0.30) |
|---|---|---|---|---|---|
| 2000 | 167.23 | 192.79 | 206.17 | 191.63 | follow, agent, Lion, static |
| 2001 | 175.11 | 203.60 | 234.44 | 276.40 | follow, agent, static, Lion |
| 2002 | 160.72 | 173.54 | 213.32 | 234.12 | follow, agent, static, Lion |
| 2003 | 172.86 | 199.49 | 226.82 | 204.89 | follow, agent, Lion, static |

`Status: numerical.` Four workload seeds, one learner seed.

- Follow cheapest and agent second on every seed. Agent faster than static on
  every seed (13.4 to 39.8 ms, mean 27.8 ms, 12.6%), slower than follow on
  every seed (12.8 to 28.5 ms), moving 14% of follow's data.
- Simulator offset, cluster minus simulator: static +22.0 to +33.7 ms (13.7%
  mean), follow +18.8 to +21.7 ms (13.5%), Lion +38.6 to +53.5 ms (23.8%).
  The per-seed order of the three baselines matches the simulator on every seed.
- Lion's extra loss is not explained by refusals: 0 refused on seed 2001,
  where its loss is largest. Concentration (imbalance 1.24) is a hypothesis.
- Refusals on 2002 and 2003 were in follow's episodes (6 and 4), which is why
  its GB moved there is below the simulator's (820.1 vs 840.2; 857.3 vs 878.0).
- Weight rescoring on the four-seed means: follow cheapest below w = 0.63,
  agent above (until static at w = 3.9); Lion never. Per-seed crossing 0.36 to
  0.73.
- Retired: "agent and Lion-style cannot be separated" (seed 2000 only).

## Agent numbers recovered from the archived artifacts (16 November 2026)

The nine Actions runs behind the paper were downloaded with `gh run download`
into `results/archive/` (55 MB). The four training runs' held-out
`summary.csv` files supply what the job summaries lacked:

- Agent imbalance on seeds 2000 to 2007, per learner seed: 0.888, 0.825,
  0.934, 0.923 (mean 0.893). Baselines on the same seeds (rerun 16 Nov):
  static 0.382, follow 0.935, Lion 1.170.
- Table IV's simulator rows now use the full objective. At w = 0.30 the agents
  score 1.738 to 1.832 against follow's 1.712. The agent is cheapest in
  simulation for 0.49 < w < 2.18 (was 0.50 to 1.82 with imbalance omitted).
- The cluster model (learner seed 3) in simulation on seeds 2000 to 2003:
  161.82, 172.05, 145.98, 168.16 ms (mean 162.0). Cluster minus simulator:
  +27.6 to +31.6 ms, 18.7% on average, between the baselines' 14% and Lion's
  24%.

## Exact per-window oracle (17 November 2026)

The greedy "per-window oracle" (each primary to its demand-weighted nearest
region, shard by shard) is replaced by an exhaustive search over all 6^6
primary assignments with followers nearest each primary
(`src/fragalloc/oracle.py`). With strong reads only two-phase commit couples
shards, so the search is exact: a true lower bound on any placement of the
starting shards. `tests/test_oracle.py` checks it against `cost.evaluate` on
sampled assignments (catches a planted error in the commit term and in the
follower wait), against 300 random placements, and against the greedy rule.

Sweep rerun (`results/runs/20261117T042521Z-*`); policies unchanged to the
digit, oracle only:

| volatility | old oracle | exact oracle | follow | gap (95% paired CI) |
|---|---|---|---|---|
| 0.5 | 118.7 | 100.1 | 117.0 | 16.9 [13.6, 20.5] |
| 1 | 118.0 | 99.3 | 119.8 | 20.4 [16.5, 24.5] |
| 2 | 111.5 | 93.4 | 137.4 | 43.9 [37.8, 50.1] |
| 4 | 102.8 | 85.0 | 160.4 | 75.4 [70.2, 82.9] |

Held-out seeds 2000 to 2007: oracle 76.47 ms (was 91.02).

- Retired: "under slow drift follow is within 2 ms of / below the oracle" and
  "the oracle is not a minimum". Follow is 16.9 ms (14%) above a true bound at
  volatility 0.5; the gap still grows with volatility.
- Also in this change: splitting claim narrowed (no split-disabled agent was
  trained), SLOG and the two masking papers cited, simulator's instant
  migration and split renumbering added to threats to validity.

## Trade-off figure, ablation sentence and tail latency (17 November 2026)

No new runs. From existing evidence:

- `results/recorded/tradeoff.csv` and `paper/figures/ccgrid/tradeoff.png`
  (Fig. 3): latency against data moved, simulator and cluster. Every learner
  seed sits below the line traced by follow throttled to every 2, 4, 8 windows.
- Ablations in Section III, from ADR-0013 (unmasked: 79.9 to 89.8%
  inapplicable, uniform policy 80.4%) and the 14 November round (n = 3 vs 1:
  -5.41 ms, paired 95% t-interval [-14.63, 3.81], RF 2).
- Tails. Simulator, held-out seeds, mean per-window p95 (`mean_tail_latency_ms`
  in the archived Train summaries): agents 528.87, 558.10, 517.27, 540.23;
  follow 517.05; Lion 513.97; static 622.71. Cluster, mean per-step p95 from
  the archived step CSVs, four seeds: follow 552.1, agent 618.2, static 689.8,
  Lion 698.7; agent below static on every seed. Step-CSV means reproduce the
  recorded cluster means to the hundredth on all sixteen episodes.

## Agents at volatility 2, unchanged (17 November 2026)

The four archived best models (trained at volatility 4) run at volatility 2
on held-out seeds 2000 to 2007, `primary_only`, on Tino's laptop
(`results/runs/20261117T051144Z-1ead496b-gen-v2-*`,
`results/recorded/generalization-v2.csv`). Reproduction check first: the same
code and the learner-seed-2 model at volatility 4 give 162.74 ms / 121.67 GB,
the recorded figures exactly.

| policy | ms | GB | imbalance | mean p95 |
|---|---|---|---|---|
| agents (4 learner seeds) | 170.50, 166.47, 166.40, 167.53 (mean 167.73) | 127.0, 252.6, 100.8, 368.4 | 0.82 to 0.97 | 532 to 572 |
| follow | 126.93 | 877.4 | 0.888 | 458.0 |
| Lion-style | 177.24 | 25.0 | 1.075 | 517.4 |
| static | 192.83 | 0.0 | 0.333 | 631.4 |
| oracle | 88.56 | | | |

`Status: numerical.` The agent holds its latency (167.7 against 165.9 at
volatility 4) and stays ahead of static and Lion-style, but follow improves
under slower drift and leads by 41 ms. The trained policy does not adapt its
trade to the slower workload. Not claimed: anything about an agent trained at
volatility 2.

## Second in-project review: findings checked and acted on (17 November 2026)

An adversarial reading by a separate AI session (not peer review) of
Sections I to IV-D. Every finding below was checked against the code or the
archived runs before the paper changed.

- **Splitting and the data saving.** Confirmed: agents finish with 12.4 to
  19.8 shards (archived Train summaries), their replica moves carry 1.9 to
  6.0 GB against 10 GB for fixed-shard policies. New control: follow,
  throttled follow, Lion and static started on 12 and 20 equal shards
  (`results/runs/20261117T054022Z-*-presplit{12,20}-heldout-v4`). Follow:
  177.49 ms / 448.8 GB (12 shards), 197.40 ms / 257.6 GB (20 shards); static
  212.75 and 229.13 ms. Even splitting makes every fixed policy slower and
  does not reproduce the agent's 165.9 ms / 183.6 GB.
- **Lease churn.** Confirmed from the cluster step CSVs: agent 131 to 188 lease
  moves per episode, 36 to 81 of them A-B-A returns; follow 111 to 122 and
  none; Lion 14 to 41.
- **Intervals** (paired by workload seed, mean of the four agents, percentile
  bootstrap as in `run_experiment.bootstrap_ci`): agent minus static -26.23
  [-31.05, -20.78]; minus follow 17.07 [11.12, 22.49]; minus Lion -14.10
  [-30.89, 2.53] (includes zero: "faster than Lion" withdrawn as a firm claim);
  minus follow every 4 -5.94 [-12.41, 0.69]; minus follow every 8 -19.96
  [-27.46, -12.62]; objective cost minus follow +0.064 [0.004, 0.115].
  Per-learner crossing weights against follow: 0.37, 0.71, 0.37, 0.55.
- **Oracle wording.** The gap is now called an upper bound on the room for a
  policy, and the "within 15%" line corrected (16.9% above the oracle).
  Oracle held-out run committed: `20261117T042521Z-f4870a4f-heldout-oracle`.
- **Model vs CockroachDB commit.** Disclosed in threats: the model charges two
  rounds from a participant coordinator; CockroachDB uses gateway coordination
  and parallel commits.
- Abstract premise reworded (CockroachDB rebalances by load); "transaction
  latency" corrected to request latency; reproducibility statement corrected;
  Lion idle share 88.5% not "90 to 95%"; related work scoped, Hilprecht et al.
  (SIGMOD 2020) and DynaMast (ICDE 2020) added from Crossref metadata.
- Note on numbering: the paper's "learner seed 3" is the code's seed 2 (run
  43674558770); the paper counts from 1.
- Not acted on: a forecast-driven heuristic and a geography-aware Lion (new
  baselines, not wording); Volley, P-Store, Squall, Detock, Tuba (unverified).

## Cluster: second agent and CockroachDB; agents trained at w = 0.6 (17 November 2026)

Cluster runs 44021436487 (2000), 44021534976 (2001), 44021600636 (2002),
44021771876 (2003), commit 153f6b8, `policies: agent crdb`, model 43674067630
(learner seed 1). Training runs 44018419041 (seed 0) and 44018524015 (seed 2),
commit 9d5de71, `W_MIGRATION: 0.6`. Numbers copied from the job summaries;
recorded in `results/recorded/cluster-eval.csv` and `tradeoff.csv`.

- **Second agent (learner seed 1).** 202.39 / 202.52 / 190.53 / 198.00 ms
  (mean 198.36), p95 615 / 667 / 548 / 620, GB 128.7 / 62.1 / 38.7 / 89.3,
  cost 2.115 / 2.110 / 1.983 / 2.074. Slower than follow on every seed (25.1
  to 35.2 ms), faster than static on every seed (3.8 to 31.9, mean 21.8,
  9.9%). On seed 2000 its cost is above static (2.103) and Lion (2.041).
  Offset from its simulator latency (169.00 / 166.21 / 153.91 / 175.45, from
  the archived summary.csv): 33.4 / 36.3 / 36.6 / 22.6 ms, 19.6%.
- **Refusals.** 120 / 108 / 134 / 1 of its 200 actions refused ("target may
  need a Raft snapshot"); 109 / 86 / 104 / 0 repeat the refused action of the
  previous window; longest run 43 / 18 / 43 / 1. Counted from the step lines
  of the logs (agent episode only). Tech-debt 18.
- **CockroachDB (ADR-0021).** 209.07 / 205.70 / 226.57 ms on 2000 / 2002 /
  2003, GB 0, lease changes 15 / 8 / 2, cost 2.156 / 2.108 / 2.320. Seed 2001
  failed at reset (`PlacementError`, replicas [1, 2, 5] for [1, 2, 3]),
  tech-debt 17. Rerun alone as 44160407645 (commit 4334e5d): 248.46 ms,
  p95 827.3, GB 0, lease changes 9, imbalance 0.467, cost 2.531, divergent
  7. Four seeds: 222.45 ms (2.3 above static), p95 694, imbalance 0.542,
  cost 2.279.
- **w = 0.6 training.** Held-out (seeds 2000 to 2007, volatility 4): learner
  seed 1 169.46 ms [163.77, 174.71], 181.3 GB; learner seed 3 170.61 ms
  [165.98, 176.21], 224.5 GB. Same seeds at w = 0.30: 163.18 / 117.8 and
  162.74 / 121.7. Higher weight, more movement and higher latency; two runs
  do not separate this from run spread (118 to 278 GB at w = 0.30). Cost at
  w = 0.6 (imbalance 0.735 / 0.874 from the archived summary.csv): 1.823 /
  1.861 against follow 1.842 (paired diffs -0.019 [-0.067, 0.028], +0.019
  [-0.026, 0.066]) and against the w = 0.30 agents of the same learner seeds,
  1.756 / 1.757 (+0.066 [0.014, 0.114], +0.103 [0.052, 0.155]). Recorded in
  `results/recorded/w06.csv`.
- Paper: Table V gains Agent 1 and CockroachDB rows; Q5 gains two
  paragraphs; weight analysis reports the trained w = 0.6 agents; abstract,
  introduction, threats and conclusion follow.

## Archive trimmed (17 November 2026)

The cluster artifacts of runs 43954753671, 43954879894, 43954980773 and
44021436487 to 44021771876 carried a copy of the checked-out `results/`
(recorded tables, runs and, for the 4402 runs, the whole archive), about
55 MB each. Those nested copies are removed; each run keeps its own episode
CSV/JSON, logs and health files. `cluster-eval.yml` now uploads only
`results/*.csv` and `results/*.json`. `agent-runs.csv`, `baselines-heldout.csv`,
`score_objective.py` and `plot_agent_frontier.py` are marked superseded (early
round, commit f459c44; not used by the paper).

## Retrain of learner seeds 2 to 4 at n_steps 3 (18 November 2026; recorded 22 November)

The 15 November Train runs for learner seeds 2 to 4 (43674455394, 43674558770,
43674597349) used n_steps 1, the workflow default, although the paper and this
log said n_steps 3; only seed 1 (43674067630) used 3. Seeds 2 to 4 were
retrained on commit 4e0b643 (training code identical to 6babfc6 apart from the
n_steps input): 44223156822, 44223258603, 44223466130. All four learner seeds
are now n_steps 3, volatility 4.0, 1,000,000 steps, w_migration 0.30,
primary_only, held-out seeds 2000 to 2007. The baselines are identical to before.

| learner seed | run | ms | GB | imbalance | mean p95 | best checkpoint |
|---|---|---|---|---|---|---|
| 1 | 43674067630 | 163.18 | 117.8 | 0.889 | 528.9 | 900,000 |
| 2 | 44223156822 | 164.36 | 186.9 | 0.918 | 528.2 | 580,000 |
| 3 | 44223258603 | 168.50 | 139.6 | 0.855 | 532.4 | 40,000 |
| 4 | 44223466130 | 166.58 | 250.8 | 0.971 | 525.5 | 810,000 |

- Four-agent mean 165.66 ms and 173.8 GB. Against static: 26.5 ms faster
  (13.8%) [21.3, 31.2]. Against follow: 16.8 ms slower [11.3, 22.6], moving 20%
  of its data. Against Lion-style: 14.3 ms faster [-1.9, 30.7]. All paired
  bootstrap intervals over workload seeds (bootstrap_ci, 10,000 reps, seed 12345).
- Objective cost at w = 0.30: agents 1.738 to 1.801, follow 1.712, mean
  difference +0.062 [0.006, 0.118]. The agents' mean is cheapest for w in
  [0.48, 2.34]. Per learner seed the follow crossing is 0.37 to 0.59.
- n_steps 3 minus n_steps 1, same code seeds, RF 3: -6.4, +5.8 and -0.3 ms
  (mean -0.3 [-3.0, 2.3]). No measurable effect under the reported protocol.
- w = 0.6 against w = 0.30 at w = 0.6: seed 1 +0.066 [0.014, 0.114]; seed 3
  +0.048 [-0.033, 0.117], no longer distinguishable from zero.
- Validation (seeds 1000 to 1002) after step 50,000: 158 to 202 ms, drifting
  down by 0.2 to 1.3 ms per 100,000 steps. The earlier "plateaued, not
  under-run" note no longer holds for this round.
- Volatility 2, unchanged agents: 170.50 (seed 1, existing run), 167.40, 168.52,
  170.09 ms; 127 to 252 GB. Follow is 126.93 ms, 42 ms ahead.
- `Not claimed:` that three-step returns help, or that seed 3's step-40,000
  checkpoint is representative. The cluster agent 3 rows predate this
  retrain and are pending a cluster rerun.
- Volatility 2 (agents trained at 4, run unchanged): seeds 2 to 4 rerun with the
  retrained models, results/runs/20261123T0358*-gen-v2-<run>: 167.40, 168.52,
  170.09 ms; with seed 1 (170.50) mean 169.13 ms, follow 126.93 (42.2 ms ahead).
  Recorded in results/recorded/generalization-v2.csv.
