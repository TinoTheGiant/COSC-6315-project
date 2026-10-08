# ADR-0002: A flat, declarative action space with no masking

**Status:** Accepted
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
| Size | 401 at the default configuration |
| Applicable fraction | ~54% of actions addressing an existing fragment, initially; see below |
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
