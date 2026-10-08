"""The falsification test: does placement actually change transaction latency?

This is the gate from docs/roadmap.md, and it is deliberately the cheapest
possible way to kill the project early. No agent, no learning, no reward
function. Just: put the ranges a transaction touches in ONE region, measure.
Spread them across SIX regions, measure. Compare the gap against the noise.

If the gap is not clearly larger than run-to-run variance, there is no reward
signal on a real cluster and no amount of agent engineering creates one. Finding
that out now is a publishable methods result. Finding it out in November is not.

Usage:
    python scripts/falsification_test.py --out results/falsification.json
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from shardmind.config import ShardMindConfig          # noqa: E402
from shardmind.topology import DEFAULT_RTT_MS         # noqa: E402

REGIONS = list(ShardMindConfig().topology.region_names)
GATEWAY_PORT = 26257          # node0's mapped port on the host


# ---------------------------------------------------------------- SQL plumbing

def sql(stmt: str, *, port: int = GATEWAY_PORT, fmt: str = "tsv") -> str:
    """Run one statement through the cockroach CLI against a node container."""
    out = subprocess.run(
        ["docker", "exec", f"crdb-{REGIONS[0]}", "cockroach", "sql", "--insecure",
         f"--format={fmt}", "-e", stmt],
        capture_output=True, text=True, timeout=120,
    )
    if out.returncode != 0:
        raise RuntimeError(f"SQL failed:\n{stmt}\n{out.stderr.strip()}")
    return out.stdout


def connect(port: int):
    import psycopg
    return psycopg.connect(
        host="127.0.0.1", port=port, user="root", dbname="defaultdb",
        autocommit=False, connect_timeout=10,
    )


# ------------------------------------------------------------------- fixtures

def build_table(n_ranges: int, rows_per_range: int) -> list[int]:
    """One table, split into n_ranges ranges at predictable boundaries."""
    sql("DROP TABLE IF EXISTS shardtest;")
    sql("CREATE TABLE shardtest (k INT PRIMARY KEY, v STRING);")
    step = rows_per_range
    points = ", ".join(f"({i * step})" for i in range(1, n_ranges))
    sql(f"ALTER TABLE shardtest SPLIT AT VALUES {points};")
    total = n_ranges * rows_per_range
    sql(f"INSERT INTO shardtest "
        f"SELECT g, repeat('x', 64) FROM generate_series(0, {total - 1}) AS g;")
    print(f"  table built: {n_ranges} ranges x {rows_per_range} rows")
    return [i * step for i in range(n_ranges)]   # one key per range


def range_ids() -> list[int]:
    out = sql("SELECT range_id FROM [SHOW RANGES FROM TABLE shardtest];")
    ids = [int(line) for line in out.strip().splitlines()[1:] if line.strip()]
    if not ids:
        raise RuntimeError("no ranges found; did SPLIT AT succeed?")
    return ids


def place_leases(ids: list[int], stores: list[int]) -> int:
    """Move each range's leaseholder to the given store. Returns failures."""
    failed = 0
    for rid, store in zip(ids, stores):
        try:
            sql(f"ALTER RANGE {rid} RELOCATE LEASE TO {store};")
        except RuntimeError as exc:
            failed += 1
            print(f"    relocate r{rid} -> store {store} FAILED: "
                  f"{str(exc).splitlines()[-1][:90]}")
    return failed


def observed_lease_regions() -> dict[int, str]:
    out = sql("SELECT range_id, lease_holder FROM "
              "[SHOW RANGES FROM TABLE shardtest WITH DETAILS];")
    seen = {}
    for line in out.strip().splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1].strip().isdigit():
            seen[int(parts[0])] = REGIONS[int(parts[1]) - 1]
    return seen


# ---------------------------------------------------------------- measurement

def time_transactions(keys_per_range: list[int], n: int, touch: int) -> list[float]:
    """Time n transactions, each touching `touch` distinct ranges.

    Timed client-side with a monotonic clock, because server-side statement
    statistics aggregate by fingerprint and cannot attribute one transaction to
    one placement.
    """
    rng = random.Random(1234)
    samples: list[float] = []
    with connect(GATEWAY_PORT) as conn:
        cur = conn.cursor()
        for _ in range(n):
            picks = rng.sample(keys_per_range, min(touch, len(keys_per_range)))
            t0 = time.monotonic()
            for k in picks:
                cur.execute("UPDATE shardtest SET v = v WHERE k = %s", (k,))
            conn.commit()
            samples.append((time.monotonic() - t0) * 1000.0)
    return samples


