# ADR-0002: A flat, declarative action space with no masking

**Status:** Accepted, **amended 19 October 2026**. The principle below stands:
flat, declarative, no masking. The *contents* changed. The space is now **261
actions over three kinds**, not 401 over five, and the applicability figure in
the table below (54%) was measured at variable replication factor and no longer
applies. See the amendment at the end before taking any number here as current.
**Date:** 2026-09-20
**Deciders:** Tinotenda Kaseke

## Context

The agent controls two things at once: how finely the data is fragmented, and
where each fragment's primary and replicas sit. The joint control of both is the
project's novelty claim, so neither can be dropped.

DQN estimates `Q(s, a)` for every `a` in a fixed discrete set. It offers no
mechanism for masking actions that do not apply in the current state, and
nothing in the standard formulation [6] provides one. Whatever the action space
is, every index in it must mean something in every state.

The obvious encodings each fail in a specific way. A factored space (pick a
fragment, then an operation, then a target) needs an architecture DQN does not
have. An imperative space ("migrate fragment 7 from region 1 to region 3")
leaves most indices meaningless in most states, since fragment 7 is usually not
in region 1. A full replica-set specification is `2^R` actions per fragment,
which is 64 per fragment at six regions and 1280 in total, and most of them are
nonsense.

## Decision

A single flat `Discrete(n)` space in which every action names a **desired end
state** rather than an operation:

```
SET_PRIMARY(f, r)      make region r the primary of fragment f
ENSURE_REPLICA(f, r)   guarantee a replica of f in r
DROP_REPLICA(f, r)     guarantee no replica of f in r
SPLIT(f)               cut f in half at its midpoint
MERGE(f)               absorb f+1 into f
NOOP                   change nothing
```

At the default configuration, 20 fragments and 6 regions, this is
`3 x 20 x 6 + 2 x 20 + 1 = 401` actions. An action that cannot take effect
resolves to a no-op charged a small fixed cost (`inapplicable_action_cost`,
default 0.02), not a large penalty.

## Options Considered

### Option A: Imperative operations

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low to state |
| Applicable fraction | Low; depends on current placement |
| Masking required | Yes |
| DQN compatible | No |

**Pros:** maps directly onto what a real system executes.
**Cons:** the set of valid indices changes every step, so the value function
must learn a shifting validity map before it can learn anything about latency.

### Option B: Declarative end states, flat (chosen)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Size | 401 at the default configuration (**now 261**, see the amendment) |
| Applicable fraction | ~54% at variable RF (**22.1% once RF is fixed**, see the amendment) |
| Masking required | No |
| DQN compatible | Yes |

**Pros:** every index is defined in every state; the semantics are idempotent,
so repeating an action is harmless; the space is small enough for one output
layer.
**Cons:** the agent can waste a step asserting something already true, and the
measured applicable fraction is lower than the proposal's "near zero
inapplicable" claim.

### Option C: Full replica-set specification per fragment

| Dimension | Assessment |
|-----------|------------|
| Size | `F * 2^R` = 1280 at six regions, growing exponentially in R |
| Applicable fraction | High |
| Scalability | Poor |

**Pros:** maximally expressive in one step.
**Cons:** does not survive an increase in region count, which Objective 3's
region sweep requires.

## Trade-off Analysis

Option B was chosen on DQN compatibility, but the applicability claim deserves
correcting. Measured on a freshly built catalogue (`test_actions.py`), of the
actions addressing a fragment that exists:

| Kind | Applicable | Why the rest are not |
|------|-----------|----------------------|
| `SET_PRIMARY` | 5 of 6 per fragment | the incumbent is already primary |
| `ENSURE_REPLICA` | 4 of 6 per fragment | two regions already hold replicas |
| `DROP_REPLICA` | 0 of 6 per fragment | the catalogue sits exactly at `min_replicas` |
| `SPLIT` | all | |
| `MERGE` | all but the last | no right neighbour |

That is about 54%, not "near zero inapplicable". The shortfall is concentrated
in `DROP_REPLICA`, which is dead until the agent has over-replicated something,
and in the fragment slots between the current count and the cap, which are dead
until the agent splits. Both become live as the agent acts, so applicability
rises over an episode rather than falling. The proposal's claim should be
restated in the paper as *every action is defined in every state*, which is the
property DQN actually needs, rather than as a statement about how many of them
change anything.

## Consequences

- No masking machinery, so vanilla DQN from Stable-Baselines3 works unmodified.
- The fraction of steps whose action changed nothing is a first-class training
  diagnostic. It is reported per step as `info["action_applied"]`.
- Action-space size grows as `3FR`, so the region sweep in Objective 3 is
  bounded by the output layer, not by the environment. Ten regions and twenty
  fragments is 641 actions, still comfortable.
