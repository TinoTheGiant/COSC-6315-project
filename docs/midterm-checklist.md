# Midterm checklist, 20 to 26 October

A step-by-step companion to [`roadmap.md`](roadmap.md). The roadmap says what
the week is for and why. This says which button to press and what to type.

Tick items off here as you go. Nothing in this file is a decision; every
decision behind it is recorded in the roadmap or an ADR.

---

## Before anything else

**1. Push.** Commits are waiting locally.

```
git push
```

Everything below runs from GitHub, so nothing works until the remote has the
code.

---

## Step 1: fire the two runs, then leave them

Both are dispatched from the repository's **Actions** tab. Neither needs your
machine, and neither needs you watching. Do both now so they are finishing
whilst you write.

### 1a. The volatility sweep

This is the run that decides how the paper's central claim is framed, so it
comes first.

> Actions → **Sweep** → *Run workflow*
>
> | Field | Value |
> |---|---|
> | Setting to sweep | `volatility` |
> | Values | `0.5,1.0,2.0,4.0` |
> | Seeds per value | `8` |
> | Windows | `200` |
> | Policies | leave as is |

Roughly two minutes. The job summary gives you the table; the artifact gives
you `sweep.png`, which goes straight into the paper.

**What you are looking for.** At volatility 1.0 the follow-traffic heuristic
sits only 5 ms above the fixed-shard bound, which leaves almost nothing for a
learned policy to win on latency. The question is whether that gap widens as
the workload drifts faster. Read the "Advantage over static hashing" table and
the gap between follow traffic and the bound at each value.

- If the gap **widens** with volatility, the latency story holds at the top of
  the sweep and that is the headline.
- If it stays **flat**, the contribution moves to movement cost: follow traffic
  pays 785 GB per episode, and matching it for a fraction of that is the
  result worth reporting.

Either answer is usable. Neither needs anything rerun.

### 1b. The diagnostic training run

> Actions → **Train agent** → *Run workflow*
>
| Field | Value |
|---|---|
| Timesteps | `300000` |
| Windows | `200` |
| Volatility | `1.0` |
| Reward weight on migration | **`0.0`** |
| Seed | `0` |
| Eval seeds | `8` |

About half an hour. The only change from run 1 is the migration weight.

**What you are looking for.** Run 1's agent moved 53 GB where follow traffic
moved 753. It learned to sit still. With the migration penalty set to zero it
has no reason to, so:

- If the agent now **approaches follow traffic**, the problem was credit
  assignment: an immediate penalty against a delayed benefit. The fix is reward
  shaping or n-step returns, and that is a post-midterm job.
- If it **still sits still**, the problem is exploration instead. The suspect is
  the two-step relocation: reaching a new region needs `MOVE_REPLICA_TO` and
  then `MOVE_LEASE` in consecutive windows, and epsilon-greedy almost never
  produces that pair by chance.

Write down which one it is. That sentence is your Limitations section.

---

## Step 2: the paper skeleton

Do this whilst the jobs run. Create `paper/` with every section present, even
the empty ones, because the rubric awards the structure separately from the
content.

```
paper/
  main.tex          IEEE conference template
  references.bib
  sections/
    01-introduction.tex
    02-related-work.tex
    03-system-model.tex
    04-evaluation.tex       placeholder
    05-conclusion.tex       placeholder
```

The rubric's wording is worth reading literally: **Evaluation and Conclusion are
worth zero points at this stage** and only need to exist as outlines. Do not
spend Monday on them.

---

## Step 3: write, in this order

The order is by points per hour, not by where a section sits in the paper.

### Introduction, Monday

Four paragraphs, no more.

1. What a distributed database does about placement today: fragmentation fixed
   at design time, allocation by a key-dependent function that never observes
   where a request came from.
2. Why that degrades: the geographic centre of a workload moves, on a daily
   cycle and abruptly during localized events, and a placement chosen for one
   is wrong for the other.
3. What this project asks: whether a reinforcement learning agent acting as an
   autonomous administrator can make fragmentation and placement decisions that
   track the workload rather than lag behind it.
4. What is in the paper: a simulator, a real six-region CockroachDB cluster, a
   measured gate, and a set of baselines.

Do not open with a sentence about the modern world or the growth of data.

### Related Work, Tuesday

Lion and GeoTP are the spine. Around them, three groups:

