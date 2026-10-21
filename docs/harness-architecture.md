# Harness architecture: the real-cluster half of the pipeline

Companion to [`architecture.md`](architecture.md), which describes the simulator.
Governed by [ADR-0009](adr/ADR-0009-cockroachdb-for-sim-to-real-parity.md).

The instructor has approved pre-training in the simulator and fine-tuning on a
real cluster. This document specifies the second half. Its one organizing
principle: **the cluster environment must be interchangeable with the simulator
environment from the agent's point of view.** Same observation space, same action
space, same reward units. Everything below follows from that.

## 1. The pipeline

```
   fragalloc.env (simulator)            fragalloc.harness.env (CockroachDB)
   ~0.5 ms per step                     ~2 to 6 s per step
   tens of thousands of steps           low thousands of steps
          |                                      |
          |  pre-train                           |  fine-tune
          +------------- DQN weights ------------>+
                    (loadable only if the
                     spaces match exactly)
```

Stable-Baselines3 `DQN.load(path, env=new_env)` validates `observation_space` and
`action_space` against the saved model and refuses a mismatch. That refusal is
the contract this document exists to satisfy. It is also the cheapest possible
integration test: if the load succeeds, the spaces agree.

| Phase | Environment | Learning rate | Exploration | Replay buffer |
|---|---|---|---|---|
| Pre-train | simulator | as tuned | full schedule | fills normally |
| Fine-tune | cluster | one tenth of pre-train | short, low final epsilon | **starts empty** |

The replay buffer starts empty on purpose. Simulator transitions carry the
simulator's dynamics, and replaying them against the cluster's reward would teach
the analytic model rather than the database. Set `learning_starts` to roughly one
episode so the agent acts on its prior whilst the buffer fills.

## 2. Topology, and the parity constraint that fixes it

**Six regions, one CockroachDB node per region, replication factor 3.**

The region count is not free. `n_regions` enters both the action-space
cardinality and the observation dimensionality, so the cluster and the simulator
must agree on it. Six matches `TopologyConfig`'s default region set, which is
what every existing measured result was produced on.

Replication factor must be strictly less than the region count, or
`MOVE_REPLICA` is degenerate: at three regions and RF 3 every range already has a
replica in every region and there is nowhere to move one. Six and three gives
each fragment three source regions and three destination regions, so nine
meaningful replica moves per fragment.

| Component | Count | Memory settings |
|---|---|---|
| `cockroach` node | 6 | `--cache=128MiB --max-sql-memory=256MiB` |
| Toxiproxy | 1 | negligible |
| Load generator | 6 processes, one per region | share one Python process pool |

Six nodes at those settings is roughly **2.3 GB**, reduced from an earlier 4.5 GB
by [ADR-0010](adr/ADR-0010-session-scoped-cluster-and-resumable-runs.md) because
the machine also has to run an IDE, a browser and other coursework. The dataset
on the cluster is small, so a large block cache buys nothing. **If the pilot shows six nodes
will not fit, the fallback is four regions on both sides**, which means re-running
the simulator sweeps at four regions before any weights are transferred. Decide
this in the pilot, not in week 6.

Latency comes from Toxiproxy rather than `tc`/`netem`: the CockroachDB image
ships no `iproute2`, and Toxiproxy can change latency mid-run, which the
volatility experiments want. Toxiproxy latency is applied per proxy, so an
intended round trip of `r` between two regions is `r/2` on each direction's
proxy. Getting that wrong puts every number in the paper out by a factor of two.

## 3. Module layout

```
src/fragalloc/harness/
  cluster.py      compose-file generation, node lifecycle, Toxiproxy control,
                  cluster-setting application and verification
  placement.py    range-id and store-id resolution, placement readback,
                  intent assertion
  executor.py     action -> SQL statement, error classification
  driver.py       concurrent per-region transaction load, client-side timing
  env.py          Gymnasium environment, spaces identical to fragalloc.env
  checkpoint.py   save and restore: agent state, placement, workload position
```

Dependency rule, mirroring [ADR-0005](adr/ADR-0005-simulator-independent-of-gymnasium.md):
`harness` depends on `fragalloc.actions`, `fragalloc.catalog`,
`fragalloc.observation`, `fragalloc.workload` and `fragalloc.topologies`. It must
**not** import `fragalloc.cost` or `fragalloc.simulator`. The cluster replaces
the cost model; importing it would invite accidentally reporting a modeled number
as a measured one.

