# ADR-0013: mask inapplicable actions in selection, exploration and the bootstrap target

**Status:** accepted, 10 November 2026; **amended 13 November 2026** (NOOP is
no longer charged, see the amendment at the end). Supersedes the "no masking" clause of
[ADR-0002](ADR-0002-flat-declarative-action-space.md); the flat, declarative
261-action space itself stands unchanged.

## Context

ADR-0002 chose a flat action space partly because plain DQN offers no masking
mechanism. Inapplicable actions resolved to a no-op charged a small fixed
`inapplicable_action_cost` (0.02), on the expectation that the agent would learn
to avoid them.

It did not. At the midterm, 79.9 to 89.8% of the agent's chosen actions were
inapplicable, against 80.4% for a uniformly random policy. The fixed cost was
not teaching avoidance fast enough, so most decisions and most stored
transitions were wasted. Measured over 1,000 states of random play at the
default configuration, only 22.7% of the 261 actions are applicable on average.
This was the largest measured inefficiency in the project.

## Decision

**Subclass Stable-Baselines3's DQN as `MaskedDQN`** (`src/fragalloc/agent/masked_dqn.py`)
and apply the mask everywhere the Q-function's argmax or max is used:

1. **Greedy choice.** Q-values of inapplicable actions are set to minus infinity
   before the argmax.
2. **Exploration.** The epsilon branch, and the warm-up before
   `learning_starts`, sample uniformly from applicable actions only.
3. **The bootstrap target.** `max_a' Q_target(s', a')` runs over the actions
   applicable in `s'` only.

The third matters as much as the first two. A masked agent never takes an
inapplicable action, so those Q-values are never corrected and drift with the
shared network; left inside the target max, they leak upward bias into every
update. Huang and Ontanon (2022) discuss the selection-only case.

**Where the mask comes from.** `ActionSpace.applicable_mask` restates the
catalogue's refusal rules as array operations. `FragAllocEnv.action_masks()`
exposes it, `FragAllocEnv.step` reports the next state's mask in
`info["action_mask"]`, and `MaskedReplayBuffer` stores it beside the next
observation so the target can use it.

**The observation is unchanged.** The mask travels through `info` and the
replay buffer, not the observation vector, so the network's input size and the
simulator-to-cluster parity constraint are untouched. The cluster harness reads
the same catalogue and can compute the identical mask.

**Evaluation is tied to training.** Every `MaskedDQN` archive records
`trained_with_mask`; plain DQN archives read `False`. `resolve_eval_mode` turns
`"auto"` into `"mask"` or `"none"` from that record and refuses a mismatch.
`"collapse"` evaluates an unmasked model with its inapplicable picks relabelled
as NOOP, giving the identical trajectory with legal actions only, which a real
cluster needs.

## Options considered

**Keep the fixed cost and raise it.** Rejected. A larger penalty distorts the
reward the paper reports, and the measured rate was already indistinguishable
from random at the current value.

**Append the mask to the observation and mask inside the Q-network.** Rejected.
It grows the observation from 703 to 964 floats, which breaks every earlier
checkpoint and complicates parity with the cluster for no benefit over storing
the mask in the buffer.

**Mask selection only.** Rejected after review: it leaves the target max
contaminated by untrained Q-values, as described above.

## Consequences

**A masked model and an unmasked model are not interchangeable.** Getting the
evaluation mode wrong is silent in both directions. A masked model evaluated
without the mask chose an inapplicable action 100% of the time and scored
exactly as static hashing; an unmasked model evaluated with the mask moved
520.7 GB instead of 3.4 GB. `resolve_eval_mode` exists to make that mistake
impossible, and `tests/test_eval_mode.py` fails under each of four deliberate
breaks.

**Earlier checkpoints still load.** Plain DQN archives load with the masked
buffer and evaluate in `"none"` mode by default, so every recorded midterm
number reproduces.

**`inapplicable_action_cost` is kept, not retired.** It no longer shapes a
masked agent, which never takes an inapplicable action, but it still governs
unmasked runs. Since the amendment below it applies to inapplicable non-NOOP
actions only.

**Masking does not guarantee a better policy.** It removes wasted decisions; it
does not make the remaining ones good. Whether it improves the objective is a
hypothesis for the masked seed sweep (volatility 4.0, `w` = 0.30, learner seeds
0 to 3, 1,000,000 steps) to test against midterm runs 3 and 7, scored with
`scripts/score_objective.py` at the same `w`. Those midterm runs may have
trained for fewer steps, so part of any difference could come from training
length rather than masking.

**Verification.** `tests/test_action_mask.py` checks the mask against trial
application in every visited state and in a full catalogue, that no training
step takes a masked action, and that the target respects the mask. Each of
three deliberate breaks (unmasked target, `train` bypassing the mask, mask
stored one slot late) makes at least one test fail.

## Amendment, 13 November 2026: NOOP is never charged

**Finding.** The masked seed sweep (volatility 4.0, `w` = 0.30, learner seeds 0
to 3, 1,000,000 steps, commit `ca553eb`) reached 0.0% inapplicable actions on
every seed, but the policy chose NOOP in only 0.1 to 1.9% of windows and moved
384 to 488 GB per episode against 45 to 63 GB for the unmasked midterm runs, for
a mean latency of 144.96 ms against 142.26 ms. `FragAllocEnv._reward` charged
`inapplicable_action_cost` whenever an action left the placement unchanged, and
NOOP always does, so NOOP paid 0.02 every window. Unmasked, NOOP and the many
inapplicable actions cost the same and the charge was neutral between them.
Masked, those inapplicable actions are unreachable and NOOP is the only way to
do nothing, so the charge became a standing tax on restraint.

**Decision.** `_reward` receives the action index and charges
`inapplicable_action_cost` only when a non-NOOP action fails to apply. NOOP is
detected by index (`ActionSpace.noop_index`), not by the mutation's reason
string. Tested in `tests/test_env.py`: an inapplicable non-NOOP action still
pays the cost, NOOP pays nothing, and a NOOP chosen through `MaskedDQN.predict`
with a mask pays nothing.

**Consequences.**

* The reward changed but no configuration field did, so the config digest
  (`60276db3` at the default) is unchanged. Runs before and after this change
  are distinguished by commit, which every run directory records.
* Evaluation numbers (latency, bytes moved, action shares) do not use the
  reward, so every recorded result still reproduces. Retraining an unmasked
  model would now differ, since an explicit NOOP is cheaper than an
  inapplicable action.
* `"collapse"` mode still gives an unmasked model's exact trajectory, but no
  longer its exact reward: its relabelled NOOPs are now free.
* This removes one bias. It is not expected to fix latency on its own, since the
  latency term dominates the reward; the rerun of the same four seeds tests
  whether it restores restraint.

## References

S. Huang and S. Ontanon, "A Closer Look at Invalid Action Masking in Policy
Gradient Algorithms," in *Proc. FLAIRS-35*, 2022.
