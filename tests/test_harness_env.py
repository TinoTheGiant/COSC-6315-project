"""Harness piece 4: the cluster environment, against the fake cluster and gateways.

The claim under test is interchangeability: the same spaces, the same workload,
the same reward function and the same encoder as the simulator environment.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from fake_cluster import FakeCluster
from fragalloc.catalog import FragmentCatalog
from fragalloc.config import FragAllocConfig
from fragalloc.env import FragAllocEnv
from fragalloc.harness.driver import READ, TXN, WRITE, Request
from fragalloc.harness.env import ClusterFragAllocEnv, account, serving_regions
from fragalloc.harness.executor import APPLIED, NO_OP
from fragalloc.harness.placement import StoreMap, TableLayout
from fragalloc.reward import reward
from fragalloc.simulator import ClusterSimulator

BASE = FragAllocConfig()
CFG = BASE.evolve(episode=replace(BASE.episode, windows_per_episode=3))
NAMES = CFG.topology.region_names
LAYOUT = TableLayout.from_config(CFG)
STORES = StoreMap(NAMES, (4, 1, 6, 2, 5, 3))


class Gateway:
    def __init__(self, node):
        self.node = node

    def query(self, stmt, params=()):
        return [(self.node,)] if stmt == "SHOW node_id" else []

    def close(self):
        pass


def shifted_cluster() -> FakeCluster:
    """The initial catalogue's boundaries, every replica set rotated one region."""
    cat = FragmentCatalog(CFG.catalog, CFG.workload.n_cells, len(NAMES))
    cat.replicas = np.roll(cat.replicas, 1, axis=1)
    cat.primary = (cat.primary + 1) % len(NAMES)
    return FakeCluster.from_catalog(cat, STORES, LAYOUT)


def make_env(cfg=CFG, cluster=None):
    c = cluster or shifted_cluster()
    env = ClusterFragAllocEnv(cfg, c, STORES, lambda r: Gateway(STORES.store_of_region[r]),
                              n_transactions=40, rebuild_table=False,
                              executor_kwargs={"sleep": lambda _: None})
    return env, c


def test_spaces_match_the_simulator_environment():
    env, _ = make_env()
    sim = FragAllocEnv(CFG)
    assert env.observation_space == sim.observation_space
    assert env.action_space == sim.action_space


def test_reset_places_the_simulators_initial_catalogue():
    env, _ = make_env()
    obs, info = env.reset(seed=2000)
    sim = ClusterSimulator(CFG)
    sim.reset(seed=2000)
    assert env.catalog.boundaries.tolist() == sim.catalog.boundaries.tolist()
    assert np.array_equal(env.catalog.primary, sim.catalog.primary)
    assert np.array_equal(env.catalog.replicas, sim.catalog.replicas)
    assert obs.dtype == np.float32 and obs.shape == env.observation_space.shape
    assert env.observation_space.contains(obs)
    assert info["drive"]["n"] == 40


def test_the_workload_is_the_simulators_for_the_same_seed():
    env, _ = make_env()
    env.reset(seed=2003)
    sim = ClusterSimulator(CFG)
    sim.reset(seed=2003)
    for t in (sim.window_index, sim.window_index + 2):
        a, b = env.generator.window(t), sim.generator.window(t)
        np.testing.assert_array_equal(a.reads, b.reads)
        np.testing.assert_array_equal(a.txn_counts, b.txn_counts)


def test_steps_run_the_executor_and_truncate_with_the_simulator():
    env, cluster = make_env()
    env.reset(seed=2000)
    noop = env.space.noop_index
    _, r, term, trunc, info = env.step(noop)
    assert info["outcome"] == NO_OP and not term and not trunc
    assert r == pytest.approx(reward(CFG, mean_latency_ms=info["mean_latency_ms"],
                                     bytes_moved=0.0, load_imbalance=info["load_imbalance"],
                                     applied=False, is_noop=True))
    legal = np.flatnonzero(env.action_masks())
    move = int(next(a for a in legal if a != noop))
    _, r2, _, trunc, info = env.step(move)
    assert info["outcome"] == APPLIED and info["divergences"] == []
    assert any(s.startswith(("ALTER RANGE", "ALTER TABLE")) for s in info["statements"])
    _, _, _, trunc, _ = env.step(noop)
    assert trunc                                     # windows_per_episode = 3


