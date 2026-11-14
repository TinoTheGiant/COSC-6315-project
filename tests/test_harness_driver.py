"""Harness piece 3: the per-region transaction driver, against fake gateways."""
from __future__ import annotations

import random
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from fragalloc.harness.driver import (
    READ, TXN, WRITE, Driver, DriverError, Request, SuspendWatch, choose_n, p95_standard_error,
    percentile, run_one, sample_requests, statements,
)
from fragalloc.harness.placement import StoreMap, TableLayout

LAYOUT = TableLayout(n_cells=8, rows_per_cell=4)
# Stores deliberately not 1..R in region order: join order decides store ids.
STORES = StoreMap(("a", "b", "c"), (2, 3, 1))


class FakeError(Exception):
    def __init__(self, msg: str, sqlstate: str | None) -> None:
        super().__init__(msg)
        self.sqlstate = sqlstate


class FakeGateway:
    """A connection to one node. Records every statement with the region it served."""

    def __init__(self, node: int, log: list, delay_s: float = 0.0, fail=None) -> None:
        self.node, self.log, self.delay_s = node, log, delay_s
        self.fail = list(fail or [])     # exceptions to raise, one per statement, in order
        self.closed = False

    def query(self, stmt, params=()):
        if stmt == "SHOW node_id":
            return [(self.node,)]
        if self.fail:
            exc = self.fail.pop(0)
            if exc is not None:
                raise exc
        if self.delay_s:
            time.sleep(self.delay_s)
        self.log.append((self.node, stmt, tuple(params)))
        return []

    def close(self):
        self.closed = True


def window(reads=None, writes=None, txns=None, cells=8, regions=3, templates=2):
    z = lambda shape: np.zeros(shape)  # noqa: E731
    return SimpleNamespace(
        reads=reads if reads is not None else z((cells, regions)),
        writes=writes if writes is not None else z((cells, regions)),
        txn_counts=txns if txns is not None else z((templates, regions)))


TEMPLATE_CELLS = np.array([[0, 5], [2, 3]])
TEMPLATE_WRITES = np.array([[False, True], [False, False]])


# ------------------------------------------------------------- sampling

def test_sample_follows_the_only_nonzero_count():
    w = np.zeros((8, 3)); w[6, 2] = 5.0
    reqs = sample_requests(window(writes=w), TEMPLATE_CELLS, TEMPLATE_WRITES, 50,
                           np.random.default_rng(0))
    assert {(r.kind, r.origin, r.cells, r.writes) for r in reqs} == {(WRITE, 2, (6,), (True,))}


def test_sample_decodes_templates_and_origins():
    t = np.zeros((2, 3)); t[1, 0] = 1.0
    reqs = sample_requests(window(txns=t), TEMPLATE_CELLS, TEMPLATE_WRITES, 10,
                           np.random.default_rng(0))
    assert all(r.kind == TXN and r.origin == 0 and r.cells == (2, 3) and r.read_only
               and r.template == 1 for r in reqs)


def test_sample_mix_matches_the_window_in_proportion():
    rng = np.random.default_rng(1)
    r = rng.random((8, 3)); w = rng.random((8, 3)); t = rng.random((2, 3)) * 4
    reqs = sample_requests(window(r, w, t), TEMPLATE_CELLS, TEMPLATE_WRITES, 20_000,
                           np.random.default_rng(2))
    total = r.sum() + w.sum() + t.sum()
    for kind, mass in ((READ, r.sum()), (WRITE, w.sum()), (TXN, t.sum())):
        got = sum(q.kind == kind for q in reqs) / len(reqs)
        assert got == pytest.approx(mass / total, abs=0.015)
    by_origin = np.bincount([q.origin for q in reqs], minlength=3) / len(reqs)
    expect = (r.sum(0) + w.sum(0) + t.sum(0)) / total
    np.testing.assert_allclose(by_origin, expect, atol=0.015)


def test_sample_refuses_empty_demand():
    with pytest.raises(ValueError):
        sample_requests(window(), TEMPLATE_CELLS, TEMPLATE_WRITES, 5, np.random.default_rng(0))


# ------------------------------------------------------------- statements

def test_single_ops_are_autocommit_and_stay_inside_their_cell():
    rng = random.Random(0)
    for kind, verb in ((READ, "SELECT"), (WRITE, "UPDATE")):
        for _ in range(30):
            (stmt, (key,)), = statements(Request(kind, 0, (3,), (kind == WRITE,)), LAYOUT, rng)
            assert stmt.startswith(verb)
            assert LAYOUT.cell_key(3) <= key < LAYOUT.cell_key(4)


