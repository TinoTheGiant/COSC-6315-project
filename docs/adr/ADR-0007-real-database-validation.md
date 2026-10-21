# ADR-0007: Train in simulation, validate on a real database, and use CockroachDB for it

**Status:** **Superseded by [ADR-0008](ADR-0008-database-selection.md). Retained for the record; two of its central factual claims are wrong. See the correction notice below before reading further.**
**Date:** 2026-09-23
**Superseded:** 2026-09-29
**Deciders:** Tinotenda Kaseke, with the course instructor
**Supersedes:** the MongoDB half of [ADR-0001](ADR-0001-simulate-rather-than-measure.md)

## Correction notice (2026-09-29)

Two claims below did not survive verification against CockroachDB's source and
documentation. Both were mine, and both pointed this decision in the wrong
direction.

**First, "Reading 1 is not achievable" is false.** The paragraph asserts that a
CockroachDB placement change is carried out by background queues with no public
API to force them. There is such an API, and it is ordinary SQL:
`ALTER RANGE <id> RELOCATE VOTERS FROM <store> TO <store>` and
`ALTER RANGE <id> RELOCATE LEASE TO <store>`. Both block. `initializeRaftLearners`
in `pkg/kv/kvserver/replica_command.go` states its own contract: it "adds etcd
LearnerNodes ... and synchronously sends them an initial snapshot to upreplicate.
Once this successfully returns, the callers can assume that the learners were
added and have been initialized via that snapshot." The statement reports `ok`
or the actual error text per range in its own result set. Training against a
real cluster is therefore *slow*, not impossible, and the reason to keep the
simulator as the training environment is wall-clock budget alone, not a missing
primitive.

**Second, the whole Option A mapping is built on the wrong primitive.** It routes
every action through `CONFIGURE ZONE USING`, and then spends three paragraphs on
the limitations that follow: zone configs attaching to schema objects rather than
ranges, `CONFIGURE ZONE` replacing a config instead of patching it, and the
resulting need to pre-partition into 256 partitions. `ALTER RANGE ... RELOCATE`
makes all three disappear. It names a range and a store directly, needs no
partitioning scheme, and carries no read-modify-write hazard.

The argument this ADR actually got right, and which [ADR-0008](ADR-0008-database-selection.md)
carries forward unchanged, is the Cassandra assessment: placement in Cassandra is
a pure function of the partition key and the token ring, so no command can name a
shard and a destination node. Independent screening confirmed it, and added that
with vnodes even `nodetool move` is unavailable.

## Context

The instructor has said the project should involve a real database, naming
Cassandra or CockroachDB. ADR-0001 already planned a real-cluster validation
harness, but named MongoDB and scoped it as a stretch goal with a week 6
go/no-go. That plan and this instruction now need reconciling, and the choice of
database is no longer free.

Three readings of "should have a real database" are possible, and they differ by
weeks of work:

1. **Results must be produced on a real database.** The agent trains against a
   real cluster and every reported number comes from it.
2. **The project must demonstrate on a real database.** The agent trains in
   simulation; a real cluster is used to show the simulator's conclusions hold.
3. **The project must be grounded in a real system's primitives.** The action
   space is shown to map onto real SQL, with a small physical demonstration.

~~Reading 1 is not achievable. A CockroachDB placement change is carried out by
background queues whose scan cadence is measured in minutes, not milliseconds,
and no public API forces them to run.~~ **Wrong, see the correction notice.** A
synchronous public API exists. Reading 1 is achievable but unaffordable: a
placement move that blocks on a snapshot transfer costs seconds, so a training
run of tens of thousands of steps is weeks of wall clock. The simulator runs a
step in about 0.5 ms, which is what makes the sweeps in Objectives 3, 5 and 6
affordable at all. The conclusion stands; the reason for it is budget, not
capability.

Readings 2 and 3 are achievable in the five weeks remaining, and 2 strictly
contains 3.

## Decision

Keep the simulator as the training environment. Add a real CockroachDB cluster
as a **validation and demonstration harness**: three regions, six nodes, on one
laptop under Docker, with wide-area latency injected by Toxiproxy.

The harness answers one question, and the paper should state it that narrowly:
**does a real cluster rank placements the way the simulator does?** Not "do the
numbers match", which they will not, but "when the simulator says layout A beats
layout B, does the cluster agree?"

