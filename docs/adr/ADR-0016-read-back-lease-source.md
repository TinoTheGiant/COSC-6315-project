# ADR-0016: How the harness reads each range's leaseholder

**Status:** Accepted, 14 November 2026: the built-in (Option B), on the evidence of Cluster pilot #5
**Date:** 2026-11-14
**Deciders:** Tino Kaseke

## Context

The harness reads placement back after every action (step 4 of the step
protocol). The leaseholder is the expensive part. In CockroachDB's current
documentation, `SHOW RANGES` returns `lease_holder` only `WITH DETAILS`, which
the docs warn "incurs a large computational overhead because it needs to fetch
data across nodes".

Cluster pilot #4 measured it: a median of 5.397 s per read-back, and 16.10 s
per executor step (each step reads at least twice), rising as the table split.
The design budget is 2 to 6 s per step. At 16 s, a 200-window episode spends
almost an hour on placement alone, before any transaction is timed.

## Decision

Make the lease source selectable (`read_ranges(..., lease_source=...)`,
`Executor(..., lease_source=...)`), keep the documented source as the library
default, and let Cluster pilot #5 decide on evidence:

- the check times both sources over five reads each on the same placement;
- it fails unless both read **identical** placements;
- its executor walk uses the built-in, so the step time it reports is the step
  time the agent would see.

If the built-in agrees and is fast, the default switches to it in a one-line
change recorded here. If it disagrees, it is not used.

## Options Considered

### Option A: `WITH DETAILS` (documented)

| Dimension | Assessment |
|-----------|------------|
| Complexity | None: current code |
| Cost | 5.4 s per read, measured |
| Correctness | Documented column |
| Risk | Blows the step budget by a factor of three |

### Option B: `crdb_internal.lease_holder(raw_start_key)` per range

| Dimension | Assessment |
|-----------|------------|
| Complexity | Low: one query, `SHOW RANGES ... WITH KEYS` plus a built-in |
| Cost | One lease-info request per range; unmeasured until pilot #5 |
| Correctness | Undocumented, but present in v25.3 (`pkg/sql/sem/builtins/builtins.go`, read directly): returns `resp.Lease.Replica.StoreID` |
| Risk | Undocumented behaviour can change between releases; requests may run one per range in sequence, each a wide-area round trip |

The first range's start key may lie before the table. The built-in asks for the
lease of the range *containing* that key, which is still this table's first
range, so the answer is still correct.

### Option C: verify only the ranges an action touched

| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium: cache placement, read one or two leases per step, full audit per episode |
| Cost | Lowest |
| Correctness | Drift on untouched ranges goes unseen until the next audit |
| Risk | Weakens the guarantee that the cluster is the authority every step |

## Trade-off Analysis

A is correct but too slow to use. B keeps a full read every step at, possibly,
a fraction of the cost, but rests on an undocumented function, so it is only
acceptable with a check that it agrees with A on a real cluster. C is the
fallback if B is still too slow: it trades drift detection for speed, and the
rebalancer is off, so drift should be rare, but "should be rare" is exactly
what the design says not to assume.

## Consequences

- Easier: whichever source wins, every read is checked against the other once
  per pilot, so a release that changes the built-in fails loudly.
- Harder: one more code path to keep tested; both are covered in
  `tests/test_harness_placement.py` and `tests/test_harness_executor.py`.
- Revisit: if pilot #5 shows the built-in above about 1 s per read, adopt C.

## Action Items

1. [x] Selectable lease source, tests for both.
2. [x] `placement_check.py` times both and requires agreement.
3. [x] Cluster pilot #5; timings in results-log.md (Run 5).
4. [x] Default switched to the built-in in `placement.py` and `executor.py`.

## Outcome (Cluster pilot #5, five runs, 14 November 2026)

| run | DETAILS, median s | built-in, median s | same placement |
|---|---|---|---|
| 43672955396 | 8.094 | 1.221 | identical |
| 43673069841 | 8.498 | 1.415 | identical |
| 43673170009 | 8.361 | 1.165 | identical |
| 43673237944 | 6.249 | 0.870 | identical |
| 43673292953 | 5.827 | 0.869 | identical |

The built-in is about seven times faster and read the same placement as the
documented source in every run. With it, an executor step took a median of
2.22 to 3.58 s (maximum 5.56 s), inside the 2 to 6 s budget. The built-in is
at or just above the 1 s line this ADR set for adopting Option C in three of
five runs; the step budget is met regardless, so C is not adopted. The pilot
keeps comparing the two sources on every run, so a release that changes the
built-in still fails loudly.