- **Fragmentation and allocation as an optimization problem.** Classical work
  solves it once, offline, with a cost model. Say why a solved-once answer
  degrades under a moving workload.
- **Learned database administration.** Index selection, knob tuning, query
  optimization. Position this work as the same idea applied to placement.
- **Geo-distributed transaction placement.** GeoTP and its neighbors. This is
  where the closest comparison sits.

Close with the gap you are filling: fragmentation and geographic placement
learned **jointly**, for transactional workloads, rather than one at a time.

### System Model and Methodology, Wednesday

Mostly transcription. [`mdp-specification.md`](mdp-specification.md) already
contains the state, action and reward definitions, and
[`ADR-0002`](adr/ADR-0002-flat-declarative-action-space.md) contains the action
space with the measurements that chose it.

What must be added rather than copied:

- The evaluation metrics, named explicitly: mean latency, p95 latency, GB moved
  per episode, cross-region transaction fraction, load imbalance. The rubric
  awards five points for this alone and it is currently only in the code.
- The baselines, named and justified: static hash (what production does today),
  random (a control proving gain comes from choosing where, not from moving),
  follow traffic (the reactive heuristic), and the fixed-shard per-window bound.
- The workload generator: 256 cells, Zipf-skewed popularity, angular drift over
  a 96-window diurnal period, localized Poisson spikes, transaction templates.

### Evaluation, Thursday and Friday

Write it around the results that exist by then, which is more than it sounds.

| Figure or table | Where it comes from |
|---|---|
| Baseline comparison, 8 seeds | Experiments run of 20 October |
| Volatility sweep, two panels | Step 1a |
| Cluster gate, co-located against spread | Cluster pilot #2 |
| Agent training curve and held-out evaluation | Train agent runs |

Three things must appear and are easy to leave out:

1. **The 5 ms headroom.** Follow traffic sits 5.00 ms above the bound at
   volatility 1.0, 5.1% of its own mean, with overlapping intervals. A reviewer
   computing that from your first table will find it in seconds. State it, then
   state where room remains.
2. **What "co-located" means on the cluster.** Replication factor 3 with one
   node per region means replicas always span three regions, so every write
   pays a cross-region quorum even when every lease is in us-east-1. That is why
   the co-located p50 is 272.7 ms and not single digits. The experiment isolates
   the leaseholder effect, which is exactly what `MOVE_LEASE` corresponds to.
3. **The confidence interval on the cluster gap is not a precision claim.** At
   N = 200 transactions the p95 is the 190th order statistic, so the bootstrap
   interval is degenerate at the top. Report the gap, report N, and say the
   interval is indicative.

### Conclusion and Limitations, Friday

Outlines only. The limitations worth listing now: no fine-tuning on the cluster
yet, N not chosen by measurement, two cores for six nodes, and the agent not
yet competitive with the reactive heuristic.

### Slides, Saturday

Ten to twelve. Architecture, the MDP, the baselines, the three result figures,
the gate, what remains. The rubric asks for "architecture, methodology and
preliminary outcomes" plus a realistic plan, and the roadmap's rubric table is
the last slide almost verbatim.

---

## Step 4: Sunday

Read the whole thing once, out loud. Check every number against the run
directory it came from, since every one of them is traceable to a `manifest.json`
by design. Submit.

---

## Things not to do this week

Listed because each is tempting and each costs a day.

- **Tuning the agent.** It is worth zero points on this rubric. One diagnostic
  run, which is step 1b, then leave it.
- **Building the cluster harness.** Final submission.
- **Re-running anything that already finished green.** The numbers are recorded
  and reproducible.
- **Making the repository public for a 4-core runner.** It is a real improvement
  and it is a decision about visibility, not about this week. Decide it before
  the final measurements instead.

---

## If something is on fire

| Symptom | What to do |
|---|---|
| A workflow fails | Open the failing step's log. Every workflow runs the test suite first, so a red test suite means the code, and anything later means the job |
| A number looks wrong | Find its run directory. `manifest.json` holds the commit, the config and the seeds, and `report.md` holds the command that reproduces it |
| Two runs disagree | Compare their config digests. Same digest means the same environment and the difference is seeds |
| You are behind | Cut the volatility sweep before you cut the Related Work section. The writing is worth ten points and the sweep is worth none directly |
