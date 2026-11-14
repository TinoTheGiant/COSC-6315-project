"""The Lion-style co-location baseline (policies.LionStylePolicy)."""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from fragalloc.actions import ActionKind, ActionSpace
from fragalloc.catalog import FragmentCatalog
from fragalloc.config import FragAllocConfig
from fragalloc.policies import LionStylePolicy, StaticHashPolicy, rollout
from fragalloc.simulator import ClusterSimulator

BASE = FragAllocConfig()
CFG = BASE.evolve(episode=replace(BASE.episode, windows_per_episode=40),
                  workload=replace(BASE.workload, volatility=4.0))


def space():
    return ActionSpace(CFG.catalog.max_fragments, CFG.n_regions)


def catalog():
    return FragmentCatalog(CFG.catalog, CFG.workload.n_cells, CFG.n_regions)


def test_placement_cost_prefers_primary_then_secondary_then_a_copy():
    cat = catalog()
    lion = LionStylePolicy(space(), w_remaster=1.0, w_migrate=5.0)
    freq = np.zeros(cat.n_fragments)
    f = 0
    primary = int(cat.primary[f])
    secondary = int(next(r for r in np.flatnonzero(cat.replicas[f]) if r != primary))
    missing = int(np.flatnonzero(~cat.replicas[f])[0])
    costs = [lion.placement_cost(cat, [f], r, freq) for r in (primary, secondary, missing)]
    assert costs == [0.0, 1.0, 5.0]


def test_clumps_join_fragments_that_transactions_access_together():
    lion = LionStylePolicy(space(), alpha=0.5)
    vertex = np.array([10.0, 8.0, 1.0, 5.0])
    edges = np.zeros((4, 4))
    edges[0, 1] = edges[1, 0] = 6.0       # strong
    edges[0, 2] = edges[2, 0] = 1.0       # below alpha * 6
    assert lion.clumps(vertex, edges) == [[0, 1], [3], [2]]


def test_coaccess_counts_each_template_on_every_fragment_pair():
    cat = catalog()
    c2f = cat.cell_to_fragment()
    a = 0
    b = int(next(c for c in range(CFG.workload.n_cells) if c2f[c] != c2f[a]))
    gen = SimpleNamespace(template_cells=np.array([[a, b]]))
    z = np.zeros((CFG.workload.n_cells, CFG.n_regions))
    window = SimpleNamespace(reads=z, writes=z, txn_counts=np.array([[3.0] + [0.0] * 5]))
    vertex, edges = LionStylePolicy.coaccess(cat, gen, window)
    assert edges[c2f[a], c2f[b]] == edges[c2f[b], c2f[a]] == 3.0
    assert vertex[c2f[a]] == vertex[c2f[b]] == 3.0


def test_overloaded_region_sheds_its_lightest_clump():
    lion = LionStylePolicy(space(), theta=1.2)
    cat = catalog()
    # Every fragment's primary in region 0, so every clump first chooses it.
    cat.primary[:] = 0
    cat.replicas[:, :] = False
    cat.replicas[:, 0] = cat.replicas[:, 1] = cat.replicas[:, 2] = True
    gen = SimpleNamespace(template_cells=np.zeros((1, 2), dtype=int))
    rng = np.random.default_rng(0)
    window = SimpleNamespace(reads=rng.random((CFG.workload.n_cells, CFG.n_regions)),
                             writes=np.zeros((CFG.workload.n_cells, CFG.n_regions)),
                             txn_counts=np.zeros((1, CFG.n_regions)))
    dest = lion.plan(cat, gen, window)
    assert len(set(dest.values())) > 1


class Checked:
    """Records every action and whether it was legal when chosen."""

    def __init__(self, inner):
        self.inner, self.chosen = inner, []

    def reset(self):
        self.inner.reset()

    def act(self, sim):
        a = self.inner.act(sim)
        self.chosen.append((a, bool(sim.action_space.applicable_mask(sim.catalog)[a])))
        return a


def test_rollout_issues_only_legal_moves_and_cuts_cross_region_transactions():
    sim = ClusterSimulator(CFG)
    lion = Checked(LionStylePolicy(space()))
    recs = rollout(sim, lion, seed=2000)
    static = rollout(sim, StaticHashPolicy(space()), seed=2000)
    xr = lambda r: np.mean([x["cross_region_txn_fraction"] for x in r[1:]])  # noqa: E731
    assert xr(recs) < xr(static)
    moves = [a for a, _ in lion.chosen if a != space().noop_index]
    assert moves and all(ok for _, ok in lion.chosen)


def test_with_nothing_to_colocate_every_fragment_stays_on_its_primary():
    """Minimum cost is zero exactly where the primary already is."""
    cat = catalog()
    lion = LionStylePolicy(space(), theta=1e9)
    gen = SimpleNamespace(template_cells=np.zeros((1, 2), dtype=int))
    rng = np.random.default_rng(1)
    window = SimpleNamespace(reads=rng.random((CFG.workload.n_cells, CFG.n_regions)),
                             writes=np.zeros((CFG.workload.n_cells, CFG.n_regions)),
                             txn_counts=np.zeros((1, CFG.n_regions)))
    dest = lion.plan(cat, gen, window)
    assert dest == {f: int(cat.primary[f]) for f in range(cat.n_fragments)}


def test_a_stale_queued_move_is_skipped_not_issued():
    sim = ClusterSimulator(CFG)
    sim.reset(seed=2000)
    sp = space()
    lion = LionStylePolicy(sp, replan_every=1000)
    lion._windows, lion._plan_boundaries = 1, sim.catalog.boundaries.tolist()
    f = 0
    bare = int(np.flatnonzero(~sim.catalog.replicas[f])[0])   # no replica: lease cannot go
    lion._queue = [(int(ActionKind.MOVE_LEASE), f, bare)]
    assert lion.act(sim) == sp.noop_index
