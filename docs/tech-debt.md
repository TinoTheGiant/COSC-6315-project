# Technical debt audit

Taken 7 October 2026, at day 27 of 57, against the question that matters now:
**what could cost days in the remaining 30?** Debt that will not bite before
6 November is recorded and deliberately not scheduled.

Scored `(Impact + Risk) x (6 - Effort)`, each 1 to 5. Impact is how much it slows
the work; risk is what happens if it is left; effort is inverted, so cheap fixes
rank higher.

| # | Item | I | R | E | Score | Status |
|---|---|---|---|---|---|---|
| 1 | No version control, and no off-machine copy | 3 | 5 | 1 | **40** | repo created today; backup still missing |
| 2 | Reward scale differs between simulator and cluster | 4 | 5 | 2 | **36** | open, blocks pre-training |
| 3 | RTT matrix is synthetic, and the code says so | 3 | 5 | 2 | **32** | open |
| 4 | Dependencies unpinned | 2 | 4 | 1 | **30** | open |
| 5 | Action space needs reshaping for the cluster | 4 | 4 | 3 | **24** | open, owned by ADR-0009 |
| 6 | Baselines have no tests | 2 | 4 | 3 | **18** | open |
| 7 | Four-deep ADR chain with two reversals | 1 | 2 | 1 | **15** | mitigated |
| 8 | 1,773 lines of untested scripts | 2 | 3 | 4 | **10** | accepted, not scheduled |

---

## 1. No version control, and no off-machine copy — score 40

**Found:** 5,579 lines of Python, eight weeks of work, ten ADRs, and
`git log` returned "not a git repository". A `.gitignore` was present and
carefully written, which means version control was intended and never
initialized.

**Fixed today.** `git init`, 65 files committed, `git fsck` clean.

**What remains, and it is the part that actually matters.** The repository lives
inside a OneDrive folder. OneDrive is a **sync, not a backup**: a corrupted file
syncs the corruption, a deletion syncs the deletion, and there is no history to
recover from. Worse, OneDrive syncing `.git/objects` while git is writing is a
known cause of repository corruption.

Two actions, in order of value:

1. **Push to a private GitHub repository.** This is the only real off-machine
   copy, it is free, and the account already exists. Fifteen minutes.
2. **Stop OneDrive syncing `.git`**, or move the project out of OneDrive
   entirely. The second is cleaner.

Until step 1 is done, a single disk failure or a mis-synced folder ends the
project 30 days before submission. Nothing else on this list comes close.

**Note on this environment:** git cannot delete its own lock files in the synced
folder without an explicit permission grant, so a commit can leave `.git/*.lock`
behind and the next command fails with "File exists". Today's leftovers were
cleared. If it recurs, delete `.git/*.lock` and `.git/objects/tmp_obj_*`.

## 2. Reward scale differs between simulator and cluster — score 36

**Found:** `CatalogConfig.dataset_bytes` is `6.0e10`, 60 GB. The cluster will
hold one or two gigabytes, because it has to fit on a laptop alongside other
coursework.

**Why it bites:** the reward is negative latency **minus migration cost**. With
migration cost in bytes, the two terms sit on completely different scales in the
two environments, so every pre-trained Q-value is wrong by a constant factor that
fine-tuning has to unlearn before it can learn anything. That is precisely the
failure [ADR-0009](adr/ADR-0009-cockroachdb-for-sim-to-real-parity.md) chose
CockroachDB to avoid, reintroduced through a config constant.

**Fix:** express migration cost as a fraction of total dataset size in both
environments, making that reward term unit-free.

**Deadline: before pre-training starts.** Every pre-trained weight depends on the
reward definition, so fixing this afterwards means discarding the pre-training.
Owned by [ADR-0010](adr/ADR-0010-session-scoped-cluster-and-resumable-runs.md)
Action Item 4.

## 3. The RTT matrix is synthetic, and the code says so — score 32

**Found:** `topology.py` carries its own warning:

> `TODO(paper): before any reported result, replace this table with a measured
> matrix from a citable source ... and record the collection date.`

Every latency number produced so far rests on a table the author marked as not
drawn from any published dataset. A reviewer who reads the source finds this
before they read the results.

**The good news: the cluster resolves it almost for free.** Toxiproxy *sets* the
inter-region latency, so on the cluster the RTT matrix stops being an estimate of
the world and becomes the experiment's own definition, exact by construction. The
simulator's table must then be set to mirror the Toxiproxy configuration exactly,
and a test should assert the two agree.

**What still needs a source** is the choice of values. Cite a public latency
dataset for the figures used, record the date, and say in the methods section
that the cluster was configured to match it. That converts the project's weakest
documented assumption into a stated experimental parameter.

