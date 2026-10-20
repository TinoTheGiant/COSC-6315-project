# Results log

Every real run against a real cluster, in order, with what it changed. A lab
notebook rather than a summary: entries are not edited once written, and a later
entry corrects an earlier one rather than rewriting it.

Simulator-only results are not recorded here. They live in `results/` and are
labelled as simulator throughout.

---

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