def pct(xs: list[float], p: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def bootstrap_gap(a: list[float], b: list[float], iters: int = 2000) -> tuple[float, float]:
    """95% CI on the difference in p95 between the two placements."""
    rng = random.Random(7)
    diffs = []
    for _ in range(iters):
        ra = [rng.choice(a) for _ in a]
        rb = [rng.choice(b) for _ in b]
        diffs.append(pct(rb, 95) - pct(ra, 95))
    diffs.sort()
    return diffs[int(0.025 * iters)], diffs[int(0.975 * iters)]


# -------------------------------------------------------------------- the test

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ranges", type=int, default=6)
    ap.add_argument("--rows-per-range", type=int, default=2000)
    ap.add_argument("--transactions", type=int, default=200)
    ap.add_argument("--touch", type=int, default=3,
                    help="distinct ranges each transaction writes to")
    ap.add_argument("--out", default="results/falsification.json")
    args = ap.parse_args()

    n_regions = len(REGIONS)
    print(f"regions: {n_regions}  {REGIONS}")
    print(f"simulator says us-east-1 <-> ap-southeast-1 is "
          f"{DEFAULT_RTT_MS[0][4]} ms\n")

    keys = build_table(args.ranges, args.rows_per_range)
    ids = range_ids()
    print(f"  ranges: {ids}\n")

    # --- Case A: every leaseholder in region 0. Transactions commit locally.
    print("case A: all leaseholders co-located in", REGIONS[0])
    fa = place_leases(ids, [1] * len(ids))
    time.sleep(3)
    print("   observed:", sorted(set(observed_lease_regions().values())))
    a = time_transactions(keys, args.transactions, args.touch)

    # --- Case B: leaseholders spread round-robin. Commits span regions.
    print("\ncase B: leaseholders spread across all", n_regions, "regions")
    fb = place_leases(ids, [(i % n_regions) + 1 for i in range(len(ids))])
    time.sleep(3)
    print("   observed:", sorted(set(observed_lease_regions().values())))
    b = time_transactions(keys, args.transactions, args.touch)

    lo, hi = bootstrap_gap(a, b)
    result = {
        "regions": n_regions,
        "transactions_per_case": args.transactions,
        "ranges_touched_per_txn": args.touch,
        "relocate_failures": {"co_located": fa, "spread": fb},
        "co_located": {"p50": pct(a, 50), "p95": pct(a, 95),
                       "mean": statistics.fmean(a), "stdev": statistics.pstdev(a)},
        "spread":     {"p50": pct(b, 50), "p95": pct(b, 95),
                       "mean": statistics.fmean(b), "stdev": statistics.pstdev(b)},
        "p95_gap_ms": pct(b, 95) - pct(a, 95),
        "p95_gap_ci95": [lo, hi],
    }

    print("\n" + "=" * 62)
    print(f"{'':16}{'p50':>10}{'p95':>10}{'stdev':>10}")
    print(f"{'co-located':16}{pct(a,50):>10.1f}{pct(a,95):>10.1f}{statistics.pstdev(a):>10.1f}")
    print(f"{'spread':16}{pct(b,50):>10.1f}{pct(b,95):>10.1f}{statistics.pstdev(b):>10.1f}")
    print(f"\np95 gap: {result['p95_gap_ms']:.1f} ms   95% CI [{lo:.1f}, {hi:.1f}]")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2))
    print(f"wrote {args.out}")

    # The verdict, stated as a pass/fail so CI can act on it.
    if fa or fb:
        print("\nVERDICT: INCONCLUSIVE. Some RELOCATE statements failed, so the "
              "two cases were not the placements they claim to be.")
        return 2
    if lo > 0:
        print("\nVERDICT: PASS. The gap excludes zero, so placement measurably "
              "changes transaction latency. The reward signal exists.")
        return 0
    print("\nVERDICT: FAIL. The confidence interval includes zero. On this "
          "cluster, placement does not measurably change transaction latency.\n"
          "Do NOT proceed to agent work. Either the latency injection is not "
          "working (run scripts/cluster.sh latency), the transactions are not "
          "actually spanning ranges, or the approach does not hold at this "
          "scale. The last of those is a reportable negative result.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