`catalog.py` remains the single source of truth for what the placement *should*
be. The cluster is the authority on what it *is*. `placement.py` reconciles them
and that reconciliation is the harness's most important function, because a
silent divergence is a corrupted reward.

## 3a. The session model

The laptop cannot stay on. It moves between buildings and is needed for other
work, so **the cluster is disposable and the run is checkpointed**, per
[ADR-0010](adr/ADR-0010-session-scoped-cluster-and-resumable-runs.md).

```
  make cluster-up      ~2 min   6 nodes, Toxiproxy, settings, licence key
  make resume          ~10 s    restore placement + agent state from checkpoint
  <one or more episodes>        200 windows each, 7 to 20 min
                                checkpoint written at every episode boundary
  make cluster-down    ~5 s     tear down completely
```

Three properties follow, and each is load-bearing.

**The episode is the scheduling unit.** `windows_per_episode` is 200, which at 2
to 6 s per step is 7 to 20 minutes. That fits between classes. It was chosen for
other reasons and should not be changed without noticing it now also governs how
long the laptop must stay open.

**Resume uses the normal step path.** Placement is replayed onto a fresh cluster
with the same `RELOCATE` statements the agent issues, so the resume path is
exercised at the start of every session rather than being emergency code that
rots. The checkpoint holds model weights and optimizer state, the replay buffer,
NumPy and Torch RNG states, the workload window index and seed, the full
placement, and the step counters.

**A suspend must never become a data point.** Every step records both
`time.monotonic()` and `time.time()` around its measurement window. If the
wall-clock delta exceeds the monotonic delta beyond a small tolerance, the host
slept mid-measurement: the latency sample is **discarded, not clamped**, the
transition is not added to the replay buffer, and the episode is flagged. A
clamped sample is a fabricated measurement, and the count of discarded steps is
reported with every run.

Two things that do **not** need engineering around, recorded so nobody spends a
day on them. CockroachDB nodes self-terminate when out of sync with half the
cluster by 80 percent of `--max-offset`, but all six nodes share one host clock,
sleep together and wake together, so they never drift relative to each other.
`--max-offset` stays at its 500 ms default. And the licence throttle, five
concurrent transactions after seven days without telemetry, is structurally
unreachable when the cluster is rebuilt each session, though the free key should
still be obtained because multi-node operation without one is outside the
licence grant.

**Toxiproxy latency is reapplied on every `cluster-up`** and asserted
afterwards. It lives in a container that is torn down with everything else, and a
silently zero-latency cluster produces numbers that look plausible and mean
nothing.

## 4. The step protocol

Each `step(a)` runs this sequence. The ordering is load-bearing.

1. **Decode** `a` into `(kind, args)` via the same `ActionSpace` the simulator
   uses. Not a parallel implementation. The same object.
2. **Resolve** the fragment to a range id and the region to a store id.
   `SHOW RANGES FROM TABLE t WITH DETAILS` and
   `SELECT store_id, node_id FROM crdb_internal.kv_store_status`. Cache both and
   invalidate the range cache on any `SPLIT`.
3. **Execute** one statement. Classify the outcome into `applied`, `rejected`
   (the statement raised; for example "unable to find store" or a descriptor
   conflict) or `no-op` (the action was already satisfied). Never retry silently.
4. **Read back** placement with `SHOW RANGES ... WITH DETAILS`, which carries
   `voting_replicas`, `lease_holder` and `lease_holder_locality` in one query.
5. **Assert** the readback matches intent. On divergence, record it, update
   `catalog` from the cluster rather than from intent, and surface the failure to
   the agent as a distinct observable rather than swallowing it. The allocator
   should be off, but assume it is not.
6. **Advance the workload window.** The workload is open-loop
   ([ADR-0006](adr/ADR-0006-cell-based-fragments-and-open-loop-workload.md)), so
   it does not observe the agent and this step is independent of 1 through 5.
7. **Drive `N` transactions**, concurrently, one load generator per region,
   drawing keys from the current window's per-region distribution. Time each
   transaction client-side with a monotonic clock. Server-side
   `statement_statistics` aggregates by fingerprint and cannot attribute one
   transaction to one placement, so it is corroboration only.
