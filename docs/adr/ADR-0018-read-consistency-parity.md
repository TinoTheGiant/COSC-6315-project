# ADR-0018: Which replica serves a read, in the simulator and on the cluster

**Status:** Accepted, 15 November 2026: `primary_only` (strong reads served by the
leaseholder) for every RF 3 result. The training round, the volatility sweep
and the cluster evaluation of 15 November all pass it explicitly. The code
default is still `nearest_replica`, so any new run must pass
`--read-consistency primary_only`; flipping the default is recorded in
`docs/tech-debt.md`.
**Date:** 2026-11-14
**Deciders:** Tino Kaseke

## Context

`CostConfig.read_consistency` defaults to `nearest_replica`: a read is served by
whichever replica is closest to the client. Every recorded result uses it.

CockroachDB does not do that by default. Its follower-reads page states that a
strong `SELECT` (no `AS OF SYSTEM TIME`) is served "Only From Leaseholder",
except on `GLOBAL` tables. A nearest-replica read on CockroachDB is a follower
read, `AS OF SYSTEM TIME follower_read_timestamp()`, which reads data at least
about 4.2 s old, and which "you cannot use ... in read-write transactions".
(Read directly, docs.cockroachlabs.com/docs/stable/follower-reads, 14 November.)

So the cluster and the simulator disagree about reads, as they disagreed about
the replication factor until ADR-0015. Like that one, it is silent: shapes
match, the model loads, and the agent meets a cost structure it never trained
on. It surfaced while writing the driver (ADR-0017), which has to choose a SQL
form for every read.

**Measured, 14 November**, RF 3, volatility 4, 200 windows, held-out seeds
2000 to 2007, `scripts/run_experiment.py`, commit 2b001f4 plus this change:

| policy | nearest_replica ms | primary_only ms | GB moved |
|---|---|---|---|
| static | 118.81 | 192.11 | 0.0 |
| random | 122.40 | 195.46 | 134.6 |
| follow | 93.50 | 148.81 | 867.7 |
| static minus follow | **25.31** | **43.30** | |

With strong reads, placement matters more in absolute terms (43 ms against
25 ms between the same two policies), because a read can no longer route around
a badly placed lease.

## Decision (proposed)

**Option B: `primary_only` in the simulator, strong reads on the cluster.**
The RF 3 runs have not started, so changing the setting now costs nothing that
ADR-0015 did not already spend. Keep the follower-read path in the driver for
one sensitivity point if time allows.

## Options Considered

### Option A: keep `nearest_replica`; follower reads on the cluster

| Dimension | Assessment |
|-----------|------------|
| Cost | None now; the driver already supports it (`read_mode="follower"`) |
| Fidelity | Partial: reads inside read-write transactions must stay at the leaseholder on CockroachDB, but the simulator lets them use the nearest replica |
| Semantics | Every read is about 4 s stale; a reviewer will ask whether the application tolerates that |
| Effect size | Smaller (25 ms static to follow) |

### Option B: `primary_only` everywhere (proposed)

| Dimension | Assessment |
|-----------|------------|
| Cost | One input on the training workflow (`read_consistency`), already added |
| Fidelity | Exact: CockroachDB's default read path, inside and outside transactions |
| Semantics | Strong reads; nothing to defend |
| Effect size | Larger (43 ms), and every number in the paper changes, which ADR-0015 already accepted |

**Cons:** replicas then matter only for writes (quorum) and load, so
`MOVE_REPLICA_TO` is worth less and the agent may lean on lease moves. That is
a finding about CockroachDB, not a defect.

### Option C: leave the mismatch

Rejected for the reason ADR-0015 rejected its Option C: poor cluster results
could not be told apart from a model trained on the wrong read path.

## Consequences

- Easier: the simulator, the driver and CockroachDB's defaults agree; no stale
  reads to justify.
- Harder: headline numbers all come from the new runs; midterm and 13 November
  results stay as RF 2, nearest-replica context.
- Revisit: if Option B makes replica moves nearly worthless and that weakens
  the story, report Option A as the sensitivity point rather than switching.

## Action Items

1. [x] `--read-consistency` on `train.py` and `run_experiment.py`; workflow
       input `read_consistency` on Train agent, applied to training and to
       evaluation alike.
2. [x] Driver `read_mode` (`leaseholder` or `follower`), `READ_MODES` maps the
       simulator setting to it; pilot input `read_consistency`.
3. [ ] Decide A or B.
4. [ ] Launch the RF 3 runs with the chosen value; record it in results-log.
5. [ ] Use the matching static-to-follow gap as `--effect-ms` when choosing N.
