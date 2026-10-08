# ADR-0003: Use Stable-Baselines3 rather than implement DQN

**Status:** Accepted
**Date:** 2026-09-20
**Deciders:** Tinotenda Kaseke

## Context

This is a solo project, on an eight-week clock, by an author with no prior
reinforcement learning implementation experience. Phases 4 and 5 allocate two
weeks to getting a DQN to converge on a non-stationary environment with a
401-action space and a delayed reward.

DQN has a well-known set of implementation details that decide whether it works
at all: target-network update cadence, replay buffer warm-up, epsilon annealing
schedule, gradient clipping, Huber loss, and the exact handling of `truncated`
against `terminated` at the episode boundary. Getting any of them wrong produces
the same symptom, a flat or diverging learning curve, which is indistinguishable
from a broken reward function.

## Decision

Use `stable_baselines3.DQN` with a CPU PyTorch build. Write no DQN code.

## Options Considered

### Option A: Hand-rolled DQN

| Dimension | Assessment |
|-----------|------------|
| Complexity | High |
| Time cost | 1-2 weeks including debugging |
| Learning value | High |
| Failure diagnosis | Ambiguous: agent or environment? |

**Pros:** complete control; genuine understanding of every detail; ablations
like Double and Duelling become trivial edits.
**Cons:** when it does not converge, there are two suspects and no way to
separate them. On this schedule that is the project's single largest risk.

### Option B: Stable-Baselines3 (chosen)

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Time cost | Hours |
| Learning value | Moderate; the details are readable, just not written here |
| Failure diagnosis | Unambiguous: a trusted agent means the fault is the environment |

**Pros:** removes one of the two suspects; `DQN(policy="MlpPolicy")` with
Double DQN available as a flag and Duelling via `policy_kwargs`, which makes
Objective 6's ablations cheap; TensorBoard integration is built in.
**Cons:** a dependency on a library whose defaults must still be understood;
some architectural freedom given up.

### Option C: CleanRL single-file DQN

| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium |
| Time cost | Days |
| Learning value | High: the file is meant to be read |
| Failure diagnosis | Reasonably clear if the file is used unmodified |

**Pros:** a middle path; every detail visible in one file.
**Cons:** no maintained ablation flags, so Double and Duelling become edits that
reintroduce the diagnosis ambiguity exactly where Objective 6 needs clarity.

## Trade-off Analysis

The argument is about where uncertainty is allowed to sit. The scientific claim
of this project is about the environment and the reward: that a learned policy
over a joint fragmentation and allocation action space beats heuristics under
migrating workloads. Nothing in the claim depends on the DQN implementation
being the author's.

So implementation uncertainty in the agent buys nothing and costs the ability to
interpret a failure. The week 3 tabular Q-learning check exists for the same
reason from the other side: it validates the reward function using an algorithm
simple enough to be beyond suspicion, so that by week 4 both suspects have been
eliminated in turn.

## Consequences

- The environment must satisfy the Gymnasium API precisely, including reporting
  `truncated` separately from `terminated`, because SB3 bootstraps the value at
  a truncation boundary and zeroes it at a termination. Getting this wrong is a
  silent, subtle bug. `test_env.py` asserts the distinction.
- Observations must be a `Box` of `float32` and normalized, since `MlpPolicy`
  applies no input normalization by default.
- Double and Duelling ablations become configuration, not code.
- Sutton and Barto [7] chapters 1 to 6 still have to be read, in parallel with
  building. The decision removes implementation risk, not the need to understand
  what is being run.

## Action Items

1. [x] Make the environment pass `gymnasium.utils.env_checker.check_env`.
2. [ ] Pin the SB3 and PyTorch versions in `requirements.txt` once Phase 3
   starts, so results reproduce.
3. [ ] Record the full hyperparameter set alongside every run in `results/`.
