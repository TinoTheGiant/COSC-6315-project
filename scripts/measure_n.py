"""Choose N, the transactions timed per step, by measurement (design doc, section 5).

1. Hold placement fixed. Drive a large sample (default 2000) of one window's
   demand through the per-region driver (harness piece 3).
2. Bootstrap the p95 estimate at a range of subsample sizes.
3. Report the smallest N whose p95 standard error is at most one third of the
   smallest effect the paper must detect.

The effect defaults to the static-to-follow gap in the simulator at volatility
4 (150.12 against 129.04 ms, results-log). Re-run with --effect-ms once the
RF 3 baselines exist (ADR-0015). N and its standard error go in the methods
section: they are results, not settings.

Also a pilot of the driver itself: gateways verified per region, retries and
failures counted, and the drive marked suspect if the machine slept.

Usage:
    python scripts/measure_n.py --replicas 3 --out results/measure_n.json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fragalloc.catalog import FragmentCatalog                          # noqa: E402
from fragalloc.config import FragAllocConfig                           # noqa: E402
from fragalloc.harness.cluster import converge_replication             # noqa: E402
from fragalloc.harness.driver import (                                 # noqa: E402
    Driver, choose_n, p95_standard_error, port_connector, sample_requests,
)
from fragalloc.harness.placement import (                              # noqa: E402
    PsycopgSql, TableLayout, create_table, read_back, resolve_stores,
)
from fragalloc.topology import build_topology                          # noqa: E402
from fragalloc.workload import WorkloadGenerator                       # noqa: E402

SIZES = (25, 50, 100, 200, 300, 400, 600, 800, 1000, 1500, 2000)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=26257, help="region 0's SQL port; region i is +i")
    ap.add_argument("--transactions", type=int, default=2000)
    ap.add_argument("--concurrency", type=int, default=2,
                    help="workers per region; fixed across every condition, stated in the paper")
    ap.add_argument("--replicas", type=int, default=None)
    ap.add_argument("--seed", type=int, default=2000, help="workload seed (first held-out seed)")
    ap.add_argument("--effect-ms", type=float, default=21.08,
                    help="smallest p95 effect to detect; target standard error is a third of it")
    ap.add_argument("--iters", type=int, default=2000)
    ap.add_argument("--out", default="results/measure_n.json")
    args = ap.parse_args()

    cfg = FragAllocConfig()
    replicas = args.replicas or cfg.catalog.min_replicas
    if not cfg.catalog.min_replicas <= replicas <= cfg.catalog.max_replicas:
        cfg = cfg.evolve(catalog=replace(cfg.catalog, min_replicas=replicas,
                                         max_replicas=replicas))
    layout = TableLayout.from_config(cfg)
    admin = PsycopgSql.connect(port=args.port)
    stores = resolve_stores(admin, cfg.topology.region_names)
    initial = FragmentCatalog(cfg.catalog, cfg.workload.n_cells, len(stores.region_names))
    create_table(admin, layout, initial.boundaries)
    took = converge_replication(admin, layout, replicas)
    placement = read_back(admin, stores, layout, cfg, lease_source="builtin")
    print(f"table ready, {replicas} voters per range after {took:.0f} s; placement held fixed:")
    print(placement.summary())

    topology = build_topology(cfg.topology, cfg.catalog.dataset_bytes)
    horizon = cfg.episode.warmup_windows + cfg.episode.windows_per_episode + 1
    gen = WorkloadGenerator(cfg.workload, topology, np.random.default_rng(args.seed), horizon)
    window = gen.window(cfg.episode.warmup_windows)
    reqs = sample_requests(window, gen.template_cells, gen.template_is_write,
                           args.transactions, np.random.default_rng(args.seed))

    connect = port_connector(args.port)
    driver = Driver(connect, stores, layout, concurrency=args.concurrency, seed=args.seed)
    print(f"gateways verified: {driver.gateways}")
    try:
        result = driver.drive(reqs)
    finally:
        driver.close()
    summary = result.summary()
    print(json.dumps({k: v for k, v in summary.items() if k != "by_kind"}, indent=1))
    print("by kind:", json.dumps(summary["by_kind"]))

    lat = result.latencies()
    sizes = [n for n in SIZES if n <= len(lat)]
    se = p95_standard_error(lat, sizes, iters=args.iters, seed=args.seed)
    target = args.effect_ms / 3.0
    chosen = choose_n(se, target)
    per_txn_s = result.wall_s / max(1, len(result.samples))
    print(f"\np95 standard error by N (bootstrap, {args.iters} resamples):")
    for n in sizes:
        mark = "  <- chosen" if n == chosen else ""
        print(f"  N={n:>5}  SE {se[n]:7.2f} ms  ~{n * per_txn_s:6.1f} s per step{mark}")
    print(f"target: SE <= {target:.2f} ms (a third of {args.effect_ms} ms)")
    print("chosen N:", chosen if chosen else f"none up to {sizes[-1]}; drive more or accept a "
          "larger detectable effect")

    checks = {
        "no failures": summary["failures"] == 0,
        "machine did not sleep": not summary["suspended"],
        "no stalled requests": summary["stalls"] == 0,
        "N found": chosen is not None,
    }
    for name, ok in checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    report = {"summary": summary, "se_by_n": se, "target_se_ms": target,
              "effect_ms": args.effect_ms, "chosen_n": chosen, "seconds_per_txn": per_txn_s,
              "replicas": replicas, "workload_seed": args.seed,
              "window": int(window.index), "checks": checks,
              "latencies_ms": lat}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=1))
    print(f"wrote {args.out}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
