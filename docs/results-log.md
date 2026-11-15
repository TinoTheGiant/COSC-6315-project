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
  point estimate, and costs nothing, so **the RF 3 runs use n_steps 3**.
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
