# ADR-0015: One replication factor for the simulator and the cluster

**Status:** Proposed
**Date:** 2026-11-13
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

Proposed: **Option A, RF 3 on both sides.** Set `min_replicas` and
`max_replicas` to 3 in every configuration, re-run the baselines, and train the
final models at RF 3.

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

1. [ ] Decide A or B.
2. [ ] (A) Set `min_replicas` and `max_replicas` to 3 in `config.py` defaults and
       every file in `configs/`; update the tests that assume 2.
3. [ ] (A) Re-run the baselines at volatility 4.0 on held-out seeds 2000 to 2007.
4. [ ] (A) Launch the 16 November long-training runs at RF 3.
5. [ ] Make `scripts/placement_check.py` fail, not warn, on an RF mismatch once
       the decision is applied.
