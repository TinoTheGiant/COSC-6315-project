# ADR-0009: Reverse to CockroachDB, because sim-to-real transfer requires cost-model parity

**Status:** Accepted.
**Date:** 2026-10-07
**Deciders:** Tinotenda Kaseke, with the course instructor
**Supersedes:** [ADR-0008](ADR-0008-database-selection.md)
**Reinstates:** the database choice in [ADR-0007](ADR-0007-real-database-validation.md), on different and better grounds

## Context

The instructor has approved **pre-training in the simulator and fine-tuning on
the real cluster**. That single fact changes the decision, and it is worth being
precise about why, because this is the second reversal.

[ADR-0008](ADR-0008-database-selection.md) screened twenty-one databases and
chose Citus. It was decided under an assumption that no longer holds: that the
simulator would be *replaced* by the cluster. Under that assumption only the
workload model had to survive, so the cost model's fidelity to the target system
did not matter, and Citus's narrow action space looked like an acceptable price
for a clean licence and a simple step function.

Under sim-to-real the simulator is not replaced, it is the first half of the
pipeline. The pre-trained network's weights only transfer if the two halves agree
on the shape of the problem:

- the **observation space** must have the same dimensionality and meaning, or the
  input layer cannot be loaded;
- the **action space** must have the same cardinality and ordering, or the output
  layer cannot be loaded;
- the **cost structure** must be qualitatively the same, or the pre-trained value
  estimates are not merely imprecise but systematically wrong, and fine-tuning
  has to unlearn before it can learn.

Cost-model parity was irrelevant on 29 September. It is decisive on 7 October.

## Decision

**Build the real environment on CockroachDB**, three regions and six nodes under
Docker, and keep the simulator as the pre-training environment with its cost
model intact.

The action space is reframed at **fixed replication factor**, which makes it map
one-to-one onto CockroachDB's three synchronous statements:

| Action | Statement | Blocking |
|---|---|---|
| `MOVE_LEASE(f, r)` | `ALTER RANGE <id> RELOCATE LEASE TO <store>` | yes, one lease transfer |
| `MOVE_REPLICA(f, from, to)` | `ALTER RANGE <id> RELOCATE VOTERS FROM <s> TO <s>` | yes, through snapshot apply |
| `SPLIT(f)` | `ALTER TABLE ... SPLIT AT VALUES (k)` | yes, sub-second |

**Amendment, 8 October, from Cluster pilot #1.** `RELOCATE LEASE` is valid only
to a store that **already holds a voting replica** of that range. At replication
factor 3 across six regions, that is three of the six, so `MOVE_LEASE(f, r)` is
undefined for half the regions at any moment. The pilot found this by asking for
leaseholders on six regions and getting two
([results-log.md](../results-log.md), run 1).

[ADR-0002](ADR-0002-flat-declarative-action-space.md) requires every action to be
defined in every state, since DQN cannot mask, so the resolution is to keep
`MOVE_LEASE(f, r)` declarative: it means *ensure the lease for `f` is in region
`r`*, moving a replica there first when one is not already present. That is one
or two statements rather than one, and the migration cost term must charge for
the replica move when it happens. Settle this alongside Action Item 2.

The same run measured why this matters: with leases co-located but replicas
spread, the median transaction still cost 207 ms, because **writes pay a quorum
round trip regardless of where the lease sits**. Moving leases alone does not
localize writes.

`NOOP` completes the space. `MERGE` is dropped: CockroachDB offers only
`UNSPLIT`, which releases a range into the merge queue rather than commanding a
merge, and [ADR-0008](ADR-0008-database-selection.md) already established that no
candidate in the field gives a synchronous merge worth building on.

## Options Considered

### Option A: Citus, as ADR-0008 decided

| Dimension | Assessment |
|-----------|------------|
| Complexity | **Low.** One blocking SQL function; no rebalancer to disable |
| Licence | **Best in field.** AGPL-3.0, OSI, no key, no telemetry |
| Footprint | **Best in field.** Four light Postgres containers, no JVM |
| Action parity with the simulator | **2 of 5 kinds** |
| Observation parity | **Fails.** One placement per shard, so the replica-set portion of the 703-dim observation has no counterpart |
| Cost-model parity | **Fails.** Replication factor 1 deletes two of the five cost terms |
| Existing results | **Invalidated.** Every measured figure would need re-deriving |

