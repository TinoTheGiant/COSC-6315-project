# ADR-0015: One replication factor for the simulator and the cluster

**Status:** Accepted, 14 November 2026 (Option A). The RF 2 data point was withdrawn on 15 November: CockroachDB refuses it
**Date:** 2026-11-13, accepted 2026-11-14
**Deciders:** Tino Kaseke

## Context

ADR-0009 and docs/harness-architecture.md fix the replication factor at 3, and
the action-space measurements in ADR-0002 were taken at RF 3
(`scripts/measure_action_space.py` sets it explicitly). But every configuration
in `configs/`, and therefore every training run and every recorded baseline,
uses `min_replicas: 2`. The initial catalogue places two replicas per fragment
and no action changes the count, so **the simulator has always run at RF 2**.
The CockroachDB cluster runs at its default of 3. The placement read-back
(harness piece 1) found this: it reports voters per range against replicas per
fragment.

The mismatch is silent. `DQN.load` checks only that observation and action
shapes agree, and they do: the replica matrix is `(F, R)` either way. A model
trained at RF 2 would load on the cluster and then see three replicas in every
row, a state it never met in training. The cost structure differs too: with
three replicas, reads have a nearer replica and a write's quorum acknowledgement
is the faster of two followers rather than the only one.

Constraints: paper due 28 November, code freeze 21 November, eight training
runs at RF 2 already in flight, a further long-training round planned for
16 November.

## Decision

**Option A, RF 3 on both sides**, with one addition: the cluster gate is also
run at RF 2 and reported as a second data point.

Set `min_replicas` and `max_replicas` to 3 in the defaults and in every
six-region configuration (`configs/reduced-tabular.json`, a separate
three-region tabular study, keeps its own bounds). Re-run the baselines and
train the final models at RF 3. On the cluster, set the count explicitly with
`fragalloc.harness.cluster.converge_replication` before any measurement.

**Why the RF 2 data point.** With two voters, a Raft majority is both, so every
write waits for the farther replica. With three, a majority is two, so a write
waits only for the nearer follower and can route around one badly placed
replica. RF 2 therefore probably exaggerates how much placement matters, which
is the effect this paper measures. Measuring both turns that threat into a
finding: the effect at CockroachDB's default, and how much larger it is when
the database cannot route around a replica.

**New evidence at acceptance.** Cluster pilot #4 (results-log Run 4) read back
two voters on every range of the harness table. The pilot never set the count:
it froze the rebalancer seconds after start-up, likely mid up-replication.
Runs 1 to 3 used the same timing, so their replica count is unknown and most
likely 2. Before this ADR the cluster matched the simulator's RF 2 by accident;
after it, both sides are at 3 by decision.

## Options Considered

### Option A: RF 3 everywhere (retrain)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low: two config values per file |
| Cost | Baseline re-run and the planned long-training runs, all on Actions |
| Fidelity | Matches CockroachDB's default and every design document |
| Schedule | Fits: the 16 November runs simply use the new config |

**Pros:** what the docs, the ADRs and reviewers expect; no unusual database
setting to defend; action-space numbers in ADR-0002 already describe it.
**Cons:** every recorded number changes, so the paper reports only RF 3
results; tonight's RF 2 runs become a learner-side ablation, not headline
results; config digests change.

### Option B: RF 2 everywhere (reconfigure the cluster)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low: one zone-config statement on the cluster |
| Cost | None: every existing result stands |
| Fidelity | Non-default; a two-replica range survives no failure |
| Schedule | Fastest |

**Pros:** keeps every recorded result; no retraining.
**Cons:** contradicts ADR-0009 and the harness design; RF 2 is an unusual
production setting a reviewer will question; the paper must explain it.

### Option C: Leave the mismatch; let fine-tuning absorb it

| Dimension | Assessment |
|-----------|------------|
| Complexity | None |
| Cost | None now; risk later |
| Fidelity | Breaks sim-to-real parity, the premise of ADR-0009 |

**Pros:** no work.
**Cons:** the agent meets out-of-distribution states on the cluster, so poor
cluster results could not be separated from the mismatch. Not defensible.

## Trade-off Analysis

A and B both restore parity; C does not and is rejected. Between A and B the
trade is cost now against defensibility later. B is free but makes the paper
defend a non-default, fault-intolerant setting and contradict its own design
documents. A costs only machine time that is already scheduled: the
16 November long-training runs were always going to produce the headline
numbers, so moving them to RF 3 adds one baseline re-run. Tonight's RF 2 runs
still answer the learner questions they were launched for (does the NOOP fix
help, does n-step help), which carry over between replication factors.

## Consequences

- Easier: one replication factor in the paper, matching the cluster and the
  docs; the cluster needs no special configuration.
- Harder: all headline numbers must come from runs after this change; the
  midterm and 13 November results become RF 2 context, labelled as such.
- Revisit: if RF 3 training is markedly worse, that is a finding about the
  problem, not a reason to switch back.

## Action Items

1. [x] Decide: A, with an RF 2 data point (14 November).
2. [x] `min_replicas` = `max_replicas` = 3 in `config.py` and the four six-region
       configs. All 262 tests pass unchanged (they build their own catalogues).
3. [ ] Re-run the baselines at RF 3 (every training run recomputes them on
       held-out seeds 2000 to 2007).
4. [ ] Train at RF 3: four seeds, then the long runs.
5. [x] `placement_check.py` now fails on any range not at the chosen count.
6. [x] `converge_replication` sets and verifies the count before any
       measurement; `--replicas` on both cluster scripts and the pilot workflow.
7. [x] Cluster pilot at `replicas = 3`. `replicas = 2` is not possible (below).
8. [x] Correction note in results-log.md for Runs 1 to 3; paper section 4
       corrected.

## Amendment, 15 November 2026: no RF 2 data point

Cluster pilot run 43672996178 asked for two voters per range. CockroachDB
v25.3 rejected the zone configuration every time: `could not validate zone
config: at least 3 replicas are required for multi-replica configurations`.
Two replicas is not a configuration the database offers. The two-voter ranges
of pilots 1 to 4 were an under-replicated transient, caught by freezing the
balancer before up-replication finished, not a setting.

Consequences: the paper reports RF 3 only; the write-quorum argument above
stays as reasoning, not as a measurement; `converge_replication` now refuses 2
before touching the cluster. Results from pilots 1 to 4 are labelled as taken
on an under-replicated cluster.
