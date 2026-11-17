# ADR-0020: Evaluate the trained agent on the cluster unchanged; defer fine-tuning

**Status:** Accepted, 16 November 2026, by Tino. Records what the CCGrid
submission does: zero-shot evaluation on the cluster, fine-tuning deferred.
**Date:** 2026-11-16
**Deciders:** Tino Kaseke (instructor informed)

## Context

The instructor approved pre-training in the simulator and fine-tuning on the
real cluster (7 October; ADR-0009). The architecture figure and Section III of
the paper were written to that plan.

What was actually run for the paper is different. Cluster evaluation 1
(Actions 43751004009, docs/results-log.md) ran one trained checkpoint, from
Train agent run 43674558770, on CockroachDB **without any further training**.
Fine-tuning was never started.

The constraint is wall clock. A cluster step took 12.9 to 15.2 s in that run,
and one 200-window episode took 3 h 19 min. ADR-0011 sized fine-tuning at about
2000 steps, roughly 8 hours of runner time per learner seed, before evaluation.
The submission deadline is 1 December 2026 and the course paper is due
30 November.

Until 16 November the paper described fine-tuning as done in two places (the
Fig. 1 node and caption, and Section III-J). An in-project review caught it.

## Decision

For the CCGrid 2027 submission, **evaluate zero-shot transfer**: run the
simulator-trained agent unchanged on the cluster, report it as such, and list
cluster fine-tuning as future work. The paper text and Fig. 1 now say this.

## Options Considered

### Option A: Zero-shot evaluation (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low; already run |
| Cost | ~3.3 h of runner time per policy episode |
| Evidence | Tests whether the simulator's policy ordering survives the move |
| Risk | Reviewers may read "pre-train and fine-tune" as promised and not delivered |

**Pros:** honest about what ran; the harness, read-back and refusal accounting
are exercised end to end; the 13% systematic offset is a finding in itself.
**Cons:** cannot show that cluster experience improves the agent.

### Option B: Short fine-tune before submission

| Dimension | Assessment |
|---|---|
| Complexity | Medium; the harness already computes the reward |
| Cost | ~8 h per learner seed for ~2000 steps, plus evaluation |
| Evidence | One fine-tuned seed, no interval |
| Risk | Under-trained result that a reviewer reads as "fine-tuning does not help" |

### Option C: Full fine-tuning study

Several learner seeds and an ablation against zero-shot. Weeks of runner time.
Out of reach before 1 December.

## Trade-off Analysis

B adds one weak data point at the cost of most of the remaining runner budget,
which the cheaper experiments (more cluster workload seeds, the agent's
simulator rerun on seed 2000) would use better. A is what the evidence
supports and states its limit.

## Consequences

- Easier: the transfer claim is narrow and checkable.
- Harder: the "pre-train, fine-tune" story from ADR-0009 is now only a plan;
  the paper must not imply otherwise.
- Revisit for the camera-ready version or a journal extension, where
  fine-tuning is the natural next experiment (paper Section V).

## Action Items

1. [x] Fig. 1 and Section III-J describe zero-shot evaluation (16 November).
2. [x] Tino accepted this ADR (16 November).
3. [x] Cluster episodes on workload seeds 2001 to 2003 (Actions 43954753671,
       43954879894, 43954980773). The agent is second to the heuristic on all
       four seeds, which the paper now reports instead of one episode.