## Options Considered

### Option A: CockroachDB

| Dimension | Assessment |
|-----------|------------|
| Fits the cost model | **Strong.** Real distributed SQL transactions, real two-phase commit, real lease placement. The commit term in `fragalloc.cost` corresponds to something the cluster actually does |
| Fits the action space | **Partial.** Four of five actions map cleanly; merge cannot be forced |
| Placement control | Zone configs with `constraints`, `voter_constraints`, `lease_preferences` |
| Observability | `crdb_internal.ranges_no_leases`, `crdb_internal.zones`, `SHOW RANGES` |
| Instructor named it | Yes |

The mapping, verified against current CockroachDB behavior:

| Action | Mechanism | Notes |
|--------|-----------|-------|
| `SET_PRIMARY(f, r)` | `ALTER PARTITION ... CONFIGURE ZONE USING lease_preferences = '[[+region=r]]'` | |
| `ENSURE_REPLICA(f, r)` | `constraints = '{"+region=r": 1}'` | counted constraint, leaves the rest free |
| `DROP_REPLICA(f, r)` | `constraints = '[-region=r]'` | excludes the region from all replicas |
| `SPLIT(f)` | `ALTER TABLE ... SPLIT AT VALUES (k)` | synchronous, sub-second, the most reliable action |
| `MERGE(f)` | `UNSPLIT AT` plus reconverged zone configs | **cannot be forced.** The merge queue decides |

**Pros:** the transaction latency the project optimizes is a real quantity in a
real system; the placement primitives are first-class SQL; the instructor named
it.
**Cons:** three structural constraints, each of which shapes the work.

1. **Zone configs attach to schema objects, not to arbitrary ranges.** To get
   independently controllable fragments, the table must be partitioned up front,
   one partition per keyspace cell. The simulator's 256 cells become 256
   partitions, and a fragment becomes a set of cells sharing a zone config.
2. **`CONFIGURE ZONE USING` replaces the whole config, it does not patch one
   field.** An action executor that sends only `constraints` silently wipes the
   `lease_preferences` a previous action set. The executor has to read the
   current config back and merge client-side.
3. **Merge is best-effort.** No paper claim can depend on a merge completing by
   a given tick. Merges get reported in aggregate, splits get reported with
   timing.

### Option B: Cassandra

| Dimension | Assessment |
|-----------|------------|
| Fits the cost model | **Weak** |
| Fits the action space | **Weak** |
| Placement control | Per-datacentre replication factor via `NetworkTopologyStrategy`. No per-key-range placement |
| Instructor named it | Yes |

**Pros:** genuinely geo-distributed, easy to run in Docker, well documented.
**Cons:** the fit is poor in exactly the places this project cares about.
Cassandra places data by consistent hashing over a token ring. There is no
supported way to say "this key range should live in Frankfurt", which is the
agent's primary action. Replication is set per keyspace and per datacentre, not
per fragment. And Cassandra has no distributed ACID transactions or two-phase
commit, so the commit term that carries the project's central argument has no
counterpart in the system.

Choosing Cassandra would mean either abandoning the transaction-latency
framing or measuring something the database does not do.

### Option C: MongoDB, as ADR-0001 originally planned

| Dimension | Assessment |
|-----------|------------|
| Fits the cost model | Moderate |
| Fits the action space | **Strongest of the three** |
| Placement control | Zone sharding: `updateZoneKeyRange`, `moveRange` |
| Instructor named it | No |