**Pros:** everything about the engineering is easier, and the licence story is
the cleanest available.
**Cons:** at replication factor 1 there is exactly one copy of each shard, so
`cost.read_serving_region` and `cost.replication_term` describe nothing the
cluster does. Reads and writes both go to the single holder. That is not a
simplification of the cost model, it is the removal of half of it, including the
read-locality-versus-write-quorum tension that is the reason placement is
interesting in the first place.

### Option B: CockroachDB at fixed replication factor

| Dimension | Assessment |
|-----------|------------|
| Complexity | **Medium.** Range ids and store ids to resolve; five settings to disable, four of them undocumented |
| Licence | **Weakest of the two.** Source-available; three nodes need a free Enterprise key with a telemetry obligation |
| Footprint | **Good.** One binary per node; six nodes is heavier than four Postgres but tractable |
| Action parity | **3 of 5 kinds directly, plus one new kind the simulator gains cheaply** |
| Observation parity | **Holds.** Replica sets exist, so the observation encoder is unchanged |
| Cost-model parity | **Holds.** All five cost terms have counterparts |
| Existing results | **Preserved**, subject to the action-space adjustment below |

**Pros:** every term in `shardmind.cost` corresponds to something the cluster
actually does. Reads really are served from the nearest replica, writes really do
pay a quorum, and cross-range transactions really do pay two-phase commit when
their leaseholders span regions. That is the whole argument of
[ADR-0004](ADR-0004-analytic-cost-model.md) and it is what makes pre-training
worth anything.
**Cons:** the licence, the key, the telemetry throttle, and the five settings.
All are one-off costs paid in the pilot, none recurs during training.

### Option C: keep Citus and reduce the simulator to match

Considered and rejected on schedule. It means rewriting `actions.py`,
`catalog.py`, `observation.py` and `cost.py`, re-deriving every measured result,
and rewriting a large share of the 115 tests. Against 30 days remaining, and
against a pre-training approval whose entire value is that the simulator's work
carries forward, it spends the approval to no purpose.

## Trade-off Analysis

The honest framing is that **Citus wins on engineering and CockroachDB wins on
scientific validity**, and pre-training moved validity from a secondary concern
to the governing one.

The reversal is not a change of mind about the facts. Everything
[ADR-0008](ADR-0008-database-selection.md) established still holds:
`citus_move_shard_placement` really does block, Citus really has no competing
rebalancer, CockroachDB really is source-available, and the telemetry throttle
really is a hazard. What changed is the weight on one criterion that was not in
the original eight. The screening test asked "can this database execute the
agent's action?" It should also have asked "can this database execute the cost
model the agent was pre-trained on?" Citus passes the first and fails the second.

The licence objection survives and should be stated plainly in the paper rather
than glossed: CockroachDB has not been open source since 24.3.0, the project uses
an Enterprise Free key obtained under Cockroach Labs' stated encouragement of
non-commercial academic research, and the experiment is reproducible by anyone
who obtains the same free key. That is a limitation, not a flaw in the method.

One consequence is strictly positive. At fixed replication factor the action
applicability problem recorded in [ADR-0002](ADR-0002-flat-declarative-action-space.md)
largely dissolves. `DROP_REPLICA` was entirely dead at `min_replicas` and overall
applicability measured 54 percent, which is poor ground for a DQN that cannot
mask. `MOVE_REPLICA` at constant count is never dead: a fragment always has
replicas to move and regions to move them to.

## Consequences

- **The simulator keeps its cost model, its observation encoder and its measured
  results.** `cost.read_serving_region` and `cost.replication_term` stay.
- **`catalog.py` gains one mutator and loses two.** `move_replica(f, from, to)`
  replaces the `ensure_replica` plus `drop_replica` pair for the agent's purposes.
  Both existing mutators stay in the module, because `move_replica` is composed
  from them and the tests for them are still worth having.
