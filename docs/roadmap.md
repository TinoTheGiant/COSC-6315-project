# Roadmap

**Target: 26 October 2026.** Rewritten 19 October, at day 39, for two reasons:
the deadline moved in from 6 November, and the midterm rubric arrived and says
what the submission is actually marked on. The plan below is organized around
that rubric rather than around the original phase structure, because points not
earned are the only failure mode that matters this week.

## Where the project actually stands

| | State |
|---|---|
| Simulator, workload, cost model, action space, observation | **done**, 152 tests passing |
| Reference policies | **done.** `StaticHashPolicy`, `RandomPolicy`, `FollowTrafficPolicy`, plus the per-window bound. No characterization tests |
| Reward normalization to a dataset fraction | **done**, 19 October. ADR-0010's precondition for pre-training |
| Experiment record keeping | **done**, 19 October. `scripts/run_experiment.py`; config, seeds and commit recorded with every row |
| Visualization, dashboards, GIS map, figure design system | **done** |
| DQN wiring | **done**, 19 October. `fragalloc/agent/`, `scripts/train.py`, verified end to end on a short run. **Not yet trained to convergence** |
| Real-cluster gate | **passed once, must be re-run.** Run 1 compared one region against two, not six, because of a `RELOCATE LEASE` constraint found during it |
| Real-cluster harness | **not started.** Specified in [`harness-architecture.md`](harness-architecture.md) |
| Paper | **not started.** This is now the largest gap |
| Tabular Q sanity check | **dropped.** The DQN is wired and cheap to run; a reduced-state rehearsal of it no longer buys enough to spend a day on |

## What the midterm rubric asks for, and where each point sits

Fifty points. The honest reading is that roughly forty are already earned by
work that exists, and the ten that are not are the two cheapest categories on
the sheet. That is the whole argument for how this week is spent.

| Rubric item | Points | State |
|---|---|---|
| Core system or simulation framework established and functional | 10 | **Earned.** Simulator, cost model, action space, observation encoder, Gymnasium adapter, 152 tests |
| Baseline integration or data pipeline operating without blocking errors | 5 | **Earned.** Three reference policies plus a bound, driven by one experiment runner, dispatchable from Actions |
| Codebase organization, version control, documentation | 5 | **Earned.** Git since 11 October, twelve ADRs, a README that explains the project to a non-specialist |
| Clear identification of evaluation metrics | 5 | **Earned in the code, not yet in prose.** Mean and p95 latency, GB moved per episode, cross-region transaction fraction, load imbalance. Needs to be stated in the paper |
| Implementation of a classical baseline | 5 | **Earned.** Static hash partitioning is the classical system; follow-traffic is the reactive heuristic |
| Preliminary test datasets or synthetic workload generators active | 5 | **Earned.** The drifting, spiking, Zipf-skewed workload generator with transaction templates |
| Early quantitative results or trace logs | 3 | **One dispatch away.** Press *Run workflow* on **Experiments** and the run record is the evidence |
| Basic analysis, critical thinking on anomalies | 2 | **Partly earned.** [`open-questions.md`](open-questions.md) and the two pilot defects in [`results-log.md`](results-log.md) are exactly this; both need a paragraph in the paper |
| Completed **Introduction** and **Related Work** | 5 | **Not started** |
| Established **System Model / Methodology** | 2 | **Not started**, but [`mdp-specification.md`](mdp-specification.md) is most of it already |
| Placeholders for Evaluation and Conclusion | 0 | Trivial |
| Effective presentation of architecture, methodology, preliminary outcomes | 2 | **Not started** |
| Realistic execution plan and mitigation | 1 | **This document** |

**The conclusion to draw from that table:** the paper and the presentation are
worth ten points and perhaps two days of work. Training the agent to beat the
baseline is worth nothing directly on this rubric. It matters enormously for
the final submission and not at all for this one, so it runs in the background,
on GitHub's machines, whilst the writing happens.

## The seven days

Step by step, with the exact dispatch settings, in
[`midterm-checklist.md`](midterm-checklist.md).

Everything on the cluster and every training run is a button press in the
Actions tab, so the laptop constraint does not bind on any of it. The writing is
the only work that needs a person at a keyboard.

| Day | Press a button | Write |
|---|---|---|
| **Mon 20** | Dispatch **Experiments**: 8 seeds, 200 windows. Dispatch **Cluster pilot**, which re-runs the gate on the fixed script | Paper skeleton, all sections present. Introduction |
| **Tue 21** | Dispatch **Train agent**: 300,000 steps, about half an hour | Related Work, from Lion and GeoTP outwards |
| **Wed 22** | Evaluate the trained agent; if it does not clear the follow-traffic baseline, adjust the migration weight and the exploration schedule and dispatch again | System Model and Methodology, mostly transcribed from `mdp-specification.md` |
| **Thu 23** | Dispatch **Experiments** at volatility 0.5, 1.0 and 2.0 for the sweep | Evaluation section, written around whatever results exist by then |
| **Fri 24** | Collect figures from the artifacts | Finish Evaluation; Conclusion and Limitations as honest placeholders |
| **Sat 25** | — | Slides: architecture, methodology, preliminary outcomes, plan for the remaining 40 percent |
| **Sun 26** | Buffer | Read the whole thing once, out loud, and submit |

