"""Harness pieces 1 and 2 on a real cluster: read-back, hand moves, executor walk.

Build-order steps 3 and 5 of docs/harness-architecture.md. Run once the cluster
is up and the balancer is disabled; the Cluster pilot workflow does both first.

Part 1, the read-back, by hand (four moves, each checked against the read-back):

1. move fragment 0's lease to another voter            must apply
2. move one of fragment 1's voters to an empty region   must apply
3. move fragment 2's lease to a region with no voter    must be REFUSED
4. split fragment 0 at its midpoint cell                must apply

Part 2, the executor: a seeded random walk of legal agent actions, with the
simulator's own catalogue stepped alongside. Every step must apply and the
cluster must match the simulator's catalogue afterwards.

Also timed, because ``SHOW RANGES ... WITH DETAILS`` is documented as costly:
the read-back alone, and a whole executor step. Both bound the step budget.

Exit 0 only if every check passes. The raw ``SHOW RANGES`` rows are printed
first, so the key format this release uses is on record.

Usage:
    python scripts/placement_check.py --out results/placement_check.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fragalloc.actions import ActionSpace                            # noqa: E402
from fragalloc.catalog import FragmentCatalog                        # noqa: E402
from fragalloc.config import FragAllocConfig                         # noqa: E402
from fragalloc.harness.executor import APPLIED, Executor             # noqa: E402
from fragalloc.harness.placement import (                            # noqa: E402
    PsycopgSql, TableLayout, create_table, read_back, read_ranges, relocate,
    resolve_stores, settle,
)
from fragalloc.topology import build_topology                        # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=26257)
    ap.add_argument("--walk-steps", type=int, default=15)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="results/placement_check.json")
    args = ap.parse_args()

    cfg = FragAllocConfig()
    layout = TableLayout.from_config(cfg)
    sql = PsycopgSql.connect(port=args.port)
    report: dict = {"checks": []}

    def check(name: str, passed: bool, detail: str) -> None:
        report["checks"].append({"check": name, "passed": passed, "detail": detail})
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {detail}")

    stores = resolve_stores(sql, cfg.topology.region_names)
    report["stores"] = dict(zip(stores.region_names, stores.store_of_region))
    print("region -> store:", report["stores"])

    initial = FragmentCatalog(cfg.catalog, cfg.workload.n_cells, len(stores.region_names))
    create_table(sql, layout, initial.boundaries)
    print(f"table {layout.table}: {layout.n_cells} cells x {layout.rows_per_cell} rows, "
          f"split at cells {initial.boundaries.tolist()}")

    raw = sql.query(f"SELECT start_key, range_id, lease_holder, voting_replicas "
                    f"FROM [SHOW RANGES FROM TABLE {layout.table} WITH DETAILS]")
    report["raw_rows"] = [[str(c) for c in row] for row in raw]
    print("\nraw SHOW RANGES rows (key format on record):")
    for row in raw:
        print("   ", row)

    # ------------------------------------------------- part 1: read-back
    print("\npart 1: read-back against hand-issued moves")
    obs0, _ = settle(sql, stores, layout, cfg)
    print(obs0.summary())
    check("boundaries match the table as split",
          obs0.boundaries.tolist() == initial.boundaries.tolist(),
          f"{obs0.boundaries.tolist()}")

    rf = sorted(set(int(c) for c in obs0.replica_counts))
    report["voters_per_range_cluster"] = rf
    report["replicas_per_fragment_simulator"] = int(cfg.catalog.min_replicas)
    print(f"voters per range on the cluster: {rf}; "
          f"replicas per fragment in the simulator: {cfg.catalog.min_replicas}")
    if rf != [cfg.catalog.min_replicas]:
        print("  WARNING: replication factor differs between cluster and simulator "
              "(ADR-0015). The read-back is correct; the two worlds are not yet at parity.")

    ranges = read_ranges(sql, layout)
    expected = obs0.copy()

    r0 = ranges[0]
    to = next(s for s in r0.voter_stores if s != r0.lease_store)
    ok, msg = relocate(sql, f"ALTER RANGE {r0.range_id} RELOCATE LEASE TO {to}")
    check("lease move to a voter applies", ok, msg)
    expected.primary[0] = stores.region_of(to)

    r1 = ranges[1]
    donor = next(s for s in r1.voter_stores if s != r1.lease_store)
    dest = next(s for s in stores.store_of_region if s not in r1.voter_stores)
    ok, msg = relocate(sql, f"ALTER RANGE {r1.range_id} RELOCATE VOTERS FROM {donor} TO {dest}")
    check("voter move to an empty region applies", ok, msg)
    expected.replicas[1, stores.region_of(donor)] = False
    expected.replicas[1, stores.region_of(dest)] = True

    r2 = ranges[2]
    bare = next(s for s in stores.store_of_region if s not in r2.voter_stores)
    ok, msg = relocate(sql, f"ALTER RANGE {r2.range_id} RELOCATE LEASE TO {bare}")
    check("lease move to a region without a voter is refused", not ok, msg)

    _, found = settle(sql, stores, layout, cfg, expected)
    check("read-back matches intent after moves 1 to 3", not found,
          "; ".join(map(str, found)) or "no divergence")

    expected.split(0)
    mid = int(expected.boundaries[1])
    sql.query(f"ALTER TABLE {layout.table} SPLIT AT VALUES ({layout.cell_key(mid)})")
    current, found = settle(sql, stores, layout, cfg, expected)
    check(f"split at cell {mid} reads back as two fragments with one placement", not found,
          "; ".join(map(str, found)) or f"{current.n_fragments} fragments")

    timings = []
    for _ in range(5):
        t0 = time.monotonic()
        read_back(sql, stores, layout, cfg)
        timings.append(time.monotonic() - t0)
    report["read_back_seconds"] = {"median": statistics.median(timings), "max": max(timings)}
    print(f"read-back time: median {statistics.median(timings):.3f} s, "
          f"max {max(timings):.3f} s over 5 reads")

    # ------------------------------------------------- part 2: executor walk
    print(f"\npart 2: executor, {args.walk_steps} random legal actions, seed {args.seed}")
    ex = Executor(sql, stores, layout, cfg)
    space = ActionSpace(cfg.catalog.max_fragments, cfg.n_regions)
    rtt = build_topology(cfg.topology, cfg.catalog.dataset_bytes).rtt
    rng = np.random.default_rng(args.seed)
    sim = current.copy()
    outcomes: Counter = Counter()
    step_times, mismatches = [], []
    for i in range(args.walk_steps):
        legal = np.flatnonzero(space.applicable_mask(sim))
        legal = legal[legal != space.noop_index]
        index = int(rng.choice(legal))
        space.apply(sim, index, rtt)
        out = ex.step(current, index)
        outcomes[out.outcome] += 1
        step_times.append(out.elapsed_s)
        agrees = (out.catalog.boundaries.tolist() == sim.boundaries.tolist()
                  and np.array_equal(out.catalog.primary, sim.primary)
                  and np.array_equal(out.catalog.replicas, sim.replicas))
        print(f"  {i:>2} {space.describe(index):<28} {out.outcome:<9} "
              f"{out.elapsed_s:6.2f} s  {'ok' if agrees and not out.diverged else 'MISMATCH'}"
              + ("" if out.outcome == APPLIED else f"  ({out.detail})"))
        if not agrees or out.diverged:
            mismatches.append({"step": i, "action": space.describe(index),
                               "outcome": out.outcome, "detail": out.detail,
                               "divergences": [str(d) for d in out.divergences]})
        current = out.catalog
        sim = current.copy()          # carry on from what the cluster holds
    report["walk"] = {"outcomes": dict(outcomes), "mismatches": mismatches,
                      "step_seconds": {"median": statistics.median(step_times),
                                       "max": max(step_times)}}
    check("every walk step applied", outcomes.get(APPLIED, 0) == args.walk_steps,
          dict(outcomes).__repr__())
    check("cluster matched the simulator's catalogue after every step", not mismatches,
          f"{len(mismatches)} mismatches" if mismatches else "all steps agree")
    print(f"executor step time: median {statistics.median(step_times):.2f} s, "
          f"max {max(step_times):.2f} s")

    print("\nfinal read-back:\n" + current.summary())
    report["passed"] = all(c["passed"] for c in report["checks"])
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(f"\nwrote {args.out}")
    print("VERDICT:", "PASS, read-back and executor track the cluster exactly."
          if report["passed"] else "FAIL, see the checks above.")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