**Pros:** the five actions map more literally than in CockroachDB. `splitAt`
splits on demand, [`mergeChunks`](https://www.mongodb.com/docs/manual/reference/command/mergechunks/)
merges on demand, and a zone key range can be reassigned to a zone directly.
Every action is explicit and synchronous, which CockroachDB's merge is not.
Recent versions also run an
[AutoMerger](https://www.mongodb.com/docs/manual/core/automerger-concept/) in
the background, which would need disabling for a controlled experiment.
**Cons:** the instructor did not name it, and cross-shard transactions are a
weaker match for the cost model than CockroachDB's distributed SQL.

## Trade-off Analysis

The honest summary is that **MongoDB maps the actions better and CockroachDB
maps the cost model better.**

That tips to CockroachDB, for a reason specific to this project. The claim is
about *transaction latency* net of migration cost under drifting workloads. The
two-phase commit term is where the argument lives: a transaction whose fragments
sit in one region commits locally and pays nothing, and that is the whole
incentive to co-locate. CockroachDB actually does that. MongoDB's cross-shard
transactions exist, but the mechanism the cost model describes is CockroachDB's.

The cost of choosing it is the merge limitation. That is survivable because
merge is the less important half of the fragmentation action: splitting is what
separates divergent populations, merging is what recovers from over-splitting.
Reporting merges in aggregate rather than per tick is a real but modest loss.

Cassandra is set aside on fit, not on difficulty, and that reasoning should be
put to the instructor explicitly rather than assumed.

## Consequences

- The simulator keeps its role. Every sweep, ablation and training run stays
  where it is, and none of the existing work is discarded.
- The paper gains its strongest missing piece. [ADR-0001](ADR-0001-simulate-rather-than-measure.md)
  named internal-consistency-without-external-validity as the largest blind
  spot, and `docs/open-questions.md` item 7 still lists it. This closes it.
- A new module is needed, `fragalloc/harness/`, holding the SQL executor, the
  placement reader and the workload driver. It should depend on
  `fragalloc.cost` and `fragalloc.catalog` and nothing above them
  ([ADR-0005](ADR-0005-simulator-independent-of-gymnasium.md) already keeps
  those importable without Gymnasium).
- The physical cluster is scoped to three regions, matching
  `configs/reduced-tabular.json`, not the full six. Six physical regions is
  effort spent on nothing the validation needs.
- Six nodes, two per region. At one node per region, `DROP_REPLICA` forces the
  replication factor down as a side effect, which entangles the action with a
  durability trade-off the project does not mean to model.
- Latency comes from Toxiproxy rather than `tc`/`netem`. The CockroachDB image
  ships no `iproute2`, netem needs a privileged sidecar sharing the node's
  network namespace, and Toxiproxy can change latency mid-run, which the
  volatility experiments may want.
- On Windows: Docker Desktop must be on the WSL2 backend, and node store
  directories must be named Docker volumes, never bind mounts onto
  `C:\Users\...`. A bind-mounted store injects disk latency into the one signal
  the experiment is trying to isolate.
- Per-transaction latency is timed client-side in the driver.
  `crdb_internal.statement_statistics` aggregates by statement fingerprint, so
  it cannot attribute a single transaction to a single placement decision. It is
  corroboration, not ground truth.

## Action Items

1. [ ] **Ask the instructor which of the three readings is meant.** Nothing else
   here should start until that is answered. The expected answer is reading 2,
   and the question to ask is narrow: *does the project need its results
   produced on a real cluster, or does it need to demonstrate that the
   simulator's conclusions hold on one?*
2. [ ] Raise the Cassandra fit problem in the same conversation. If the
   instructor requires Cassandra specifically, the project's framing has to
   change, and that is a week 3 decision rather than a week 7 discovery.
3. [ ] Confirm Docker Desktop is installed and on the WSL2 backend.
4. [ ] Week 1 of this effort: stand up three nodes, confirm the partition-level
   zone config limitation on the actual cluster, and measure how long a lease
   preference takes to take effect. Those three facts govern everything after.
5. [ ] Write `docs/validation-plan.md`: which placements get ranked, on what
   topology, under what injected latencies, and what agreement statistic counts
   as a pass. Fix the threshold in advance, before seeing results.
6. [ ] Revise `docs/roadmap.md`. This is a new workstream in a schedule with no
   spare room; something else gives.

## Sources

- [mergeChunks, MongoDB Manual](https://www.mongodb.com/docs/manual/reference/command/mergechunks/)
- [The AutoMerger, MongoDB Manual](https://www.mongodb.com/docs/manual/core/automerger-concept/)
- [Merge Chunks in a Sharded Cluster, MongoDB Manual](https://www.mongodb.com/docs/manual/tutorial/merge-chunks-in-sharded-cluster/)
- [Sharded Cluster Balancer, MongoDB Manual](https://www.mongodb.com/docs/manual/core/sharding-balancer-administration/)