## Mitigation, item by item

**If the agent does not beat the follow-traffic baseline by 26 October.** It is
reported as a preliminary negative, with the training curve and the held-out
evaluation, and the submission still clears the 50 to 60 percent milestone the
rubric asks for. Nothing on the rubric requires the agent to win. The failure
mode to avoid is spending the week tuning hyperparameters and arriving with no
paper, which converts a safe thirty-eight points into a risky twenty.

**If the re-run gate fails.** The contribution becomes the simulator result and
the cluster becomes a measured negative finding, exactly as planned in October.
The fallback has not changed and remains publishable.

**If the Actions runner is slow or the job is queued.** Every workflow writes a
complete, self-describing run directory, so a job that finishes at 3 a.m.
unattended is still usable at 9 a.m. Nothing waits on a person watching it.

**If OneDrive or the laptop misbehaves.** The repository is on GitHub, the
results are in Actions artifacts, and neither needs the machine.

**What is deliberately not being done this week.** The real-cluster harness,
fine-tuning on the cluster, characterization tests for the baselines, and the
Lion-style cost-model rebalancer. All four are for the final submission. Listed
here so none of them gets quietly started on Tuesday.

## The gate, originally scheduled 12 October

**Question:** on a six-node cluster under injected wide-area latency, is the
single-region against cross-region transaction latency gap clearly larger than
run-to-run noise?

**How it is answered:** `scripts/falsification_test.py`, with no agent and no
learning, run either locally or by dispatching the **`Cluster pilot`** workflow
from the Actions tab. The workflow route needs no local machine at all and is the
fastest path: it brings up the cluster, proves the latency injection is real,
disables the balancer, runs the test and reports the verdict in the job summary.

The by-hand description below is what the script does. Place a table's
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

## Block 1, kept as a record

Block 1 ran 7 to 19 October and is complete except for the cluster re-run. Its
items, with outcomes:

| Item | Outcome |
|---|---|
| Enterprise Free licence key | Obtained. No payment method, no charge |
| Six nodes under Docker, generated from `DEFAULT_RTT_MS` | Done. `scripts/gen_cluster.py`, `scripts/cluster.sh`, verified in CI by the pilot workflow |
| Verify the five balancer settings individually | Done, each set and read back in the pilot workflow |
| The falsification test | **Passed**, 8 October, then invalidated by a defect found during it. Re-run pending |
| `MOVE_REPLICA` encoding | Done, 19 October. 261 actions, chosen by measurement. [ADR-0002 amendment](adr/ADR-0002-flat-declarative-action-space.md) |
| Replication factor fixed at 3 | Done |
| Migration cost as a dataset fraction | Done, 19 October |
| Tabular Q-learning sanity check | **Dropped.** The DQN is wired and a short run costs minutes; rehearsing it on a reduced state space no longer earns its day |

Two decisions from block 1 that still bind everything downstream. The simulator
runs at **0.356 ms per step**, so pre-training is seconds of environment time
and minutes in total, which is why a GPU buys nothing here and Kaggle was
rejected ([ADR-0011](adr/ADR-0011-where-the-compute-runs.md)). And the region
count fixes the action-space cardinality, so the six-region choice is now
locked: changing it would invalidate every trained weight.

## Not yet built

- `fragalloc/harness/`, the five modules in [`harness-architecture.md`](harness-architecture.md). **Final submission, not this week**
- `scripts/finetune.py`. Depends on the harness
- `docs/validation-plan.md`: topology, injected latencies, workload parameters,
  and the agreement statistic that counts as a pass. **Fix the threshold before
  seeing results**
- Characterization tests for the reference policies, pinning each on a fixed seed
- `tests/test_policies.py`, `tests/test_simulator.py`, `tests/test_observation.py`
  are absent. The coverage gap is real but it is behind the paper in priority
- The Lion-style cost-model rebalancer baseline. The strongest related-work
  comparison, and the first thing to add back once the paper exists
- `paper/`. **Starts Monday 20 October**

## Working in short sessions

The laptop cannot stay on, so the plan assumes it will not.
[ADR-0010](adr/ADR-0010-session-scoped-cluster-and-resumable-runs.md) makes the
cluster disposable and the run checkpointed: `cluster-up`, `resume`, run one or
more episodes, `cluster-down`. An episode is 200 windows, which at 2 to 6 s per
step is **7 to 20 minutes**, so a single episode fits between classes and closing
the laptop costs at most the episode in progress.

Two consequences for the schedule. Fine-tuning does not need an uninterrupted
night, only a sequence of sessions, which is what makes block 4 realistic.
And every run reports how many steps were discarded to suspends, so an
interrupted run is auditable rather than quietly degraded.

## The schedule's honest risk

One day of buffer, which is thin, and it is spent entirely on writing rather
than on compute. That is the right place for it: every compute task this week
is a dispatch that runs unattended on somebody else's machine, and the only
irreducibly serial work is a person writing prose.

The risk is therefore not that a job fails. It is the familiar one of spending
Tuesday and Wednesday tuning a learning rate because the agent is more
interesting than the Related Work section, and arriving on Sunday with a better
agent and no paper. Ten of the fifty points depend on writing and none of them
depend on the agent winning. The schedule above is built to make that trade
hard to get wrong, and this paragraph exists so that the reasoning survives
being tempted.
