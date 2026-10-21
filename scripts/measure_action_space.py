"""Reproduce the measurements behind the ADR-0002 amendment.

The amendment cites applicability and reachability figures that chose the
261-action space over two alternatives. Numbers in an ADR that cannot be
re-derived are assertions, so this script regenerates all of them.

    python scripts/measure_action_space.py

Expected output at the default shape (six regions, cap 20 fragments, RF 3):

    A  previous five-kind   401 actions   22.1% applicable
    B  naive (f, from, to)  861 actions   22.9% applicable
    C  destination-only     261 actions   29.2% applicable
    reachability: 0 unreachable pairs of 3600, diameter 5 (vs 3 when both
    ends are named)
"""
from __future__ import annotations

import itertools
import sys
from collections import deque
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fragalloc.catalog import FragmentCatalog          # noqa: E402
from fragalloc.config import FragAllocConfig           # noqa: E402
from fragalloc.topology import DEFAULT_RTT_MS, build_topology  # noqa: E402

RF = 3
SEEDS, STEPS = 5, 240


def setup():
    base = FragAllocConfig()
    cfg = base.evolve(catalog=replace(base.catalog, min_replicas=RF, max_replicas=RF))
    R = len(cfg.topology.region_names)
    return cfg, R, cfg.catalog.max_fragments, cfg.workload.n_cells


def walk(cfg, R, n_cells, rtt, seed):
    """A drifting placement, so applicability is measured over real states."""
    rng = np.random.default_rng(seed)
    cat = FragmentCatalog(cfg.catalog, n_cells, R)
    for _ in range(STEPS):
        yield cat
        f = int(rng.integers(0, cat.n_fragments))
        roll = rng.random()
        if roll < 0.08:
            cat.split(f)
        elif roll < 0.54:
            cat.set_primary(f, int(rng.integers(0, R)))
        else:
            cat.move_replica_to(f, int(rng.integers(0, R)), rtt)


def live_counts(cat, R, F, max_frag):
    """Live actions under each encoding, counted from the catalogue's state."""
    n = cat.n_fragments
    splits = sum(1 for f in range(n) if n < max_frag
                 and int(cat.boundaries[f + 1]) - int(cat.boundaries[f]) >= 2)
    # A: SET_PRIMARY applies except to the incumbent; ENSURE/DROP are dead at
    # fixed RF; MERGE applies except to the last fragment.
    a = n * (R - 1) + 0 + 0 + splits + max(0, n - 1)
    lease_any = sum(1 for f in range(n) for r in range(R) if cat.primary[f] != r)
    lease_held = sum(1 for f in range(n) for r in range(R)
                     if cat.replicas[f, r] and cat.primary[f] != r)
    mv_pairs = sum(1 for f in range(n) for x in range(R) if cat.replicas[f, x]
                   for y in range(R) if x != y and not cat.replicas[f, y])
    mv_dest = sum(1 for f in range(n) for r in range(R) if not cat.replicas[f, r])
    return {
        "A  previous five-kind": (a, 3 * F * R + 2 * F + 1),
        "B  naive (f, from, to)": (lease_any + mv_pairs + splits, F * R + F * R * R + F + 1),
        "C1 destination, loose lease": (lease_any + mv_dest + splits, 2 * F * R + F + 1),
        "C  destination-only": (lease_held + mv_dest + splits, 2 * F * R + F + 1),
    }


def reachability(R, rtt, both_ends: bool):
    states = [(frozenset(s), p) for s in itertools.combinations(range(R), RF) for p in s]

    def succ(st):
        s, p = st
        out = {(s, r) for r in s if r != p}
        if both_ends:
            for a in s:
                for b in range(R):
                    if b not in s:
                        ns = set(s); ns.discard(a); ns.add(b)
                        out.add((frozenset(ns), b if p == a else p))
        else:
            for r in range(R):
                if r not in s:
                    held = [x for x in s if x != p] or list(s)
                    d = max(held, key=lambda x: rtt[x][r])
                    ns = set(s); ns.discard(d); ns.add(r)
                    out.add((frozenset(ns), r if p == d else p))
        return out

    worst, unreachable = 0, 0
    for start in states:
        dist, q = {start: 0}, deque([start])
        while q:
            cur = q.popleft()
            for nxt in succ(cur):
                if nxt not in dist:
                    dist[nxt] = dist[cur] + 1; q.append(nxt)
        unreachable += len(states) - len(dist)
        worst = max(worst, max(dist.values()))
    return unreachable, len(states) ** 2, worst


def main() -> None:
    cfg, R, F, n_cells = setup()
    rtt = build_topology(cfg.topology, cfg.catalog.dataset_bytes).rtt

    rows = []
    for seed in range(SEEDS):
        for cat in walk(cfg, R, n_cells, rtt, seed):
            rows.append(live_counts(cat, R, F, cfg.catalog.max_fragments))

    print(f"applicability over {len(rows)} states, {SEEDS} seeds, RF {RF}, "
          f"{R} regions, cap {F} fragments\n")
    for key in rows[0]:
        fracs = [r[key][0] / r[key][1] for r in rows]
        print(f"  {key:30s} {rows[0][key][1]:4d} actions   "
              f"{np.mean(fracs) * 100:5.1f}% applicable")

    print("\nreachability of the destination-only tie-break")
    for both, name in ((False, "C  destination-only"), (True, "B  both ends named")):
        un, tot, d = reachability(R, DEFAULT_RTT_MS, both)
        print(f"  {name:22s} unreachable {un}/{tot}   diameter {d}")

    print("\nC is chosen: smallest of the live candidates, densest, fully "
          "reachable.\nC1 is denser still but fuses the cheap lease move with "
          "the expensive\nreplica move, which is the cost distinction ADR-0009 "
          "exists to preserve.")


if __name__ == "__main__":
    main()
