# ADR-0008: Build the training environment on Citus, and keep CockroachDB as the fallback

**Status:** **Superseded by [ADR-0009](ADR-0009-cockroachdb-for-sim-to-real-parity.md).** The
twenty-one-system screen below stands and remains the project's reference for what
each candidate can and cannot do. Its *conclusion* does not: the instructor has
since approved sim-to-real pre-training, which makes cost-model parity between the
simulator and the cluster decisive, and Citus at replication factor 1 cannot
provide it. ADR-0009 explains the reversal and reinstates CockroachDB.
**Date:** 2026-09-29
**Superseded:** 2026-10-07
**Deciders:** Tinotenda Kaseke, with the course instructor
**Supersedes:** [ADR-0007](ADR-0007-real-database-validation.md) in full
**Amends:** [ADR-0001](ADR-0001-simulate-rather-than-measure.md), which named MongoDB

## Context

The instructor requires the project to run against a real database rather than a
simulator, and is not restricting the choice. [ADR-0007](ADR-0007-real-database-validation.md)
chose CockroachDB, but it did so on two claims that later verification broke: it
asserted that no public API can force a CockroachDB placement change (false, and
the correction notice on that ADR records it), and it built its entire action
mapping on zone configs rather than on the direct per-range relocation statement
that actually exists. With both errors removed the choice reopens, so the field
was screened properly rather than narrowed by assumption.

Twenty-one systems were screened. The screen was designed around one observation
that turns out to be decisive and that is easy to miss.

### The criterion that decides this: synchrony

An RL environment must satisfy a contract. `env.step(action)` returns, and the
latency measured immediately afterwards is attributable to that action. If a
placement command merely enqueues a request into a background scheduler and
returns before the data has moved, the agent measures the *previous* placement
and credits it to the *new* action. Every reward is then bound to the wrong
transition, the Markov property fails, and the agent learns the statistics of the
scheduler's queue rather than the geography of the workload. Worse, several of
these schedulers may abandon a queued operation, so an action can have no effect
at all whilst reporting success.

This is the single most common failure mode in the field, because the
architectural instinct of nearly every distributed database is to treat placement
as the system's business and hide it from the operator. That instinct is precisely
what this project needs to override.

A command passes criterion 4 if it blocks until the destination holds the data.
It also passes, with a penalty, if it returns early but offers a per-shard
completion signal that can be polled to a defined terminal state. It fails if the
only signal is cluster-global, or if the operation can silently time out.

### The eight criteria

1. **Licence.** OSI-approved open source, free for a multi-node academic cluster,
   no key, no telemetry obligation, no throttle.
2. **Real horizontal sharding.** Different nodes hold different rows. Full
   replication only is a failure.
3. **Commandable placement.** A public command naming a specific shard and a
   specific target node.
4. **Synchrony.** As above. Decisive.
5. **Split and merge on demand.**
6. **Add or remove a replica of one shard on demand.**
7. **Cross-shard transactions whose latency depends on placement.** The reward
   signal is transaction latency, so a system without distributed transactions
   has nothing for the reward to refer to.
8. **Three or more shard-holding nodes on one 16 GB laptop**, plus the automatic
   rebalancer being fully disableable, plus programmatic placement readback.

## Decision

**Build the environment on Citus**, the PostgreSQL extension, under AGPL-3.0.

The step function is a single blocking SQL call:

```sql
SELECT citus_move_shard_placement(shard_id, source_node_id, target_node_id,
                                 shard_transfer_mode => 'block_writes');
```

It either returns, meaning the shard has been copied, the target placement row
inserted, the source placement dropped and worker metadata synchronised, or it
raises and rolls back leaving the cluster untouched. The function's own header
comment in `src/backend/distributed/operations/shard_transfer.c` states it: "If
the move fails at any point, this function throws an error, leaving the cluster
without doing any changes in source node or target node." There is no scheduler,
no job id, no polling loop, and no timeout to defend against.

Re-fragmentation uses the companion, which splits and places in the same
synchronous call:

```sql
SELECT citus_split_shard_by_split_points(shard_id, ARRAY['...'], ARRAY[node_ids],
                                        shard_transfer_mode => 'block_writes');
```

Placement is read back in plain SQL:

