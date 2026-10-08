# Roadmap

**Window:** 11 September to 6 November 2026. **Rewritten 7 October**, at day 27
of 57, because [ADR-0009](adr/ADR-0009-cockroachdb-for-sim-to-real-parity.md) put
a real-cluster workstream on the critical path and the original plan had no room
for one.

## Where the project actually stands

| | State |
|---|---|
| Simulator, workload, cost model, action space, observation | **done**, 122 tests passing |
| Baselines | **partial.** `NoOpPolicy`, `RandomPolicy`, `GreedyPrimaryPolicy` built. No characterization tests. Threshold and Lion-style rebalancers not built |
| Visualization, dashboards, GIS map, figure design system | **done** |
| Tabular Q-learning sanity check | **not started** |
| DQN wiring | **not started**. No `shardmind/agent/`, no `scripts/train.py` |
| Real-cluster harness | **not started**. `shardmind/harness/` specified in [`harness-architecture.md`](harness-architecture.md), not built |
| Paper | **not started** |

Two measured results already exist and are reportable: a traffic-following
policy beats static hashing 94 ms against 157 ms at 451 GB moved per episode,
and per-cell traffic concentration is 53 percent against an even split of 16.7
percent whilst per-fragment is 41 percent. Both are **simulator** results and
must be labeled as such throughout.

## The shape of the remaining 30 days

Two tracks, run in parallel, because the cluster work is mostly waiting on
containers and the simulator work is mostly waiting on training runs. One gate
between them that decides whether the headline result is measured or modeled.

```
  Track A  simulator        action encoding -> tabular Q -> DQN -> pre-train -> sim results
  Track B  cluster          key -> 6 nodes -> settings -> FALSIFICATION TEST -> harness -> fine-tune
                                                              |
                                                     GATE, 12 October
```

| Block | Dates | Track A, simulator | Track B, cluster |
|---|---|---|---|
| 1 | 07–12 Oct | Fix the `MOVE_REPLICA` encoding; set RF 3; tabular Q sanity check | Licence key; six nodes up; verify five settings; **falsification test** |
| 2 | 13–19 Oct | DQN wired; first runs on the reduced instance | Measurement protocol, fix `N`; `placement.py`; `executor.py` |
| 3 | 20–26 Oct | Full pre-training; pre-training converged and saved | `driver.py`; `harness/env.py`; `DQN.load` parity check |
| 4 | 27 Oct–02 Nov | Simulator results, sweeps, all figures | **Fine-tuning run**, overnight; cluster results |
| 5 | 03–06 Nov | Full draft, revision, buffer | |

## The gate, 12 October

**Question:** on a six-node cluster under injected wide-area latency, is the
single-region against cross-region transaction latency gap clearly larger than
run-to-run noise?

**How it is answered:** by hand, with no agent and no learning. Place a table's
ranges so that a transaction's participants sit in one region, measure. Move them
so the participants span three regions, measure. Compare the gap against the
spread of repeated measurements at fixed placement.

**If yes:** proceed as planned. The paper's headline is a measured result.

**If no:** the reward signal does not exist on the real cluster, and no amount of
agent engineering fixes that. Fall back immediately to **simulator results as the
contribution**, with the cluster reported as a measured negative finding: the
placement-latency coupling the simulator assumes was not recoverable at
laptop scale under Toxiproxy injection. That is a publishable methods result and
an honest paper. It is a much worse outcome discovered on 2 November.

This gate exists because it is the cheapest possible way to find out whether the
project's central assumption survives contact with a real database, and because
discovering it late is the single largest risk on the board.

## What was cut, and why

Being explicit, so none of it gets quietly reintroduced in week 4 and sink the
schedule.