def test_transactions_are_explicit_and_read_only_when_nothing_writes():
    rng = random.Random(0)
    rw = statements(Request(TXN, 0, (0, 5), (False, True)), LAYOUT, rng)
    ro = statements(Request(TXN, 0, (2, 3), (False, False)), LAYOUT, rng)
    assert [s for s, _ in rw] == ["BEGIN", "SELECT v FROM fragalloc WHERE k = %s",
                                  "UPDATE fragalloc SET v = v WHERE k = %s", "COMMIT"]
    assert ro[0][0] == "BEGIN TRANSACTION READ ONLY" and ro[-1][0] == "COMMIT"


# ------------------------------------------------------------- run_one

def ticking():
    t = [0.0]

    def clock():
        t[0] += 0.001
        return t[0]
    return clock


def test_serialization_failure_retries_the_whole_transaction_and_counts_it():
    log = []
    gw = FakeGateway(2, log, fail=[None, FakeError("restart", "40001"),
                                   FakeError("restart", "40001")])
    req = Request(TXN, 0, (0, 5), (False, True))
    s = run_one(gw, req, LAYOUT, random.Random(0), sleep=lambda _: None, clock=ticking())
    assert s.ok and s.attempts == 2
    stmts = [x[1] for x in log]
    # attempt 1: BEGIN ran, SELECT raised, ROLLBACK raised too (scripted);
    # attempt 2 runs every statement from BEGIN.
    assert stmts[-4:] == ["BEGIN", "SELECT v FROM fragalloc WHERE k = %s",
                          "UPDATE fragalloc SET v = v WHERE k = %s", "COMMIT"]


def test_retry_latency_runs_from_the_first_attempt():
    gw = FakeGateway(2, [], fail=[FakeError("restart", "40001")])
    t = [0.0]

    def clock():
        return t[0]

    def sleep(dt):
        t[0] += 0.5                  # half a second lost to backoff
    s = run_one(gw, Request(READ, 0, (1,), (False,)), LAYOUT, random.Random(0),
                sleep=sleep, clock=clock)
    assert s.ok and s.attempts == 2 and s.latency_ms == pytest.approx(500.0)


def test_other_errors_fail_once_and_are_not_retried():
    log = []
    gw = FakeGateway(2, log, fail=[FakeError("duplicate", "23505")])
    s = run_one(gw, Request(WRITE, 0, (1,), (True,)), LAYOUT, random.Random(0),
                sleep=lambda _: None)
    assert not s.ok and s.attempts == 1 and "23505" in s.error and log == []


def test_retries_give_up_at_the_cap():
    gw = FakeGateway(2, [], fail=[FakeError("restart", "40001")] * 3)
    s = run_one(gw, Request(READ, 0, (1,), (False,)), LAYOUT, random.Random(0),
                max_attempts=3, sleep=lambda _: None)
    assert not s.ok and s.attempts == 3


def test_lost_connection_is_not_a_sample():
    gw = FakeGateway(2, [], fail=[ConnectionResetError("gone")])
    with pytest.raises(DriverError):
        run_one(gw, Request(READ, 0, (1,), (False,)), LAYOUT, random.Random(0))


# ------------------------------------------------------------- the driver

def make_driver(log, concurrency=2, delay_s=0.0, nodes=None, fail_region=None):
    nodes = nodes or STORES.store_of_region

    def connect(region):
        fail = [None] * 3 + [ConnectionRefusedError("node died")] if region == fail_region else None
        return FakeGateway(nodes[region], log, delay_s, fail=fail)
    return Driver(connect, STORES, LAYOUT, concurrency=concurrency, seed=0)