```sql
SELECT s.shardid, s.shardminvalue, s.shardmaxvalue, n.nodeid, n.nodename
FROM pg_dist_shard s
JOIN pg_dist_placement p ON s.shardid = p.shardid
JOIN pg_dist_node     n ON p.groupid  = n.groupid;
```

**Keep CockroachDB as the named fallback**, to be invoked only if Action Item 1
resolves in a way that puts replica placement back in scope.

## Screening results

Legend: PASS, PARTIAL, FAIL, `?` not established.

| System | 1 Licence | 2 Shards | 3 Targeted cmd | 4 **Synchronous** | 5 Split/merge | 6 Replica | 7 Cross-shard txn | 8 16 GB | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| **Citus** | **AGPL-3.0, OSI** | PASS | `citus_move_shard_placement` | **PASS, from source** | split only | PARTIAL | **2PC** | **4 Postgres** | **CHOSEN** |
| CockroachDB | source-available, key needed | PASS | `ALTER RANGE ... RELOCATE` | **PASS, from source** | split only | PASS | serializable | 3 procs | **FALLBACK** |
| ScyllaDB 6.2.x | AGPL-3.0, OSI (6.2.x only) | PASS | `tablets/move` | **PASS, from source** | no API | PASS | **none** | 3 containers | ELIMINATE |
| MongoDB | SSPL, not OSI | PASS | `moveRange` | **PASS, from source** | PASS | FAIL | PASS | 11 to 13 procs | ELIMINATE |
| TiDB / TiKV | Apache 2.0 | PASS | `operator add transfer-region` | FAIL, may time out | **both** | PASS | 2PC | 5 procs, hostile | ELIMINATE |
| YugabyteDB | Apache 2.0 | PASS | `change_config` | FAIL, bootstrap after return | split only | PASS | PASS | ~9 procs | ELIMINATE |
| Apache HBase | Apache 2.0 | PASS | `move 'ENC','srv'` | **PASS, from source** | async + Future | PASS | **single-row only** | HDFS + ZK + JVMs | ELIMINATE |
| Elasticsearch | ELv2 default, AGPL opt-in | PASS | `_cluster/reroute` | FAIL, state update only | new index only | index-wide | **none** | 3 JVMs, tight | ELIMINATE |
| OpenSearch | Apache 2.0 | PASS | as above | as above | as above | index-wide | **none** | as above | ELIMINATE |
| ArangoDB | BUSL 1.1, 100 GB cap | PASS | `moveShard` | FAIL, 202 + jobId | `?` | `?` | `?` | 5 to 7 procs | ELIMINATE |
| Apache Cassandra | Apache 2.0 | PASS | **none exists** | n/a | no shard object | FAIL | LWT single-partition | heap = half RAM | ELIMINATE |
| ClickHouse | Apache 2.0 | PASS | **static config** | n/a | partition-local | FAIL | **not as a whole** | light | ELIMINATE |
| FoundationDB | Apache 2.0 | PASS | **none exists** | n/a | FAIL | FAIL | strictly serializable | light | ELIMINATE |
| Couchbase CE | `?`, 5 nodes / 4 cores | PASS | **none found** | n/a | fixed 1024 | bucket-level | PASS | `?` | ELIMINATE |
| Vitess | Apache 2.0 | PASS | leadership only | `?` | `Reshard`, minutes | PARTIAL | 2PC | heavy | ELIMINATE |
| Google Spanner | emulator Apache, Omni proprietary | emulator has no nodes | **none exists** | n/a | FAIL | FAIL | PASS | n/a | ELIMINATE |
| SingleStore | proprietary | PASS | `?` | `?` | `?` | `?` | PASS | Dev Image | ELIMINATE |
| Greenplum | **closed by Broadcom, 2024** | PASS | `gpexpand` only | FAIL | FAIL | FAIL | PASS | heavy | ELIMINATE |
| Vanilla PostgreSQL | PostgreSQL licence | **does not shard** | n/a | n/a | n/a | n/a | n/a | light | ELIMINATE |
| MySQL InnoDB Cluster | GPL-2.0 | **full replication** | n/a | n/a | n/a | n/a | n/a | moderate | ELIMINATE |
| Percona XtraDB Cluster | GPL-2.0 | **full replication** | n/a | n/a | n/a | n/a | n/a | moderate | ELIMINATE |
| MariaDB Galera | GPL-2.0 | **full replication** | n/a | n/a | n/a | n/a | n/a | moderate | ELIMINATE |
| DuckDB | MIT | **single process** | n/a | n/a | n/a | n/a | n/a | n/a | ELIMINATE |
| OrientDB | Apache 2.0 | `?` | `?` | `?` | `?` | `?` | `?` | `?` | ELIMINATE, dormant |