- One action per decision window caps how fast the agent can reorganize. A
  wholesale reshuffle takes many windows, which is a rate limit on thrashing
  and a bias toward incremental adjustment. Whether that bias helps or hurts is
  an empirical question worth an ablation.

## Action Items

1. [x] Implement and prove the no-raise property by exhaustive fuzz test.
2. [ ] Log the applied-action fraction to TensorBoard during Phase 3 training.
3. [ ] Restate the applicability claim in the paper's method section using the
   measured table above.

## Amendment, 19 October 2026: the space is 261 actions, not 401

[ADR-0009](ADR-0009-cockroachdb-for-sim-to-real-parity.md) fixes the replication
factor and requires each action to map onto a CockroachDB statement. Three of the
five original kinds do not survive that, and the measurement below chose the
replacement rather than argument.

### What the old space costs at fixed RF

Measured over 1,200 states across five seeds, RF 3, six regions, cap 20
fragments, applying every index to a copy of the catalogue and asking whether it
changed anything:

| Kind | Applicable |
|---|---|
| `SET_PRIMARY` | 56.1% |
| `ENSURE_REPLICA` | **0.0%** |
| `DROP_REPLICA` | **0.0%** |
| `SPLIT` | 45.0% |
| `MERGE` | 62.3% |

**240 of the 401 actions are dead in every state.** `ENSURE_REPLICA` and
`DROP_REPLICA` change the replication factor, which is now fixed. That is much
worse than the 54% applicability this ADR originally recorded, because that
figure was measured at variable RF 2 to 4. `MERGE` is live but unmappable:
CockroachDB offers only `UNSPLIT` into a background queue ([ADR-0008](ADR-0008-database-selection.md)).

### The three candidates

| Encoding | Size | Applicable |
|---|---|---|
| A, the five kinds above | 401 | 22.1% |
| B, naive `MOVE_REPLICA(f, from, to)` | 861 | 22.9% |
| **C, destination-only** | **261** | **29.2%** |

C is a third the size of B and denser than either. Naming both ends of a replica
move costs `F x R x R` actions, 720 at the default shape, of which only 16.8%
apply, because a move needs a replica at the source and none at the destination.

### The tie-break, and why it costs nothing

`MOVE_REPLICA_TO(f, r)` names only a destination. The evicted replica is **the
non-primary replica whose region is farthest from `r` by RTT**. That is part of
the action's meaning and the paper must state it.

Breadth-first search over the replica-set state space, 60 states of
`(replica set, primary)` for six regions at RF 3, confirms the tie-break costs no
expressiveness: **0 unreachable pairs of 3,600**, with a worst-case path of 5
actions against 3 when both ends are named. Two extra steps in the worst case,
against an output layer a third the size and twice as dense, is a trade worth
taking inside a 200-window episode.

### Why `MOVE_LEASE` is restricted, at a cost

A lease moves only to a region that already holds a replica, because that is what
`ALTER RANGE ... RELOCATE LEASE` enforces, as Cluster pilot #1 found by asking
for leaseholders in six regions and getting two ([results-log.md](../results-log.md)).

Allowing a lease move to acquire a replica would raise applicability from 29.2%
to 44.7%. It is declined, because it fuses the cheap tier with the expensive one,
and the two-tier cost structure is the specific property
[ADR-0009](ADR-0009-cockroachdb-for-sim-to-real-parity.md) chose CockroachDB over
Citus to obtain. Density bought by corrupting the reward is not a gain.

The restriction has a clean consequence: **the two placement blocks partition.**
For any `(fragment, region)` at most one of them is live, and the only dead case
is the region that is already primary. A test pins it.

### Consequence for the baselines, which is not cosmetic

`GreedyPrimaryPolicy` used `SET_PRIMARY`, which acquired a replica as a side
effect. It now needs two windows: `MOVE_REPLICA_TO`, then `MOVE_LEASE`. Measured
over 200 windows at volatility 1.0, seed 0:

| Policy | Before | After |
|---|---|---|
| no-op (static hash) | 156.93 ms, 0 GB | 156.93 ms, 0 GB |
| greedy primary | 94.19 ms, 451 GB | **110.54 ms, 760 GB** |
| improvement over static | 40% | **29.6%** |

The static control is unchanged, as it must be. The greedy policy is worse
because a relocation now takes two windows, so it tracks drifting traffic a
window behind, and it performs 76 replica acquisitions per episode against 45.

**This is the honest comparison, not a regression.** The baseline previously used
a compound action no single cluster statement can perform. A baseline and an
agent must share an action space or the contest is rigged. It also widens the
headroom: a policy that anticipates drift and pre-places replicas has more to
win against 110.54 than it had against 94.19.

### Residual

`MERGE` is gone, so shard count is monotone within an episode. The random policy
consequently splits to the cap, reaching 20 fragments where it previously
settled near 4. Report the cap as a parameter rather than a result.