def test_every_request_runs_on_a_gateway_in_its_own_region():
    log = []
    d = make_driver(log)
    reqs = [Request(READ, r, (r,), (False,)) for r in (0, 1, 2) for _ in range(20)]
    res = d.drive(reqs)
    assert len(res.samples) == 60 and all(s.ok for s in res.samples)
    # The read for origin r touches cell r's keys; each must have gone to r's node.
    for node, _, (key,) in log:
        assert node == STORES.store_of_region[key // LAYOUT.rows_per_cell]
    assert res.gateways == {"a": 2, "b": 3, "c": 1}


def test_a_gateway_in_the_wrong_region_refuses_to_start():
    with pytest.raises(DriverError, match="not that region's node"):
        make_driver([], nodes=(2, 1, 3))


def test_concurrency_is_the_stated_number_not_the_core_count():
    log = []
    d = make_driver(log, concurrency=3, delay_s=0.02)
    res = d.drive([Request(READ, r, (0,), (False,)) for r in (0, 1, 2) for _ in range(12)])
    assert res.max_in_flight == 9
    s = res.summary()
    assert s["concurrency_per_region"] == 3 and s["n"] == 36 and s["failures"] == 0


def test_a_node_lost_mid_drive_aborts_the_drive():
    d = make_driver([], concurrency=1, fail_region=1)
    with pytest.raises(DriverError, match="region 1"):
        d.drive([Request(READ, r, (0,), (False,)) for r in (0, 1, 2) for _ in range(5)])


def test_close_closes_every_connection():
    d = make_driver([], concurrency=2)
    d.close()
    assert all(sql.closed for pool in d._pools for sql in pool)


def test_summary_counts_retries_and_failures():
    from fragalloc.harness.driver import DriveResult, Sample
    res = DriveResult([Sample(READ, 0, 10.0, 1, True), Sample(TXN, 1, 30.0, 3, True),
                       Sample(WRITE, 2, 99.0, 1, False, "x")], wall_s=1.0,
                      concurrency=1, gateways={})
    s = res.summary()
    assert (s["n"], s["ok"], s["failures"], s["retries"]) == (3, 2, 1, 2)
    assert s["max_ms"] == 30.0          # failures are not latencies
    assert s["by_kind"][TXN]["n"] == 1


def test_suspend_watch_is_quiet_when_nothing_sleeps():
    w = SuspendWatch()
    time.sleep(0.01)
    assert not w.suspended and w.reference in ("boottime", "wall")


# ------------------------------------------------------------- choosing N

def test_percentile_is_nearest_rank():
    xs = list(range(1, 101))
    assert percentile(xs, 50) == 51 and percentile(xs, 95) == 95 and percentile(xs, 100) == 100


def test_p95_error_shrinks_with_sample_size_and_choose_n_picks_the_smallest():
    lat = np.random.default_rng(0).lognormal(5.0, 0.5, size=2000)
    se = p95_standard_error(lat, [50, 200, 800], iters=400)
    assert se[50] > se[200] > se[800]
    assert choose_n(se, se[200] + 1e-9) == 200
    assert choose_n(se, se[800] / 2) is None


# ------------------------------------------------------------- read modes (ADR-0018)

def test_follower_mode_reads_read_only_work_at_the_follower_timestamp():
    rng = random.Random(0)
    (single, _), = statements(Request(READ, 0, (3,), (False,)), LAYOUT, rng, "follower")
    ro = [s for s, _ in statements(Request(TXN, 0, (2, 3), (False, False)), LAYOUT, rng,
                                   "follower")]
    rw = [s for s, _ in statements(Request(TXN, 0, (0, 5), (False, True)), LAYOUT, rng,
                                   "follower")]
    assert "follower_read_timestamp()" in single
    assert ro[:2] == ["BEGIN TRANSACTION READ ONLY",
                      "SET TRANSACTION AS OF SYSTEM TIME follower_read_timestamp()"]
    # CockroachDB forbids follower reads in a read-write transaction.
    assert not any("follower" in s for s in rw)


def test_leaseholder_mode_never_reads_stale():
    rng = random.Random(0)
    for req in (Request(READ, 0, (3,), (False,)), Request(TXN, 0, (2, 3), (False, False))):
        assert not any("AS OF" in s for s, _ in statements(req, LAYOUT, rng, "leaseholder"))


def test_driver_carries_its_read_mode_to_every_request():
    log = []
    d = Driver(lambda r: FakeGateway(STORES.store_of_region[r], log), STORES, LAYOUT,
               concurrency=1, read_mode="follower")
    res = d.drive([Request(READ, r, (0,), (False,)) for r in (0, 1, 2)])
    assert res.summary()["read_mode"] == "follower"
    assert all("follower_read_timestamp()" in stmt for _, stmt, _ in log)
    with pytest.raises(ValueError):
        Driver(lambda r: FakeGateway(STORES.store_of_region[r], []), STORES, LAYOUT,
               read_mode="nearest")
