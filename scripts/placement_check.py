"""Harness piece 1 on a real cluster: create, read back, move by hand, read back.

Build-order step 3 of docs/harness-architecture.md: "test it by issuing
relocations by hand and confirming the readback". Run once the cluster is up and
the balancer is disabled; the Cluster pilot workflow does both first.

Four moves, each checked against the read-back:

1. move fragment 0's lease to another voter            must apply
2. move one of fragment 1's voters to an empty region   must apply
3. move fragment 2's lease to a region with no voter    must be REFUSED
4. split fragment 0 at its midpoint cell                must apply

Exit 0 only if every read-back matches intent. The raw ``SHOW RANGES`` rows are
printed first, so the key format this release uses is on record.

Usage:
    python scripts/placement_check.py --out results/placement_check.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fragalloc.catalog import FragmentCatalog                        # noqa: E402
from fragalloc.config import FragAllocConfig                         # noqa: E402
from fragalloc.harness.placement import (                            # noqa: E402
    PlacementError, PsycopgSql, compare, create_table, read_back, read_ranges,
    relocate, resolve_stores, TableLayout,
)


def settled(sql, stores, layout, cfg, expected: FragmentCatalog | None = None,
            tries: int = 15, wait: float = 1.0):
    """Read back, retrying whilst leases settle. Returns (catalog, divergences)."""
    observed, found, last_err = None, [], None
    for _ in range(tries):
        try:
            observed = read_back(sql, stores, layout, cfg)
        except PlacementError as exc:      # e.g. a range with no leaseholder yet
            last_err = exc
            time.sleep(wait)
            continue
        found = compare(expected, observed) if expected is not None else []
        if not found:
            return observed, []
        time.sleep(wait)
    if observed is None:
        raise last_err
    return observed, found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=26257)
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

    obs0, _ = settled(sql, stores, layout, cfg)
    print("\nread back:\n" + obs0.summary())
    check("boundaries match the table as split",
          obs0.boundaries.tolist() == initial.boundaries.tolist(),
          f"{obs0.boundaries.tolist()}")

    rf = sorted(set(int(c) for c in obs0.replica_counts))
    report["voters_per_range_cluster"] = rf
    report["replicas_per_fragment_simulator"] = int(cfg.catalog.min_replicas)
    print(f"\nvoters per range on the cluster: {rf}; "
          f"replicas per fragment in the simulator: {cfg.catalog.min_replicas}")
    if rf != [cfg.catalog.min_replicas]:
        print("  WARNING: replication factor differs between cluster and simulator. "
              "The read-back is correct; the two worlds are not yet at parity.")

    ranges = read_ranges(sql, layout)
    expected = obs0.copy()

    # 1. lease to another voter
    r0 = ranges[0]
    to = next(s for s in r0.voter_stores if s != r0.lease_store)
    ok, msg = relocate(sql, f"ALTER RANGE {r0.range_id} RELOCATE LEASE TO {to}")
    check("lease move to a voter applies", ok, msg)
    expected.primary[0] = stores.region_of(to)

    # 2. one voter to an empty region
    r1 = ranges[1]
    donor = next(s for s in r1.voter_stores if s != r1.lease_store)
    dest = next(s for s in stores.store_of_region if s not in r1.voter_stores)
    ok, msg = relocate(sql, f"ALTER RANGE {r1.range_id} RELOCATE VOTERS FROM {donor} TO {dest}")
    check("voter move to an empty region applies", ok, msg)
    expected.replicas[1, stores.region_of(donor)] = False
    expected.replicas[1, stores.region_of(dest)] = True

    # 3. lease to a region with no voter: CockroachDB must refuse
    r2 = ranges[2]
    bare = next(s for s in stores.store_of_region if s not in r2.voter_stores)
    ok, msg = relocate(sql, f"ALTER RANGE {r2.range_id} RELOCATE LEASE TO {bare}")
    check("lease move to a region without a voter is refused", not ok, msg)

    obs1, found = settled(sql, stores, layout, cfg, expected)
    check("read-back matches intent after moves 1 to 3", not found,
          "; ".join(map(str, found)) or "no divergence")

    # 4. split fragment 0 at its midpoint; both halves inherit its placement
    expected.split(0)
    mid = int(expected.boundaries[1])
    sql.query(f"ALTER TABLE {layout.table} SPLIT AT VALUES ({layout.cell_key(mid)})")
    obs2, found = settled(sql, stores, layout, cfg, expected)
    check(f"split at cell {mid} reads back as two fragments with one placement", not found,
          "; ".join(map(str, found)) or f"{obs2.n_fragments} fragments")

    print("\nfinal read-back:\n" + obs2.summary())
    report["passed"] = all(c["passed"] for c in report["checks"])
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(f"\nwrote {args.out}")
    print("VERDICT:", "PASS, the read-back tracks the cluster exactly."
          if report["passed"] else "FAIL, see the checks above.")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
