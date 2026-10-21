# ADR-0005: Keep the simulator independent of Gymnasium

**Status:** Accepted
**Date:** 2026-09-20
**Deciders:** Tinotenda Kaseke

## Context

The natural way to build an RL environment is to write a `gym.Env` subclass and
put the model inside `step()`. It is one class, one file, and every tutorial
does it.

But four of the six research objectives do not involve an agent. Objective 3
characterizes four heuristic baselines. Objective 2 requires a validation
harness that compares the model's placement ranking against a real cluster.
Objective 5 sweeps reward weights, which is a property of the scalarization, not
of the model. If the model lives inside `step()`, all of that has to go through
`reset`, `step`, an observation vector and a scalar reward, none of which a
baseline or a ranking comparison wants.

## Decision

Two layers:

- `fragalloc.simulator.ClusterSimulator` owns the topology, the workload, the
  catalogue and the clock. It imports NumPy and nothing else. It knows nothing
  about observations, rewards or episodes-as-RL-objects.
- `fragalloc.env.FragAllocEnv` is a thin Gymnasium adapter holding exactly three
  translations: state to observation vector, integer to action, cost vector to
  scalar reward.

## Options Considered

### Option A: Single `gym.Env` class

| Dimension | Assessment |
|-----------|------------|
| Complexity | Lowest at first |
| Testability | Poor: every test imports Gymnasium and speaks in observations |
| Baseline support | Awkward: heuristics must be expressed as policies over vectors |
| Reward sweeps | Requires re-instantiating the whole environment |

**Pros:** fewer files, matches every tutorial.
**Cons:** the cost model's unit tests would have to assert on a 703-element
float32 vector rather than on `mean_latency_ms`, which makes a failing test
nearly unreadable.

### Option B: Simulator plus adapter (chosen)

| Dimension | Assessment |
|-----------|------------|
| Complexity | One extra module |
| Testability | Good: cost-model tests assert on named quantities |
| Baseline support | Direct: a baseline reads the catalogue and the window |
| Reward sweeps | Free: the scalarization lives in one method |

**Pros:** the baselines in Objective 3 work against the same model the agent
does, with no RL vocabulary in between; `CostBreakdown` is a named record, so a
test failure says `mean_txn_latency_ms` rather than `obs[698]`; the
Objective 5 weight sweep touches one function.
**Cons:** two files where one would do, and a small amount of plumbing.

## Trade-off Analysis

The decisive point is what a failing test should say. When the cost model breaks
in week 5, the difference between

    assert result.mean_txn_latency_ms == approx(3.0)

and

    assert obs[698] == approx(0.0042)

is the difference between a ten-minute fix and an afternoon. The second form
also silently couples every cost-model test to the observation layout, so
changing the encoding breaks tests that have nothing to do with encoding.

The secondary benefit is that the validation harness (ADR-0001) can call
`fragalloc.cost.evaluate` directly on a handful of candidate placements without
constructing an environment, an agent or an episode.

## Consequences

- `fragalloc.cost`, `fragalloc.catalog`, `fragalloc.workload` and
  `fragalloc.topology` are importable without Gymnasium installed. Only
  `fragalloc.env` needs it.
- The observation encoding is a separate, separately testable object with a
  published layout (`ObservationEncoder.layout`), which makes feature ablations
  a matter of slicing rather than of rewriting the environment.
- One more indirection for a reader following an action through the code.

## Action Items

1. [x] Keep Gymnasium out of every module but `env.py`.
2. [ ] Build the Phase 2 baselines against `ClusterSimulator`, not `FragAllocEnv`.
