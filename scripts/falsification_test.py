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


def region_to_store() -> dict[str, int]:
    """Map region name -> store id, read from the cluster.

    CockroachDB assigns node ids in join order, which is nondeterministic, so
    `crdb-us-east-1` is NOT reliably node 1. Assuming it silently produces the
    wrong placements and a confident, meaningless result. Resolve it.
    """
    out = sql("SELECT s.store_id, n.locality FROM crdb_internal.kv_store_status s "
              "JOIN crdb_internal.kv_node_status n ON s.node_id = n.node_id;")
    mapping: dict[str, int] = {}
    for line in out.strip().splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        store = int(parts[0])
        # locality renders as "region=us-east-1"
        for kv in parts[1].split(","):
            if kv.strip().startswith("region="):
                mapping[kv.split("=", 1)[1].strip()] = store
    missing = [r for r in REGIONS if r not in mapping]
    if missing:
        raise RuntimeError(
            f"could not resolve a store for {missing}. Found: {mapping}. "
            f"Are all nodes live and did --locality=region=... get set?")
    return mapping


def store_to_region() -> dict[int, str]:
    return {v: k for k, v in region_to_store().items()}


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


def relocate(stmt: str) -> tuple[bool, str]:
    """Run an ALTER RANGE ... RELOCATE and read the RESULT COLUMN.

    This is the trap that made the first pilot run report zero failures whilst
    relocations were failing: the statement reports 'ok' or the error text as a
    column in its own result set, and `cockroach sql -e` exits 0 either way. A
    returncode check alone sees success.
    """
    try:
        out = sql(stmt)
    except RuntimeError as exc:
        return False, str(exc).splitlines()[-1][:120]
    rows = [l for l in out.strip().splitlines()[1:] if l.strip()]
    for line in rows:
        result = line.split("\t")[-1].strip()
        if result.lower() != "ok":
            return False, result[:120]
    return True, "ok"


def voters(rid: int) -> list[int]:
    """Store ids currently holding a voting replica of this range."""
    out = sql("SELECT range_id, voting_replicas FROM "
              "[SHOW RANGES FROM TABLE shardtest WITH DETAILS];")
    for line in out.strip().splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].strip() == str(rid):
            return [int(x) for x in parts[1].strip("{}[] ").split(",") if x.strip()]
    return []


def place(ids: list[int], targets: list[int], *, move_data: bool) -> int:
    """Put each range's leaseholder on its target store. Returns failures.

    `RELOCATE LEASE` can only target a store that ALREADY holds a voting
    replica, which the first pilot run discovered the hard way: with
    replication factor 3 across six nodes, only three of the six are eligible
    per range, so a round-robin lease placement collapsed onto two regions.

    With move_data=True the voter is moved first, which is what actually makes
    the placement what it claims to be.
    """
    failed = 0
    for rid, target in zip(ids, targets):
        if move_data:
            current = voters(rid)
            if target not in current:
                donor = next((v for v in current if v not in targets), None) or current[-1]
                ok, msg = relocate(
                    f"ALTER RANGE {rid} RELOCATE VOTERS FROM {donor} TO {target};")
                if not ok:
                    failed += 1
                    print(f"    r{rid}: move voter {donor} -> {target} FAILED: {msg}")
                    continue
        ok, msg = relocate(f"ALTER RANGE {rid} RELOCATE LEASE TO {target};")
        if not ok:
            failed += 1
            print(f"    r{rid}: move lease -> store {target} FAILED: {msg}")
    return failed


def observed_lease_regions(s2r: dict[int, str]) -> dict[int, str]:
    out = sql("SELECT range_id, lease_holder FROM "
              "[SHOW RANGES FROM TABLE shardtest WITH DETAILS];")
    seen = {}
    for line in out.strip().splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1].strip().isdigit():
            seen[int(parts[0])] = s2r.get(int(parts[1]), f"store{parts[1]}")
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

    r2s = region_to_store()
    s2r = {v: k for k, v in r2s.items()}
    print("  region -> store:", r2s, "\n")

    keys = build_table(args.ranges, args.rows_per_range)
    ids = range_ids()
    print(f"  ranges: {ids}\n")

    # --- Case A: every leaseholder in one region. Transactions commit locally.
    print("case A: all leaseholders co-located in", REGIONS[0])
    fa = place(ids, [r2s[REGIONS[0]]] * len(ids), move_data=True)
    time.sleep(3)
    obs_a = sorted(set(observed_lease_regions(s2r).values()))
    print("   observed:", obs_a)
    if len(obs_a) != 1:
        print("   WARNING: leases did not all land in one region. The two cases "
              "are less distinct than intended, which weakens the test.")
    a = time_transactions(keys, args.transactions, args.touch)

    # --- Case B: leaseholders spread round-robin. Commits span regions.
    print("\ncase B: leaseholders spread across all", n_regions, "regions")
    fb = place(ids, [r2s[REGIONS[i % n_regions]] for i in range(len(ids))],
               move_data=True)
    time.sleep(3)
    obs_b = sorted(set(observed_lease_regions(s2r).values()))
    print("   observed:", obs_b)
    if len(obs_b) < 2:
        print("   WARNING: leases did not spread. Case B is not spread, so any "
              "gap below is not measuring what it claims to.")
    b = time_transactions(keys, args.transactions, args.touch)

    lo, hi = bootstrap_gap(a, b)
    result = {
        "regions": n_regions,
        "transactions_per_case": args.transactions,
        "ranges_touched_per_txn": args.touch,
        "relocate_failures": {"co_located": fa, "spread": fb},
        "observed_regions": {"co_located": obs_a, "spread": obs_b},
        "distinct_regions": {"co_located": len(obs_a), "spread": len(obs_b)},
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