8. **Compute reward** in the same units the simulator uses: negative weighted
   latency percentile, minus the migration cost of the executed action. Migration
   cost is **a fraction of total dataset size, never raw bytes**: the simulator
   holds 60 GB and the cluster one or two, so a bytes-denominated term would put
   the two environments on different scales and make every pre-trained Q-value
   wrong by a constant. Identical formula, different latency source.
9. **Encode observation** with the unchanged `ObservationEncoder`, from the
   reconciled catalog and the window's workload estimate.
10. **Return** `(obs, reward, terminated, truncated, info)`, with `info`
    carrying the raw latency sample, the outcome class from step 3, and any
    divergence from step 5.

## 5. The measurement protocol

**This is where the experiment's credibility lives, and it is the part most
likely to be done casually.**

`N`, the number of transactions per step, trades wall clock against reward
variance. Too few and the agent learns noise. Too many and the run does not
finish. `N` must be chosen by measurement, not by guess:

1. Hold placement fixed. Drive 2000 transactions.
2. Bootstrap the p95 estimate to get its standard error as a function of
   subsample size.
3. Choose the smallest `N` whose p95 standard error is below one third of the
   smallest effect the paper needs to detect. The sensible target is the
   simulator's static-to-follow gap, which measured 157 ms against 94 ms.
4. Report `N` and that standard error in the methods section. It is a result,
   not an implementation detail.

Two confounds to control explicitly rather than hope about:

- **The gateway node is part of the latency.** A transaction's cost includes the
  hop from client to gateway. Run one generator per region, pinned to that
  region's node, and make gateway choice an explicit part of the design.
- **Concurrency changes latency.** Queueing at 16-way concurrency is not the same
  as at 1-way. Fix the concurrency level across all conditions, state it, and do
  not tune it between the baseline runs and the agent runs.

## 6. Failure modes the harness must detect

| Failure | Detection | Response |
|---|---|---|
| Licence throttle, 5 concurrent transactions after 7 days without telemetry | observed concurrency collapses; p95 jumps by an order of magnitude | **abort the run loudly.** Never let this become a data point |
| Allocator undoes a placement | step 5 readback diverges from intent | record, resync catalog from cluster, continue; if frequent, the settings did not take |
| `RELOCATE` raises "range already being rebalanced" | statement raises | classify `rejected`, surface to the agent, do not retry |
| Range cache stale after a split | range id not found | invalidate and re-resolve once, then fail |
| Node death under memory pressure | connection refused | abort; six nodes on 16 GB is the suspect |

The throttle case deserves the emphasis. A cluster quietly limited to five
concurrent transactions still returns numbers, and those numbers look like a
catastrophic latency regression rather than like a licensing event. Assert
against it on every step.

## 7. Scope boundaries

In scope: lease placement, replica placement at fixed replication factor, and
range splitting, on six regions under injected wide-area latency, with
transaction latency measured client-side.

Out of scope, and each needs one sentence in the paper's limitations:

- **Replication factor as an agent decision.** Fixed at 3. The durability
  trade-off is not modeled.
- **Merge.** CockroachDB offers only `UNSPLIT` into a merge queue, so shard count
  is monotone within an episode.
- **Throughput.** [ADR-0004](adr/ADR-0004-analytic-cost-model.md) already
  excluded queueing from the cost model; the harness measures latency at a fixed
  concurrency and makes no throughput claim.
- **Failure and recovery.** The balancer is disabled, so the cluster has no
  self-healing during an episode. This is a controlled experiment, not an
  availability study.

## 8. Build order

Each step de-risks the next. Do not reorder.

1. `cluster.py`: `up` / `down` / `status` / `verify` **written as scripts on day
   one**, before a hand-tuned cluster exists to become precious. Six nodes,
   Toxiproxy in place and asserted, the five settings applied and verified
   individually on every start, licence key installed.
2. **The falsification test.** Single-region against cross-region transaction
   latency, by hand, no agent. If the gap is not clearly larger than run-to-run
   noise there is no reward signal and the approach fails here, cheaply.
3. `placement.py`: resolve, read back, assert. Test it by issuing relocations by
   hand and confirming the readback.
4. The measurement protocol from section 5. Fix `N`.
5. `executor.py`: the three statements, with error classification.
6. `driver.py`: concurrent per-region load.
7. `env.py`, then immediately `DQN.load` against it with a simulator-trained
   model. If the load succeeds, the spaces agree and the pipeline is real.
