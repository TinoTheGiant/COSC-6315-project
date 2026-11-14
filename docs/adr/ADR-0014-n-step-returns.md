# ADR-0014: n-step returns in the masked replay buffer

**Status:** accepted, 13 November 2026.

## Context

A move's costs and benefits arrive at different times. Its migration cost is
charged in the window the move is made; its latency benefit lands over the
windows after it, as traffic meets the new placement. A one-step target,
`r + gamma * max Q(s', a')`, sees the cost directly and the benefit only through
a bootstrapped estimate, which early in training is noise. That biases the
agent against moves whose payoff is delayed, which in this problem is most
useful moves. No midterm run converged, which is consistent with weak credit
assignment, though not proof of it.

n-step returns put several windows of real reward into the target:
`r_t + gamma r_{t+1} + ... + gamma^{n-1} r_{t+n-1} + gamma^n max Q(s_{t+n}, a')`.

## Decision

**Implement n-step sampling in `MaskedReplayBuffer`**, selected by
`DQNConfig.n_steps` (default 1), the `--n-steps` flag of `scripts/train.py`, and
the `n_steps` input of `train.yml`.

For each sampled transition the buffer sums up to `n` discounted rewards,
stopping early at an episode end, and returns the observation and the
**action mask of the state at the end of that run**, with `discounts` set to
`gamma^k` for the `k` steps actually summed. `MaskedDQN.train` already reads
`discounts`, so the learning step is unchanged. A truncation (time limit) ends
the run but still bootstraps; a termination ends it and does not. A run never
reads past the newest transition, which in a full buffer is followed by the
oldest, from another episode.

**Not Stable-Baselines3's `NStepReplayBuffer`.** It is used only when no custom
buffer is set, so beside `MaskedReplayBuffer` it would be ignored with a
warning, and it does not return the mask of the n-th next state that the masked
target needs (ADR-0013). The sampling logic follows its approach, including
treating the newest transition as truncated during sampling.

**`MaskedDQN` takes `n_steps` itself** and never passes it to Stable-Baselines3,
so behaviour does not depend on the installed SB3 version. It is stored as
`n_step_returns`, survives save and load, and an archive written before this
change reads as one step.

## Consequences

**`n_steps = 1` is the previous code path exactly**, so existing models, recorded
results and default runs are unaffected. The config digest is unchanged, since
`n_steps` is a learner setting in `DQNConfig`, not an environment setting; each
run's `agent_config.json` records it.

**Bias against variance.** Larger `n` propagates delayed reward faster but adds
variance, and because DQN learns off-policy from replay, the summed rewards
come from an older, more exploratory policy than the one being evaluated. n = 3
is the usual starting point (Hessel et al., 2018); this project does not tune it
beyond that.

**Verification.** `tests/test_n_step.py` checks, on hand-built transitions with
known rewards: the discounted sum and the end-of-run observation and mask; early
stop at truncation (bootstraps) and termination (does not); never reading past
the newest transition, including across the wrap of a full buffer; that
sampling leaves stored timeouts unchanged; that `MaskedDQN` hands `n` and
`gamma` to its buffer; and that `n` survives save and load. Each of four
deliberate breaks (no write-head guard, mask taken from the start of the run,
a fixed `gamma^n` discount, `n` not passed to the buffer) makes at least one
test fail.

## References

M. Hessel et al., "Rainbow: Combining Improvements in Deep Reinforcement
Learning," in *Proc. AAAI*, 2018.

R. S. Sutton and A. G. Barto, *Reinforcement Learning: An Introduction*, 2nd ed.
MIT Press, 2018, ch. 7.
