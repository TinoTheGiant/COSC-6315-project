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