**Deadline:** before the results section. Realistically block 1, since the
Toxiproxy configuration has to be written then anyway.

## 4. Dependencies unpinned — score 30

**Found:** nine `>=` constraints and no lockfile. `stable-baselines3>=2.3` and
`torch>=2.2` can resolve to anything.

**Why it bites a paper specifically:** reproducibility is a claim the submission
makes. A reviewer who installs from `requirements.txt` in 2027 gets different
versions and possibly different numbers. It also bites locally: a reinstall
mid-project can change DQN behaviour with no change to the project's own code,
and that failure is very hard to diagnose under time pressure.

**Fix:** `pip freeze > requirements.lock.txt` once the environment is working,
commit it, and keep `requirements.txt` as the human-readable set. Ten minutes.
Record the Python version too.

## 5. Action space needs reshaping for the cluster — score 24

**Found:** 401 actions as `3 x 20 x 6 + 2 x 20 + 1`, with
[ADR-0002](adr/ADR-0002-flat-declarative-action-space.md) recording 54 percent
applicability and `DROP_REPLICA` entirely dead at `min_replicas`.

Under [ADR-0009](adr/ADR-0009-cockroachdb-for-sim-to-real-parity.md) the space
changes shape anyway. The naive `MOVE_REPLICA(f, from, to)` encoding is 720
actions, worse than what it replaces. Working proposal is destination-only with a
documented source tie-break, giving 261.

**Why it is debt rather than just work:** the action space fixes the network's
output layer, so it must be settled before pre-training, not discovered during
it. Owned by ADR-0009 Action Item 2, scheduled for block 1.

## 6. Baselines have no tests — score 18

**Found:** `policies.py` holds `StaticHashPolicy`, `RandomPolicy` and
`FollowTrafficPolicy`. There is no `tests/test_policies.py`. Also absent:
`test_simulator.py` and `test_observation.py`.

**Why the baselines specifically:** the headline claim is a *comparison*. "The
agent beats static hashing by 40 percent" is only true if static hashing is
implemented correctly. A silently wrong baseline does not announce itself; it
produces a plausible number that makes the paper's central claim wrong. Of the
untested modules, this is the one whose failure is invisible.

**Fix:** a characterization test per policy, pinning its behaviour on a fixed
seed. Not property tests, not exhaustive: just a record of what each produces now
so a later refactor cannot silently change it. Half a day for all three.

## 7. Four-deep ADR chain with two reversals — score 15

**Found:** the database decision runs 0007 (CockroachDB, two factual errors) to
0008 (Citus, twenty-one-system screen) to 0009 (back to CockroachDB) to 0010
(session-scoped). A reader landing on 0007 first gets a superseded answer built
on a false premise.

**Already mitigated:** 0007 and 0008 carry prominent superseded headers, 0007
carries an explicit correction notice, and `README.md` directs readers to 0009.

**Residual risk** is a reader who finds a file directly rather than through the
index. Accepted. The chain is also, honestly, a decent record of how a decision
was reached and corrected, which is worth more than a tidy single ADR that hides
the reasoning.

## 8. 1,773 lines of untested scripts — score 10

**Found:** seven scripts, including a 577-line live dashboard and a 414-line
analysis dashboard, with no tests.

**Why it is not scheduled:** scripts are run by eye, and a broken figure is
visible the moment it renders. The failure mode is a wasted afternoon, not a
wrong result. The one risk that *would* have been serious, figures that look fine
on screen and fail in print, is now covered by `test_viz_print_safety.py`.

**Accepted for this project.** Revisit only if a script starts producing numbers
rather than pictures.

---

## Phased plan

Mapped onto [`roadmap.md`](roadmap.md), so none of this competes with the
critical path.

| When | Items | Cost |
|---|---|---|
| **Today, before anything else** | 1: push to private GitHub, stop OneDrive syncing `.git` | 15 min |
| **Block 1, 07–12 Oct** | 2: reward normalization. 5: action space. 3: RTT matrix set from the Toxiproxy config | ~1.5 days, already on the roadmap |
| **Block 1, while containers download** | 4: pin dependencies | 10 min |
| **Block 2, 13–19 Oct** | 6: characterization tests for the three baselines | half a day |
| **Not scheduled** | 7, 8 | accepted |

Items 2, 3 and 5 are already roadmap work; they appear here because each is also
a correctness risk, not merely a task. Items 1 and 4 are the pure debt, and
together they cost under half an hour.

## The one-line version

**Push the repository to GitHub today.** Everything else on this list is
recoverable.