def test_a_refused_action_is_charged_like_an_inapplicable_one():
    env, cluster = make_env()
    env.reset(seed=2000)
    legal = np.flatnonzero(env.action_masks())
    move = int(next(a for a in legal if a != env.space.noop_index
                    and env.space.decode(int(a)).kind.name == "MOVE_LEASE"))
    cluster.refuse_next = "range already being rebalanced"
    _, r, _, _, info = env.step(move)
    assert info["outcome"] == "rejected" and info["bytes_moved"] == 0.0
    assert r == pytest.approx(reward(CFG, mean_latency_ms=info["mean_latency_ms"],
                                     bytes_moved=0.0, load_imbalance=info["load_imbalance"],
                                     applied=False, is_noop=False))


def test_a_masked_model_loads_and_acts_on_the_cluster(tmp_path):
    """DQN.load parity: weights saved from the simulator run here unchanged."""
    from fragalloc.agent.masked_dqn import MaskedDQN
    sim = FragAllocEnv(CFG)
    model = MaskedDQN("MlpPolicy", sim, learning_starts=1, buffer_size=100, verbose=0)
    model.save(tmp_path / "m.zip")
    env, _ = make_env()
    obs, _ = env.reset(seed=2000)
    loaded = MaskedDQN.load(tmp_path / "m.zip", env=None)
    action, _ = loaded.predict(obs, deterministic=True)
    assert 0 <= int(action) < env.action_space.n


# ------------------------------------------------------------- accounting

def tiny_catalog():
    cat = FragmentCatalog(CFG.catalog, CFG.workload.n_cells, len(NAMES))
    return cat


def test_leaseholder_reads_land_on_the_primary_and_writes_on_every_replica():
    cat = tiny_catalog()
    rtt = env_rtt()
    f0_cell = 0
    reqs = [Request(READ, 3, (f0_cell,), (False,)), Request(WRITE, 3, (f0_cell,), (True,))]
    ops, _ = account(reqs, cat, rtt, follower=False)
    expect = cat.replicas[0].astype(float)
    expect[cat.primary[0]] += 1
    np.testing.assert_array_equal(ops, expect)


def test_follower_reads_land_on_the_nearest_replica_but_not_inside_read_write_txns():
    cat = tiny_catalog()
    rtt = env_rtt()
    near = serving_regions(cat, rtt, follower=True)
    c2f = cat.cell_to_fragment()
    # An origin whose nearest replica of fragment 0 is not its leaseholder.
    origin = int(next(o for o in range(len(NAMES)) if near[0, o] != cat.primary[0]))
    other = int(next(c for c in range(CFG.workload.n_cells) if c2f[c] != 0))
    ro = Request(TXN, origin, (0,), (False,))
    rw = Request(TXN, origin, (0, other), (False, True))
    ops_ro, _ = account([ro], cat, rtt, follower=True)
    ops_rw, _ = account([rw], cat, rtt, follower=True)
    expect_ro = np.zeros(len(NAMES)); expect_ro[near[0, origin]] = 1
    expect_rw = cat.replicas[c2f[other]].astype(float); expect_rw[cat.primary[0]] += 1
    np.testing.assert_array_equal(ops_ro, expect_ro)
    np.testing.assert_array_equal(ops_rw, expect_rw)      # the read stayed at the lease


def test_cross_region_fraction_counts_transactions_over_two_primaries():
    cat = tiny_catalog()
    c2f = cat.cell_to_fragment()
    a = 0
    b = int(next(c for c in range(CFG.workload.n_cells)
                 if cat.primary[c2f[c]] != cat.primary[c2f[a]]))
    same = Request(TXN, 0, (a, a), (False, False))
    split = Request(TXN, 0, (a, b), (False, False))
    _, frac = account([same, split], cat, env_rtt(), follower=False)
    assert frac == 0.5


def env_rtt():
    from fragalloc.topology import build_topology
    return build_topology(CFG.topology, CFG.catalog.dataset_bytes).rtt