| Cut | Reason |
|---|---|
| **Volatility sweep on the cluster** | At 2 to 6 s per step a sweep across nine volatility levels is days of wall clock. Report the sweep from the simulator, labeled as simulator, on the three axes the earlier finding requires: latency, tracking gap, migration volume |
| **More than two seeds on the cluster** | Two seeds on the cluster, five in the simulator. State both counts |
| **`MERGE` as an action** | CockroachDB has no synchronous merge ([ADR-0009](adr/ADR-0009-cockroachdb-for-sim-to-real-parity.md)). Shard count is monotone within an episode |
| **Replication factor as an agent decision** | Fixed at 3. The durability trade-off leaves the scope |
| **Lion-style cost-model rebalancer baseline** | Stretch. It is the strongest related-work comparison and the first thing to add back if block 2 finishes early |
| **Six regions, if the pilot says they will not fit** | Fall back to four regions on **both** sides and re-run the simulator baselines at four. Decide in block 1, never later, because region count fixes the action-space cardinality and therefore weight transfer |

## Block 1, concretely

Six days, and the ordering matters because each item de-risks the next.

**Track B first, because it has a hardware answer that could change everything.**

1. **Obtain the Enterprise Free licence key.** Minutes. Do it before touching
   Docker. A cluster running without one is throttled to five concurrent
   transactions after seven days, and that throttle looks exactly like a
   catastrophic latency regression rather than like a licensing event.
2. **Six nodes up under Docker**, one per region, `--cache=256MiB
   --max-sql-memory=512MiB`, distinct `--locality`, Toxiproxy between regions at
   half the intended round trip per direction. If six will not fit in 16 GB, call
   the four-region fallback **today**.
3. **Verify the five balancer settings individually.** Four of
   `kv.allocator.load_based_rebalancing`, `kv.replicate_queue.enabled`,
   `kv.lease_queue.enabled`, `kv.split_queue.enabled` and
   `kv.range_merge.queue.enabled` are in source but absent from the public
   settings documentation. Set each, read it back, and confirm placement stops
   drifting with the agent idle.
4. **The falsification test.** The gate above.

**Track A, which can proceed whilst containers download.**

5. **Fix the `MOVE_REPLICA` encoding.** The naive `(fragment, from, to)` form is
   `20 x 6 x 6 = 720` actions, which is worse than the 401 it replaces. The
   working proposal is destination-only, `MOVE_REPLICA_TO(f, r)`, with the source
   chosen as the replica whose region is farthest from `r`, giving
   `20 x 6 x 2 + 20 + 1 = 261`. **Measure applicability under it before
   committing**, and record the tie-break as part of the action semantics in an
   amendment to [ADR-0002](adr/ADR-0002-flat-declarative-action-space.md), not as
   an implementation detail.
6. **Set replication factor to 3** and re-run the two headline measurements to
   confirm they survive at fixed RF. If the 94-against-157 gap moves materially,
   that is a finding and the paper's numbers change.
7. **Tabular Q-learning on a reduced state space.** Three regions, three
   fragments, allocation only. One question: can *any* learning agent beat static
   hashing here? If not, the reward function is wrong, and half a day in block 1
   is the whole point of asking.

## Not yet built

- `shardmind/agent/`, wrapping Stable-Baselines3 DQN, block 2
- `scripts/train.py`, `scripts/finetune.py`, block 2 and 3
- `shardmind/harness/`, the five modules in [`harness-architecture.md`](harness-architecture.md), blocks 1 to 3
- `docs/validation-plan.md`: topology, injected latencies, workload parameters,
  and the agreement statistic that counts as a pass. **Fix the threshold before
  seeing results**
- Characterization tests for the three existing baselines, pinning each on a
  fixed seed
- `tests/test_policies.py`, `tests/test_simulator.py`, `tests/test_observation.py`
  are absent. The coverage gap is real but it is behind the paper in priority
- `paper/`, block 5

## The schedule's honest risk

The plan has four days of buffer, which is thin, and it depends on the fine-tuning
run in block 4 working first time. The mitigating fact is that pre-training moves
the expensive part off the cluster: at 2 to 6 s per step a 2000-step fine-tuning
run is 1 to 3.5 hours and fits in a night. The thing that would actually break
this schedule is not compute, it is discovering on 2 November that the cluster
never had a signal to learn from. That is what the 12 October gate is for.