Doris, StarRocks, Accumulo, Riak, Aerospike, Neon and Hydra were dismissed on
architectural grounds without full screening: the first four place data by an
automatic balancer or hash ring with no targeted command, and the last two do not
shard a table across compute nodes at all.

### The shape of the field

Only five systems in twenty-one have a *verified synchronous* targeted placement
command: Citus, CockroachDB, ScyllaDB 6.2.x, MongoDB and HBase. Of those five,
three fall at another criterion that cannot be engineered around.

- **ScyllaDB** was the most interesting near-miss. `POST /storage_service/tablets/move`
  names a destination host *and shard*, and `storage_service::transit_tablet`
  blocks on a per-tablet predicate under the comment "Wait for transition to
  finish." It fails on criterion 7: ScyllaDB has only single-partition lightweight
  transactions, so there is no cross-shard cost for the reward to measure. It also
  fails on licence durability, since 6.2.x is the last AGPL release and everything
  from 2025.1 is source-available.
- **HBase** likewise: `HMaster.move()` genuinely blocks on a
  `TransitRegionStateProcedure`, but HBase offers single-row atomicity only. It has
  a second problem worth recording, that regions live in HDFS so `move` relocates
  the serving assignment rather than the bytes, which muddies the link between
  placement and latency that the experiment exists to measure.
- **MongoDB** passes both 4 and 7. It loses on licence, being SSPL rather than
  OSI, and on footprint: a faithful topology of three shards as three-member
  replica sets, plus config servers, plus a router, is eleven to thirteen
  processes on a 16 GB laptop against Citus's four.

## Why Citus over CockroachDB

CockroachDB remains a defensible choice and the two are close. Four things decide
it for Citus.

**1. Licence.** Citus is AGPL-3.0, which is OSI-approved, with no key, no node
cap and no telemetry obligation. CockroachDB has not been open source since
24.3.0, and the no-key allowance is explicitly single-node only, so a three-node
research cluster needs an Enterprise Free key. Cockroach Labs encourage exactly
this use, so the key is free and quick, but it carries a consequence that matters
more than the licence text: a cluster that goes seven days without sending
telemetry is **throttled to five concurrent transactions**. On a laptop that
sleeps, travels or sits offline, that would silently corrupt a training run's
reward data rather than failing loudly. It is an avoidable research hazard.

**2. Citus has no automatic rebalancer at all.** Nothing moves unless
`rebalance_table_shards()` or `citus_rebalance_start()` is called. There is
nothing to disable and nothing competing with the agent, so the MDP is clean by
construction. CockroachDB needs five cluster settings switched off, and four of
them (`kv.replicate_queue.enabled`, `kv.lease_queue.enabled`,
`kv.split_queue.enabled`, `kv.range_merge.queue.enabled`) are registered in source
but absent from the public settings documentation, so each has to be verified as
actually taking effect on the installed build. CockroachDB's own authors flag the
hazard: `Replica.ChangeReplicas` carries a guard refusing to run with the error
"must disable replicate queue to use ChangeReplicas manually", prefaced by the
comment that tests mixing manual replication with an active queue "are often
flaky". A flaky test is an annoyance; a flaky MDP is a void result.

**3. Footprint, and therefore region count.** Citus is one coordinator Postgres
plus one Postgres per region, with a 128 MB default `shared_buffers` and no JVM,
no ZooKeeper and no etcd. Six regions is seven light containers, which brings the
simulator's multi-region topology within reach on a 16 GB laptop. CockroachDB's
three nodes are cheap, but each carries a 25 percent-of-RAM `--max-sql-memory`
default that must be overridden, and scaling to six regions is meaningfully
heavier.