- **The action space shrinks and its shape changes.** From
  **Settled 19 October**, see the amendment to
  [ADR-0002](ADR-0002-flat-declarative-action-space.md): destination-only, 261
  actions, 29.2% applicable, fully reachable. The prediction below was right that
  the naive form is worse. From
  `3 x 20 x 6 + 2 x 20 + 1 = 401` to `MOVE_LEASE(20 x 6) + MOVE_REPLICA(20 x 6 x 6)
  + SPLIT(20) + NOOP`. The naive `MOVE_REPLICA` encoding is 720 actions, which is
  worse, not better. **Action Item 2 owns this**: the likely answer is a
  destination-only encoding, `MOVE_REPLICA_TO(f, r)`, with the source chosen as
  the replica whose region is farthest from `r`, giving `20 x 6 x 2 + 20 + 1 = 261`.
  That bakes a tie-break into the action, which must be documented as part of the
  action semantics rather than hidden.
- **Replication factor becomes a fixed experimental parameter, not an agent
  decision.** Set it to 3. `min_replicas` and `max_replicas` collapse to one
  value, and the durability trade-off leaves the paper's scope. Say so in the
  limitations.
- **The pilot is now the critical path**, and it has two jobs rather than one:
  confirm the three statements block as documented, and confirm the five balancer
  settings actually take effect on the installed build.
- **Latency injection returns to Toxiproxy**, as [ADR-0007](ADR-0007-real-database-validation.md)
  specified, because the CockroachDB image ships no `iproute2`.
- **Three regions, six nodes, two per region.** At one node per region a replica
  move has nowhere to go within a region, which entangles every move with a
  cross-region change.
- **`docs/roadmap.md` is rewritten** around the remaining 30 days.
  [ADR-0008](ADR-0008-database-selection.md)'s Action Item 1, whether replica
  placement is in scope, dissolves: CockroachDB supports it either way, so the
  question no longer blocks anything.

## Action Items

1. [ ] **Obtain the Enterprise Free licence key before anything else.** It is
   free, Cockroach Labs encourage academic use, and a cluster running without one
   is throttled to five concurrent transactions after seven days. Add an
   assertion to the harness that fails loudly if observed transaction concurrency
   collapses, so a throttle can never be mistaken for a result.
2. [ ] **Fix the `MOVE_REPLICA` encoding** and record it in an amendment to
   [ADR-0002](ADR-0002-flat-declarative-action-space.md). Destination-only with a
   documented source tie-break is the working proposal; measure applicability
   under it before committing.
3. [ ] **Run the pilot.** Six nodes, three regions, Toxiproxy. Three
   measurements: how long each of the three statements takes at the intended
   shard size, that each raises rather than hangs when its target is unreachable,
   and that `SHOW RANGES ... WITH DETAILS` reflects the new placement the instant
   the statement returns.
4. [ ] **Verify the five balancer settings take effect**, individually, on the
   installed build: `kv.allocator.load_based_rebalancing`,
   `kv.replicate_queue.enabled`, `kv.lease_queue.enabled`, `kv.split_queue.enabled`,
   `kv.range_merge.queue.enabled`. Four are in source but absent from the public
   settings documentation. Assert observed placement after every action regardless.
5. [ ] **Run the falsification test before writing any agent code.** Measure the
   single-region against cross-region transaction latency gap under injected
   delay. If it is not clearly larger than run-to-run noise, the reward signal
   does not exist, and that must be discovered in the pilot rather than in week 7.
6. [ ] Set replication factor to 3 in the simulator config and re-run the three
   headline measurements to confirm they survive at fixed RF.

## Sources

- [`replica_command.go`, containing `initializeRaftLearners`](https://github.com/cockroachdb/cockroach/blob/master/pkg/kv/kvserver/replica_command.go)
- [`ALTER RANGE`, CockroachDB docs](https://www.cockroachlabs.com/docs/stable/alter-range)
- [`SHOW RANGES`, CockroachDB docs](https://www.cockroachlabs.com/docs/stable/show-ranges)
- [CockroachDB licensing FAQ, on Enterprise Free and the telemetry throttle](https://www.cockroachlabs.com/docs/stable/licensing-faqs)
- [Parallel Commits](https://www.cockroachlabs.com/blog/parallel-commits/)
- [ADR-0008](ADR-0008-database-selection.md), for the twenty-one-system screen that still stands
