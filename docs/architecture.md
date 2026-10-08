# Architecture

**Date:** 2026-09-20
**Audience:** anyone picking this repository up, including future you in week 7.

## Context and goals

This project asks whether a Deep Q-Network can continuously re-fragment and
re-allocate database shards across regions under workloads whose geographic
origin keeps moving. The software has to support six research objectives, only
two of which involve an agent, so the design is driven as much by what the
baselines and the validation harness need as by what the agent needs.

Constraints that shaped everything: one laptop, eight weeks, no GPU, no cloud
spend, and an author who had not implemented RL before starting.

## High-level design

```
                 ShardMindConfig          one frozen record describes a run
                        |
        +---------------+---------------+
        |               |               |
   Topology       WorkloadGenerator   FragmentCatalog
   regions,       drifting demand     boundaries, primaries,
   RTT matrix     over cells          replicas; five mutators
        |               |               |
        +-------+-------+---------------+
                |
             cost.evaluate                CostBreakdown:
             analytic latency,            mean, p95, per-class,
             load, tail                   load, storage, churn
                |
         ClusterSimulator                 clock, episode, transition
         (no RL vocabulary)
                |
        +-------+--------+
        |                |
   ShardMindEnv      baselines /          the adapter is thin on purpose
   Gymnasium         validation harness
   obs, reward
        |
   Stable-Baselines3 DQN
```

The load-bearing boundary is between `ClusterSimulator` and `ShardMindEnv`.
Everything below it is a model of a database cluster and imports only NumPy.
Everything above it is reinforcement learning. ADR-0005 has the argument; the
short version is that four of six objectives live below the line, and a cost
model test that asserts on `mean_txn_latency_ms` is debuggable where one that
asserts on `obs[698]` is not.

## Data flow through one step

1. `ShardMindEnv.step(a)` receives an integer.
2. `ActionSpace.decode(a)` turns it into a desired end state.
3. `ActionSpace.apply` calls one of `FragmentCatalog`'s five mutators, which
   either changes the catalogue and reports bytes moved, or refuses and reports
   why. It never raises (ADR-0002).
4. The clock advances. `WorkloadGenerator.window(t)` returns the next window's
   demand, which depends on `t` and the seed and on nothing the agent did.
5. `cost.evaluate` scores the new catalogue against that demand and returns a
   `CostBreakdown`.
6. `ObservationEncoder.encode` builds the observation vector.
7. `ShardMindEnv._reward` scalarizes the cost vector.

One step is roughly half a millisecond, so a 200-window episode is about a tenth
of a second and tens of thousands of episodes are an overnight run on a CPU.

## Key decisions and trade-offs

Recorded as ADRs in `docs/adr/`:

| ADR | Decision | The trade-off in one line |
|-----|----------|---------------------------|
| [0001](adr/ADR-0001-simulate-rather-than-measure.md) | Simulate; validate on a real cluster as a stretch goal | Sweeps become affordable; fidelity must be argued rather than assumed |
| [0002](adr/ADR-0002-flat-declarative-action-space.md) | Flat declarative actions, no masking | DQN works unmodified; about half the actions change nothing in the initial state |
| [0003](adr/ADR-0003-stable-baselines3-over-hand-rolled-dqn.md) | Stable-Baselines3, not a hand-rolled DQN | A non-converging run has one suspect instead of two |
| [0004](adr/ADR-0004-analytic-cost-model.md) | Analytic expected cost, not discrete-event | Exact percentiles and 2000 windows/second; no queueing, so no throughput claims |
| [0005](adr/ADR-0005-simulator-independent-of-gymnasium.md) | Simulator independent of Gymnasium | Baselines and validation work directly on the model; one extra module |
| [0006](adr/ADR-0006-cell-based-fragments-and-open-loop-workload.md) | Cell-based fragments, correlated cell angles, open-loop workload | Splitting is meaningful and the MDP stays Markov; the workload ignores the agent |
| [0007](adr/ADR-0007-real-database-validation.md) | Train in simulation, validate on CockroachDB | **Superseded by 0008.** Two central claims were wrong: a synchronous placement API does exist, and zone configs were the wrong primitive |
| [0008](adr/ADR-0008-database-selection.md) | Citus as the real environment | **Superseded by 0009.** The twenty-one-system screen stands; its conclusion predated the pre-training approval |
| [0009](adr/ADR-0009-cockroachdb-for-sim-to-real-parity.md) | CockroachDB, at fixed replication factor | The cost model and observation encoder transfer intact; `MERGE` is dropped and RF leaves the agent's control |

## Module reference

| Module | Responsibility | Depends on |
|--------|----------------|-----------|
| `config` | Every tunable, in frozen dataclasses; JSON round-trip | nothing |
| `topology` | Regions, RTT matrix, the geographic circle | `config` |
| `workload` | Drifting demand over cells; transaction templates; spikes | `config`, `topology` |
| `catalog` | Fragment boundaries, placement, the five declarative mutators | `config` |
| `cost` | Analytic latency, exact tail, load and storage accounting | `config`, `catalog`, `topology`, `workload` |
| `actions` | The 401-action flat space; encode, decode, apply | `catalog` |
| `observation` | State to unit-box vector, with a published layout | all of the above |
| `simulator` | Clock, transition, episode, snapshots | all of the above |
| `env` | Gymnasium adapter: observation, action, reward | `simulator`, `observation` |
| `policies` | Reference policies for exercising the environment | `simulator`, `actions` |

## Integration points

- **Gymnasium.** `ShardMindEnv` registers as `ShardMind-v0` and passes
  `gymnasium.utils.env_checker.check_env`. Episodes truncate, never terminate;
  the distinction matters for value bootstrapping.
- **Stable-Baselines3.** Not yet wired. `MlpPolicy` over a 703-element `Box`
  and a `Discrete(401)`. Phase 3.
- **`shardmind/harness/`, the CockroachDB environment.** Not yet built, and on
  the critical path. Six nodes, one per region, replication factor 3, Toxiproxy
  supplying wide-area latency. Placement driven by three synchronous statements:
  `ALTER RANGE ... RELOCATE LEASE`, `ALTER RANGE ... RELOCATE VOTERS` and
  `ALTER TABLE ... SPLIT AT`. It must expose the **same** observation and action
  spaces as `shardmind.env`, because that is what lets a simulator-pre-trained
  DQN load against it. Specified in
  [harness-architecture.md](harness-architecture.md); decided in
  [ADR-0009](adr/ADR-0009-cockroachdb-for-sim-to-real-parity.md), which supersedes
  ADR-0008 and, through it, the MongoDB plan in ADR-0001. The dependency rule:
  `harness` may import `shardmind.actions`, `catalog`, `observation`, `workload`
  and `topologies`, but **not** `cost` or `simulator`, so a modeled number can
  never be reported as a measured one.
- **Experiment records.** `ClusterSimulator.snapshot()` returns a flat
  JSON-friendly dict per step, and `ShardMindConfig.save` writes the run's full
  configuration. Together those are enough to reproduce any figure.

## What is not here yet

Phase 2 onward, in `docs/roadmap.md`:

- `shardmind/baselines/`: consistent hashing, greedy nearest-region, threshold
  rebalancing, and a Lion-style cost-model rebalancer.
- `shardmind/harness/`: the CockroachDB executor, placement reader and workload
  driver. Depends on `shardmind.cost` and `shardmind.catalog`, nothing above.
- A tabular Q-learning agent on a reduced state space, as the week 3 check that
  the reward function points somewhere before the DQN is suspected of anything.
- The DQN itself, the sweeps, and the ablations.
