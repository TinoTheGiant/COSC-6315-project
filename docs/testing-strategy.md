# Testing strategy

**Date:** 2026-09-20
**Current state:** 115 tests, under one second, all passing.

## What this suite is defending against

Not crashes. A simulator that crashes is a good day. The failure this suite
exists to prevent is the one where the code runs, the agent trains, the curve
goes down, and the number at the end is wrong because the cost model had an
indexing bug in week 2 that nobody noticed until the paper was written.

Reinforcement learning makes that failure unusually likely, for two reasons.
First, a learned policy will exploit any bug that lets it lower the reward, so a
broken cost model produces a *better looking* result, not a worse one. Second, a
non-converging run has several plausible causes, and without a trusted
environment there is no way to rule any of them out.

So the priorities are, in order: the cost model is arithmetically correct; the
catalogue's invariants hold under every reachable action sequence; a seed
reproduces exactly; and the reward points somewhere.

## Shape of the suite

This is not a web service, so the usual pyramid does not transfer cleanly. The
useful axis is not unit against integration but **exact against property**.

| Layer | What it checks | Count | Example |
|-------|----------------|-------|---------|
| Exact | Closed-form arithmetic against hand calculation | ~30 | a fully co-located cluster costs exactly the intra-region RTT |
| Property | Orderings and invariants that must hold whatever the numbers | ~45 | `primary_only` reads are never faster than nearest-replica |
| Fuzz | Invariants under long random action sequences | 3 | 2000 random mutations, validated after each |
| Determinism | Seed reproduction | 5 | identical seed and actions give identical observations and rewards |
| Conformance | External contracts | 4 | `gymnasium.utils.env_checker.check_env` |
| End to end | The reward signal points somewhere | 1 | a traffic-following policy beats a static one |

Property tests carry most of the weight, deliberately. The absolute latency a
placement produces is a modelling choice that will change as the model is
calibrated; asserting on it would mean rewriting tests every time a parameter
moves. The *orderings* are the model's meaning and must not change: a read is
served by the nearest replica, distance from the traffic costs latency, an
all-acknowledgement write is never faster than a majority one, co-locating a
transaction's fragments removes the commit charge.

## Coverage by module

| Module | Approach | Notes |
|--------|----------|-------|
| `config` | Exact | Every validation branch; JSON round-trip; `evolve` does not mutate the original |
| `topology` | Property | Symmetry, diagonal, asymmetric input is symmetrized, geographic sanity (EU-EU closer than EU-Asia), immutability |
| `workload` | Property + exact | Seed reproduction, request-count conservation, drift moves the centroid, a full period returns to the start, zero volatility freezes, spikes are localized, cell angles are correlated not i.i.d. |
| `catalog` | Exact + fuzz | Keyspace partition, per-mutation byte costs, split/merge round-trip, every refusal path, 2000-step fuzz with `validate()` after each step |
| `cost` | Property + exact | The closed forms above, exact weighted percentiles, conservation of served operations |
| `actions` | Exhaustive | Encode/decode bijection over all 401 indices; **every action applied in every state along a trajectory, with no raise and no broken invariant** |
| `observation` | Via `env` | Covered by the box-containment test; a dedicated layout test is a gap |
| `simulator` | Determinism | Two simulators under the same actions stay in step |
| `env` | Conformance + behaviour | `check_env`, truncation not termination, reward composition per term |

## The three tests that matter most

**`test_actions.py::test_no_action_ever_raises_in_any_reachable_state`** walks a
random trajectory and, at every state visited, fires all 401 actions at a copy
of the catalogue, checking that none raises and no invariant breaks. This is the
direct proof of the property ADR-0002 depends on: DQN cannot mask invalid
actions, so every index must be defined in every state. If this test ever fails,
training is unsound, not merely worse.

**`test_cost.py::test_distance_from_the_traffic_costs_latency`** collapses the
whole cluster into each region in turn, with all demand originating in region 0,
and asserts that the resulting latencies are ordered exactly as the RTT row from
region 0. It is the tightest available statement that the cost model means what
it says, and it would catch a transposed index in `read_latency` or
`write_latency` immediately, which is the single most likely silent bug in the
codebase.

**`test_env.py::test_a_policy_that_follows_the_traffic_beats_one_that_does_not`**
runs a myopic tracker and a do-nothing policy over a full episode and asserts
the tracker wins on mean latency. If a policy that moves primaries toward the
traffic cannot beat one that does nothing, the reward function is not pointing
at the problem and no amount of DQN tuning will help. This is the small version
of the week 3 tabular Q-learning sanity check, and it runs on every commit.

## Running it

```bash
pytest                       # the whole suite, about one second
pytest tests/test_cost.py -v # one module
pytest -k percentile         # by name
pytest --durations=5         # find anything that has got slow
```

## Gaps, honestly

1. **No observation-layout test.** `ObservationEncoder.layout` is published but
   nothing asserts that a given block actually contains what its name claims.
   A test that plants a known demand pattern and reads it back out of the
   `read_demand` slice would catch an encoder reshuffle. Worth adding before the
   feature ablations in Objective 6, which slice the observation by name.
2. **No coverage measurement.** `pytest-cov` is not wired up. A target of 90%
   on `cost`, `catalog` and `actions`, and 70% elsewhere, would be honest;
   coverage on `env` matters less because `check_env` exercises it.
3. **Cost-model fidelity is untested against anything real.** Every cost test
   checks internal consistency. Whether the model ranks placements the way a
   real cluster does is exactly what the MongoDB harness is for (ADR-0001), and
   until it exists this is the suite's largest blind spot. Internal consistency
   is not validity.
4. **No performance regression test.** Step cost is currently about 0.5 ms. If
   an innocent-looking change makes it 5 ms, nothing notices until an overnight
   run does not finish. A test asserting 200 windows complete in under a second
   would be cheap insurance.
5. **Stochastic mode is barely tested.** `stochastic_counts=True` gets one test.
   If the experiments end up using it, it needs the same property coverage the
   deterministic path has.

## What gets tested as the project grows

- **Baselines (week 3).** Each baseline gets a characterization test pinning its
  behaviour on a fixed seed, so that a later refactor cannot silently change the
  opponent the agent is measured against. This matters more than it sounds: a
  baseline that quietly got worse is indistinguishable in the results from an
  agent that got better.
- **The tabular agent (week 3).** One test: on a reduced configuration, it beats
  static hashing. If that fails, the reward function is wrong, and week 3 is
  when to find out rather than week 6.
- **The DQN (weeks 4 to 5).** Not unit-tested. Instead, a smoke test that a
  short training run completes and the replay buffer fills, plus TensorBoard
  curves as the real diagnostic. Asserting on learning outcomes in a test suite
  makes the suite flaky and teaches nothing.
- **Experiment reproducibility (week 6).** A test that a saved configuration
  plus a seed reproduces a recorded episode's summary statistics to within
  floating-point tolerance. This is the claim Objective 2 makes, and it should
  be enforced rather than asserted in prose.