**4. The step function is as simple as it can be.** One SQL function call that
returns or raises. No range ids to discover, no store ids to map, no result set to
parse for per-row `ok`. The environment code that wraps it is short enough to be
obviously correct, which matters in a five-week window.

Set against those, CockroachDB's real advantage is its two-tier action structure:
`RELOCATE LEASE` is cheap and `RELOCATE VOTERS` is expensive, which gives the
reward's migration term genuine structure rather than one flat penalty. That is a
loss, and it is the subject of the next section.

## What the action space loses, and why that is acceptable

Citus supports two of the simulator's five mutators. `MOVE` and `SPLIT` survive.
`MERGE` does not exist: the UDF tree was searched and no merge function is
present. `ENSURE_REPLICA` and `DROP_REPLICA` are effectively unavailable, because
per-shard multi-replica operation depends on `citus.shard_replication_factor > 1`,
which is deprecated. `citus_copy_shard_placement` does exist and is synchronous by
the same code path, so a second placement of a named shard can be created, but no
paper claim should rest on a deprecated setting.

Three reasons this narrowing is acceptable, and one reason it is an improvement.

**It matches the project's own title.** The work is *Reinforcement Learning for
Dynamic Data Fragmentation and Allocation*. Fragmentation is `SPLIT`. Allocation
is `MOVE`. Replication is a third concern that the title does not claim, and the
research question asks how well a DQN can "continuously re-fragment and
re-allocate", which is exactly the surviving pair.

**The lost actions were already the weakest part of the design.**
[ADR-0002](ADR-0002-flat-declarative-action-space.md) records that `DROP_REPLICA`
is entirely dead at `min_replicas`, and that overall action applicability measured
54 percent. A 401-action space in which nearly half the actions are no-ops at any
given state is poor ground for DQN, which cannot mask. The Citus action space is
`S x (N-1)` moves plus `S` splits plus a no-op, all of which are meaningful, which
is a denser and better-conditioned learning problem.

**Losing merge keeps the action space stationary.** Without merge, shard count is
monotonically non-decreasing and can be capped by pre-splitting, so the action
space does not change shape mid-episode. That is the cleaner experiment, and
CockroachDB would not have given merge either: it offers only `UNSPLIT`, which
releases a shard into the merge queue rather than commanding a merge.

**The honest cost** is that with a single placement per shard there is no
read-at-nearest-replica term, so the tension between cheap local reads and
expensive write quorums disappears from the cost model. Reads and writes both go
to the one node holding the shard, and the remaining trade-offs are putting each
shard where its traffic originates and co-locating shards that transact together.
That is a narrower cost model than `shardmind.cost` currently implements, and the
paper must say so plainly rather than quietly. If the instructor considers
replica placement essential to the contribution, that is the trigger to fall back
to CockroachDB, which is why Action Item 1 comes before any code.

## Consequences

- **The training environment changes, not the research question.** The reward is
  still negative transaction latency net of migration cost, and Citus's two-phase
  commit means that quantity is real: `citus.multi_shard_commit_protocol` defaults
  to `2pc`, the coordinator issues `PREPARE TRANSACTION` to each participating
  worker and then `COMMIT PREPARED`, so under injected latency commit cost is a
  direct function of which nodes hold the touched shards.
- **`shardmind/harness/` is still the new module**, but it is smaller than
  [ADR-0007](ADR-0007-real-database-validation.md) anticipated: no zone-config
  read-modify-write merge, no 256-partition scheme, no Toxiproxy requirement.
- **Latency injection returns to `tc`/`netem`.** ADR-0007 chose Toxiproxy because
  the CockroachDB image ships no `iproute2`. The Postgres image can have
  `iproute2` installed, so netem in each container is available again. Note that
  netem shapes egress only, so half the intended round-trip goes on each side.
- **`shardmind.cost` becomes a model of the harness rather than a substitute for
  it.** Its read-at-nearest-replica and quorum terms have no counterpart under
  replication factor 1. Either the cost model is reduced to match, or it is kept
  and the divergence is documented as a limitation. This needs deciding before the
  results section is drafted.
- **The simulator is not discarded.** It stays as the fast environment for the
  volatility sweeps and ablations, which remain unaffordable against any real
  cluster at seconds per step. The relationship between the two is now the
  simulator trains and sweeps, Citus produces the headline result.
