# ADR-0010: A session-scoped cluster and episode-checkpointed runs

**Status:** Accepted.
**Date:** 2026-10-07
**Deciders:** Tinotenda Kaseke
**Extends:** [ADR-0009](ADR-0009-cockroachdb-for-sim-to-real-parity.md)

## Context

Two operating constraints were not in the earlier decisions, and both are hard.

**No charge, under any circumstance.** The project has no budget.

**The laptop cannot stay on.** It moves between buildings, it is needed for
other classes and projects, and it sleeps several times a day. Every earlier
plan quietly assumed a machine that could sit undisturbed for hours.

The first constraint turns out not to bind. The second rewrites the harness.

### What the licence actually costs: nothing

Verified against the current documentation rather than assumed:

- The **Free** licence carries "the same features as Enterprise, free of charge
  for businesses with less than $10M in annual revenue." A student research
  project qualifies with room to spare.
- Obtaining one is a form, some qualification questions, agreeing to terms, and
  generating a key. **The documentation describes no credit card and no payment
  method.** Read the form before submitting it, but there is nothing to pay.
- Cockroach Labs state plainly: "Cockroach Labs encourages non-commercial
  academic research involving CockroachDB", and direct such projects to this
  licence.

So the licence is free and it should simply be obtained. Two operational facts
attach to it and both matter here:

- Free and Trial clusters must send telemetry, and "clusters will be throttled
  after 7 days without sending telemetry." Throttling caps concurrent open SQL
  transactions at **5**.
- A cluster with no key at all is throttled 7 days after initialization, and
  single-node development clusters are never throttled.

A cluster that is rebuilt for each work session restarts that 7-day clock every
time, so the throttle is structurally unreachable under the design below. That is
a happy side effect, **not** the reason for the design, and it is not a reason to
skip the key: multi-node operation without one falls outside the licence's
Limited Non-Production Use grant, which is single-node only.

### What sleeping does, and does not, break

The instinct is to worry about clock skew. CockroachDB nodes shut themselves
down when out of sync "with at least half of the other nodes in the cluster by
80% of the maximum offset allowed", 400 ms at the 500 ms default.

**That failure does not apply here, and it is worth recording why so nobody
engineers around a problem they do not have.** All six nodes are co-located on
one host and share one system clock. They sleep together and wake together, so
they never drift relative to *each other*, which is the only comparison the
check makes. A geographically distributed cluster on sleeping laptops would die;
six containers on one laptop will not.

What sleeping does break is more mundane and more damaging to the science:

| Breaks | Consequence |
|---|---|
| Node liveness records expire during suspend | Nodes see each other as dead, then recover together. Usually fine, occasionally slow, never guaranteed clean |
| Raft leases expire | Re-acquired on wake, but placement may not be what the agent last set |
| Open SQL connections drop | The in-flight step raises mid-measurement |
| **Wall clock jumps forward** | A transaction timed across the suspend records minutes of latency. **This is the dangerous one**: it is a plausible-looking number, not an error |

The last row is the real risk. A suspend in the middle of a measurement window
produces a latency sample that is wrong by orders of magnitude and looks like a
catastrophic placement decision. The agent would learn from it.

## Decision

**The cluster is ephemeral and scoped to a work session. The run is checkpointed
every episode. Measurements that span a suspend are detected and discarded.**

### The session model

```
  make cluster-up      ~2 min   6 nodes, Toxiproxy, settings, licence key
  make resume          ~10 s    restore placement + agent state from checkpoint
  <one or more episodes>        200 windows each, 7 to 20 min
  make checkpoint               written automatically at each episode boundary
  make cluster-down    ~5 s     tear down completely
```

Nothing is expected to survive the teardown except the checkpoint directory. The
cluster is treated as disposable infrastructure rebuilt from a script, which is
the only assumption that survives a laptop being closed mid-thought.

### The episode is the unit of work, and it already fits

`EpisodeConfig.windows_per_episode` is 200. At 2 to 6 s per step that is **7 to
20 minutes per episode**, which fits between classes without planning around it.
This is a fortunate accident of a parameter chosen for other reasons, and it
should not be changed without noticing that it is now also the scheduling unit.

### The checkpoint

Written at every episode boundary, to `results/checkpoints/<run-id>/`:

| Contents | Why |
|---|---|
| DQN weights and optimizer state | the model |
| Replay buffer | discarding it on every resume would cripple learning |
| RNG states, NumPy and Torch | reproducibility across a resume |
| Workload window index and seed | the workload must continue, not restart |
| Full placement: every fragment's replicas and leaseholder | the cluster is rebuilt empty and must be put back |
| Episode and step counters, and the licence-throttle assertion baseline | so a resumed run is auditable |

Resume replays the placement onto a fresh cluster with the same `RELOCATE`
statements the agent uses, then continues. A resume is therefore exercised by the
same code path as a normal step, which is the cheapest way to keep it working.

### Suspend detection

Every step records both `time.monotonic()` and `time.time()` around the
measurement window. If the wall-clock delta exceeds the monotonic delta by more
than a small tolerance, the host suspended mid-step. The step's latency sample is
**discarded, not clamped**, the transition is not added to the replay buffer, and
the episode is flagged in its metadata.

Discarding rather than clamping matters. A clamped sample is a fabricated
measurement, and a research harness that silently fabricates measurements is
worse than one that loses a few.

### Memory, so the laptop stays usable

Reduced from [ADR-0009](ADR-0009-cockroachdb-for-sim-to-real-parity.md)'s
figures, because the machine has to run an IDE, a browser and other coursework
at the same time:

| Setting | Was | Now |
|---|---|---|
| `--cache` | 256 MiB | **128 MiB** |
| `--max-sql-memory` | 512 MiB | **256 MiB** |
| Per node | ~750 MiB | **~384 MiB** |
| Six nodes | ~4.5 GB | **~2.3 GB** |

The dataset on the cluster is small, so a large block cache buys nothing. Add a
`make cluster-down` to the end of every session rather than leaving containers
idling: 2.3 GB reclaimed is the difference between a usable laptop and a
swapping one.

### Reward normalization, which the scale change forces

`CatalogConfig.dataset_bytes` is 60 GB in the simulator. The cluster will hold
one or two. The reward is negative latency **minus migration cost**, and if
migration cost is expressed in bytes those two terms sit on wildly different
scales in the two environments. The pre-trained Q-values would then be wrong in a
way that fine-tuning has to unlearn, which is exactly the failure
[ADR-0009](ADR-0009-cockroachdb-for-sim-to-real-parity.md) chose CockroachDB to
avoid.

**Both environments must express migration cost as a fraction of total dataset
size, not in bytes.** The reward becomes unit-free in that term and transfers.
This is a change to `shardmind.cost` as well as to the harness, and it must be
made before pre-training starts, because every pre-trained weight depends on it.

## Options Considered

### Option A: a long-lived cluster the laptop keeps running

| Dimension | Assessment |
|---|---|
| Complexity | Low, until it fails |
| Fits the constraint | **No** |

**Cons:** it is the plan every earlier document implicitly assumed, and it
requires the machine to sit undisturbed for hours. It does not survive a walk
between buildings.

### Option B: a cloud-hosted cluster

| Dimension | Assessment |
|---|---|
| Fits the laptop constraint | **Perfectly**, it runs without the laptop |
| Cost | **Fails the constraint** |
| Placement control | Fails on the free tier anyway |

**Cons:** dedicated multi-node clusters cost money, which is excluded. The free
serverless tier is multi-tenant and exposes no node-level placement, so
`ALTER RANGE ... RELOCATE` is not available and the project's primary action does
not exist. Rejected on both counts, and the second would hold even with a budget.

### Option C: single-node CockroachDB, never throttled and no key needed

| Dimension | Assessment |
|---|---|
| Licence | Cleanest possible |
| Placement | **There is none** |

**Cons:** one node means one store, so there is nowhere to relocate anything.
This removes the entire subject of the research. Noted only because the licence
documentation makes it look attractive.

### Option D: session-scoped cluster with episode checkpointing

Chosen. It costs one script and one checkpoint format, and in exchange nothing in
the project assumes an uninterrupted machine.

## Trade-off Analysis

The cost of Option D is about two days of engineering for the lifecycle script,
the checkpoint format and the suspend detector, taken out of a 30-day budget that
is already tight.

It buys three things worth more than two days. **Interruption stops being a
failure.** A closed laptop costs at most the current episode, which is minutes.
**The resume path is exercised constantly rather than being emergency code**,
because every session begins with one. And **a rebuilt-from-script cluster is
reproducible by definition**, which the paper's methods section needs anyway and
which an eight-week-old hand-tuned cluster never is.

The honest risk is that episode boundaries become the only safe interruption
points, so closing the laptop mid-episode still costs that episode. At 7 to 20
minutes that is acceptable. If it proves not to be, checkpoint every 50 windows
instead of every 200; the format does not change.

## Consequences

- **`shardmind/harness/cluster.py` grows a lifecycle**: `up`, `down`, `status`,
  and a `verify` that re-checks the five balancer settings on every start, since
  a fresh cluster has them at defaults.
- **A `Makefile`, or equivalent**, so a session starts with one command. This is
  not polish. A multi-step manual startup performed twice a day will be got wrong.
- **`shardmind/harness/checkpoint.py` is a new module** with one job and a
  round-trip test.
- **`shardmind.cost` changes**: migration cost becomes a dataset fraction. Before
  pre-training, not after.
- **Every reported run states how many steps were discarded to suspends.** If
  that number is large the result is weaker, and hiding it would be misconduct.
- **The simulator gains the same checkpoint format.** Pre-training is hours of
  wall clock and faces the identical interruption problem; there is no reason for
  two mechanisms.
- **Toxiproxy latency must be reapplied on every cluster start**, since it lives
  in a container that is also torn down. Put it in `cluster-up` and assert it
  afterwards, because a silent zero-latency cluster produces numbers that look
  plausible and mean nothing.
- **`--max-offset` stays at its 500 ms default.** The co-located clock argument
  above says the skew check will not fire; raising the offset would weaken a real
  safety property for no benefit.

## Action Items

1. [ ] Obtain the Enterprise Free licence key. Free, no payment method, a few
   minutes. Do it before standing up six nodes.
2. [ ] Write `cluster-up` / `cluster-down` as scripts on day one, before any
   manual cluster exists to become precious.
3. [ ] Implement suspend detection in the measurement loop **before the first
   real run**, not after a suspicious result appears.
4. [ ] Change migration cost to a dataset fraction in `shardmind.cost`, with a
   test asserting the simulator and harness agree on the same placement change.
5. [ ] Checkpoint round-trip test: save, tear the cluster down, bring it up,
   restore, and assert placement and agent state match exactly.
6. [ ] Record in `docs/validation-plan.md` how discarded steps are reported.

## Sources

- [Licensing FAQs](https://www.cockroachlabs.com/docs/stable/licensing-faqs), for the Free licence, the academic-research statement, and the 7-day telemetry throttle to 5 concurrent transactions
- [Operational FAQs](https://www.cockroachlabs.com/docs/stable/operational-faqs), for the 80%-of-max-offset self-termination rule and the 500 ms default
