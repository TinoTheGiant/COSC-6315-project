# ADR-0006: Cell-based fragments, and an open-loop workload

**Status:** Accepted
**Date:** 2026-09-20
**Deciders:** Tinotenda Kaseke

## Context

Two modelling choices sit underneath everything else and are easy to get wrong
in ways that quietly invalidate the result.

**Granularity.** The novelty claim rests on fragmentation being a decision
variable, not just allocation. If fragments are opaque objects with their own
access distributions, then splitting one has to invent distributions for the two
halves, and the natural thing to invent is two copies of the parent's. Under
that model splitting can never help, and the fragmentation action is noise. The
claim would be untestable by construction.

**Feedback.** In a real system, latency changes behaviour: users retry, clients
back off, traffic reroutes. A workload model can either ignore that (open loop)
or model it (closed loop).

## Decision

**Granularity.** The keyspace is divided into `n_cells` atomic cells, default
256. A fragment is a contiguous run of cells. Each cell carries its own angular
position on the geographic circle, and those positions follow a correlated
random walk along the keyspace rather than being drawn independently. A split
cuts a fragment at its midpoint cell; the halves inherit the parent's placement
and can then diverge.

**Feedback.** The workload is open loop. `WorkloadGenerator.window(t)` depends
on `t` and the seed, and on nothing the agent did.

## Options Considered

### Granularity

| Option | Split is meaningful? | Complexity | Note |
|--------|---------------------|------------|------|
| Opaque fragments | No | Lowest | fragmentation action is unfalsifiable |
| Cells with i.i.d. angles | Barely | Low | every fragment looks alike in expectation |
| Cells with correlated angles (chosen) | Yes | Low | a wide fragment spans divergent affinities |
| Per-tuple modelling | Yes | High | no gain over cells at this scale |

The random walk is what makes the difference. With i.i.d. cell angles, a
fragment's aggregate access distribution converges to the global average as it
widens, so all wide fragments look alike and splitting buys nothing
systematically. With a correlated walk, a wide fragment genuinely straddles two
populations and splitting separates them. `cell_angle_walk_sigma` controls how
much, and it is therefore the parameter that sets how much the fragmentation
action can possibly be worth. It belongs in the ablation of Objective 6.

### Feedback

| Option | Realism | Reproducibility | Complexity |
|--------|---------|-----------------|------------|
| Open loop (chosen) | Lower | Exact | Low |
| Closed loop | Higher | Harder | High |

## Trade-off Analysis

On granularity, the choice is forced: the project's central claim is not
testable under opaque fragments, so cells are not a convenience but a
requirement. The remaining question is only how correlated the cell angles
should be, and that is an empirical parameter rather than a design decision.

On feedback, the open loop is chosen for a specific reason beyond simplicity. A
closed loop makes the reward depend on the agent's own history in a way the
state does not capture, which breaks the Markov property the MDP formulation
assumes. Debugging non-convergence under a non-Markov environment, with no prior
RL experience and five weeks left, is not a risk worth taking. The honest
framing is that the agent is being asked to track an exogenous workload, which
is exactly the follow-the-sun scenario the problem statement describes.

## Consequences

- Split is free in bytes: both halves keep the parent's placement, so the split
  is a catalogue edit. Merge is not free: the right half's data must be copied
  to any region in the left half's replica set that lacked it.
- `n_cells` bounds how finely the agent can cut, independently of
  `max_fragments`. At 256 cells and a cap of 20 fragments the cap binds first,
  which is intended.
- The workload is indifferent to placement, so a pathological placement never
  makes traffic go away. Results overstate how forgiving a bad placement is.
- Because `window(t)` is pure, two runs with the same seed and the same actions
  produce identical trajectories, which is what makes the determinism guarantee
  in Objective 2 testable at all.

## Action Items

1. [x] Implement cells with a correlated angular walk.
2. [ ] Ablate `cell_angle_walk_sigma` in Objective 6, and report the value of
   the fragmentation action as a function of it. If the split action adds
   nothing even at high sigma, that is a finding and must be reported as one.
3. [ ] Name the open-loop assumption in the paper's threats to validity.