- **The eight-week schedule has no room for this.** A real-database workstream was
  scoped in ADR-0007 as a stretch goal and is now the critical path.
  `docs/roadmap.md` must be rewritten, not amended.
- **AGPL-3.0 is copyleft.** Irrelevant to an academic paper, worth one sentence to
  the instructor so it is not discovered late.

## Action Items

1. [ ] **Ask the instructor whether replica placement is in scope.** Nothing else
   starts until this is answered. The question is narrow: *does the contribution
   require the agent to control how many replicas each shard has and where they
   sit, or is it sufficient to control where each shard lives and how it is
   split?* If the former, fall back to CockroachDB and accept the licence key and
   telemetry constraints. If the latter, Citus.
2. [ ] Ask the second question in the same conversation: *may the agent be trained
   in the simulator and evaluated on the real cluster, or must training itself run
   against it?* A move that blocks on a shard copy costs seconds, so training
   entirely on the cluster is weeks of wall clock.
3. [ ] Stand up four Postgres containers with the Citus extension, one coordinator
   and three workers, and confirm three facts before building anything:
   how long `citus_move_shard_placement` takes for a shard of the intended size,
   that it raises rather than hangs when the target is unreachable, and that
   `pg_dist_placement` reflects the new placement the instant the call returns.
   Those three numbers govern every design decision after.
4. [ ] Measure the single-shard versus multi-shard transaction latency gap under
   `netem` delay, before writing any agent code. If that gap is not clearly larger
   than run-to-run noise, the reward signal does not exist and the whole approach
   fails at the first hurdle. This is the cheapest possible falsification test and
   it should be run first.
5. [ ] Decide the fate of `shardmind.cost`'s replication terms: reduce, or retain
   and document the divergence.
6. [ ] Rewrite `docs/roadmap.md` around the real-database critical path.
7. [ ] Write `docs/validation-plan.md`: topology, injected latencies, workload
   parameters, and the agreement statistic that counts as a pass. Fix the
   threshold before seeing results.

## Sources

Placement and synchrony, read from source:

- [`citus_move_shard_placement` UDF definition](https://github.com/citusdata/citus/blob/main/src/backend/distributed/sql/udfs/citus_move_shard_placement/latest.sql)
- [`shard_transfer.c`, containing `TransferShards()`](https://github.com/citusdata/citus/blob/main/src/backend/distributed/operations/shard_transfer.c)
- [`citus_split_shard_by_split_points` UDF definition](https://github.com/citusdata/citus/blob/main/src/backend/distributed/sql/udfs/citus_split_shard_by_split_points/latest.sql)
- [`replica_command.go`, containing `initializeRaftLearners`](https://github.com/cockroachdb/cockroach/blob/master/pkg/kv/kvserver/replica_command.go)
- [`ALTER RANGE`, CockroachDB docs](https://www.cockroachlabs.com/docs/stable/alter-range)

Licence positions:

- [Citus 11 goes fully open source](https://www.citusdata.com/blog/2022/06/17/citus-11-goes-fully-open-source/)
- [CockroachDB licensing FAQ](https://www.cockroachlabs.com/docs/stable/licensing-faqs)
- [ScyllaDB source-available FAQ](https://www.scylladb.com/source-available-faq/)
- [ArangoDB licence change to BUSL 1.1](https://arango.ai/blog/evolving-arangodbs-licensing-model-for-a-sustainable-future/)
- [Spanner Omni licence terms, section 3.4 on benchmark disclosure](https://cloud.google.com/terms/spanner-omni-license-terms)

Transaction and metadata behavior:

- [How Citus executes distributed transactions](https://www.citusdata.com/blog/2017/11/22/how-citus-executes-distributed-transactions/)
- [Citus metadata tables reference](https://docs.citusdata.com/en/stable/develop/api_metadata.html)
- [Citus configuration reference](https://docs.citusdata.com/en/stable/develop/api_guc.html)
- [ClickHouse transactional guarantees](https://clickhouse.com/docs/guides/developer/transactional)
- [Cassandra topology changes, on `nodetool move` and vnodes](https://cassandra.apache.org/doc/4.0/cassandra/operating/topo_changes.html)
