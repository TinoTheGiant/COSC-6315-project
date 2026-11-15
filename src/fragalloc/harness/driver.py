"""Drive one window's transactions against the cluster and time each one.

Step 7 of the step protocol in docs/harness-architecture.md, and the
measurement protocol of its section 5.

What is sent. A window's demand (``WorkloadWindow``) is three count matrices:
single-key reads, single-key writes, and multi-cell transactions by template.
:func:`sample_requests` draws ``N`` requests from those counts in proportion,
so the mix of kinds, origins and cells on the cluster is the simulator's mix.

How each kind runs (designing-application-transactions guidance):

=================  ===========================================================
single read        one autocommit ``SELECT``
single write       one autocommit ``UPDATE``
transaction        ``BEGIN``; one statement per member cell, in template
                   order; ``COMMIT``. ``BEGIN TRANSACTION READ ONLY`` when no
                   member writes. Sequential statements match the simulator,
                   which charges a transaction the sum of its members.
=================  ===========================================================

A ``40001`` (serialization failure) retries the whole unit of work with capped
exponential backoff and jitter. The latency recorded is from the first attempt
to success, because that is what a client sees, and the retries are counted.
Any other error is a failure, recorded, never retried. Lost connections abort
the drive: a dead node is not a data point (design doc, section 6).

Gateways. One pool of ``concurrency`` workers per region, each with its own
connection to that region's node, so the client-to-gateway hop is local. Each
connection asks the server which node it reached (``SHOW node_id``) and the
drive refuses to start if any gateway is in the wrong region.

Concurrency is a fixed, stated parameter, independent of the runner's core
count. Threads, not processes: the work is network-bound and psycopg releases
the GIL while it waits.

Timing is client-side with ``time.perf_counter`` (monotonic). A laptop that
sleeps mid-drive stops the monotonic clock on Linux but not the boot clock, so
:class:`SuspendWatch` compares the two and marks the drive suspect.
"""

from __future__ import annotations

import queue
import random
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np

from fragalloc.harness.placement import Sql, StoreMap, TableLayout, is_connection_error

READ, WRITE, TXN = "read", "write", "txn"


class DriverError(RuntimeError):
    """The drive cannot produce valid numbers: wrong gateway, lost node."""


@dataclass(frozen=True)
class Request:
    """One unit of work: who sends it and which cells it touches."""

    kind: str
    origin: int
    cells: tuple[int, ...]
    writes: tuple[bool, ...]
    template: int = -1

    @property
    def read_only(self) -> bool:
        return not any(self.writes)


def sample_requests(window, template_cells: np.ndarray, template_is_write: np.ndarray,
                    n: int, rng: np.random.Generator) -> list[Request]:
    """Draw ``n`` requests from one window's demand, in proportion to its counts."""
    reads = np.asarray(window.reads, dtype=np.float64)
    writes = np.asarray(window.writes, dtype=np.float64)
    txns = np.asarray(window.txn_counts, dtype=np.float64)
    weights = np.concatenate([reads.ravel(), writes.ravel(), txns.ravel()])
    total = weights.sum()
    if n < 1 or total <= 0:
        raise ValueError(f"need n >= 1 and some demand, got n={n}, demand={total}")
    n_cells, n_regions = reads.shape
    single = n_cells * n_regions
    picks = rng.choice(weights.size, size=int(n), p=weights / total)
    out = []
    for p in picks.tolist():
        if p < 2 * single:
            kind = READ if p < single else WRITE
            cell, origin = divmod(p % single, n_regions)
            out.append(Request(kind, origin, (cell,), (kind == WRITE,)))
        else:
            t, origin = divmod(p - 2 * single, n_regions)
            out.append(Request(TXN, origin, tuple(int(c) for c in template_cells[t]),
                               tuple(bool(w) for w in template_is_write[t]), template=t))
    return out


@dataclass(frozen=True)
class Sample:
    """One request's outcome, as the client saw it."""

    kind: str
    origin: int
    latency_ms: float
    attempts: int
    ok: bool
    error: str = ""


def sqlstate(exc: BaseException) -> str:
    state = getattr(exc, "sqlstate", None)
    if state is None:
        state = getattr(getattr(exc, "diag", None), "sqlstate", None)
    return str(state or "")


#: How reads are served (ADR-0018). ``leaseholder`` is a plain strong read, the
#: simulator's ``primary_only``. ``follower`` reads read-only work at
#: ``follower_read_timestamp()`` so the nearest replica can serve it, the
#: simulator's ``nearest_replica``; reads inside a read-write transaction stay
#: at the leaseholder, because CockroachDB allows nothing else.
READ_MODES = {"primary_only": "leaseholder", "nearest_replica": "follower"}
FOLLOWER_TS = "AS OF SYSTEM TIME follower_read_timestamp()"


def statements(req: Request, layout: TableLayout, rng: random.Random,
               read_mode: str = "leaseholder") -> list[tuple[str, tuple]]:
    """The SQL for one request. A random row within each member cell."""
    if read_mode not in ("leaseholder", "follower"):
        raise ValueError(f"unknown read mode {read_mode!r}")
    follower = read_mode == "follower"
    t = layout.table
    stmts = []
    for cell, w in zip(req.cells, req.writes):
        key = layout.cell_key(cell) + rng.randrange(layout.rows_per_cell)
        if w:
            stmts.append((f"UPDATE {t} SET v = v WHERE k = %s", (key,)))
        elif follower and req.kind == READ:
            stmts.append((f"SELECT v FROM {t} {FOLLOWER_TS} WHERE k = %s", (key,)))
        else:
            stmts.append((f"SELECT v FROM {t} WHERE k = %s", (key,)))
    if req.kind != TXN:
        return stmts
    if not req.read_only:
        return [("BEGIN", ())] + stmts + [("COMMIT", ())]
    begin = [("BEGIN TRANSACTION READ ONLY", ())]
    if follower:
        begin.append((f"SET TRANSACTION {FOLLOWER_TS}", ()))
    return begin + stmts + [("COMMIT", ())]


def run_one(sql: Sql, req: Request, layout: TableLayout, rng: random.Random,
            max_attempts: int = 8, sleep: Callable[[float], None] = time.sleep,
            clock: Callable[[], float] = time.perf_counter,
            read_mode: str = "leaseholder") -> Sample:
    """Run one request to completion, retrying the whole unit on ``40001``."""
    stmts = statements(req, layout, rng, read_mode)
    explicit = req.kind == TXN
    backoff = 0.01
    t0 = clock()
    for attempt in range(1, max_attempts + 1):
        try:
            for stmt, params in stmts:
                sql.query(stmt, params)
            return Sample(req.kind, req.origin, (clock() - t0) * 1000.0, attempt, True)
        except Exception as exc:  # noqa: BLE001 - classified below
            if is_connection_error(exc):
                raise DriverError(f"lost the gateway for region {req.origin}: {exc}") from exc
            if explicit:
                try:
                    sql.query("ROLLBACK")
                except Exception as rb:  # noqa: BLE001
                    if is_connection_error(rb):
                        raise DriverError(f"lost the gateway for region {req.origin}: {rb}") from rb
            if sqlstate(exc) != "40001" or attempt == max_attempts:
                return Sample(req.kind, req.origin, (clock() - t0) * 1000.0, attempt, False,
                              f"{sqlstate(exc) or type(exc).__name__}: {exc}"[:200])
            sleep(backoff + rng.uniform(0, backoff))
            backoff = min(backoff * 2, 1.0)
    raise AssertionError("unreachable")  # pragma: no cover


class SuspendWatch:
    """Detects a machine that slept mid-measurement.

    Linux: ``CLOCK_BOOTTIME`` counts suspend and ``perf_counter`` does not, so a
    gap between them is time the process did not run. Elsewhere the wall clock
    stands in, which NTP can also move, so the threshold is generous.
    """

    def __init__(self, threshold_s: float = 1.0) -> None:
        self.threshold_s = threshold_s
        boot = getattr(time, "CLOCK_BOOTTIME", None) if sys.platform.startswith("linux") else None
        self._other = (lambda: time.clock_gettime(boot)) if boot is not None else time.time
        self.reference = "boottime" if boot is not None else "wall"
        self._t0 = (time.perf_counter(), self._other())

    def gap_s(self) -> float:
        mono = time.perf_counter() - self._t0[0]
        other = self._other() - self._t0[1]
        return other - mono

    @property
    def suspended(self) -> bool:
        return abs(self.gap_s()) > self.threshold_s


def percentile(xs: Sequence[float], p: float) -> float:
    """Nearest-rank percentile, the definition falsification_test.py reports."""
    s = sorted(xs)
    if not s:
        return float("nan")
    return float(s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))])


@dataclass
class DriveResult:
    samples: list[Sample]
    wall_s: float
    concurrency: int
    gateways: dict[str, int]
    read_mode: str = "leaseholder"
    suspended: bool = False
    suspend_gap_s: float = 0.0
    max_in_flight: int = 0
    stalls: list[float] = field(default_factory=list)

    def latencies(self, ok_only: bool = True) -> list[float]:
        return [s.latency_ms for s in self.samples if s.ok or not ok_only]

    def summary(self) -> dict:
        lat = self.latencies()
        by_kind = {}
        for kind in (READ, WRITE, TXN):
            xs = [s.latency_ms for s in self.samples if s.kind == kind and s.ok]
            by_kind[kind] = {"n": len(xs), "p50": percentile(xs, 50), "p95": percentile(xs, 95)}
        return {
            "n": len(self.samples),
            "ok": len(lat),
            "failures": sum(not s.ok for s in self.samples),
            "retries": sum(s.attempts - 1 for s in self.samples),
            "mean_ms": float(np.mean(lat)) if lat else float("nan"),
            "p50_ms": percentile(lat, 50),
            "p95_ms": percentile(lat, 95),
            "p99_ms": percentile(lat, 99),
            "max_ms": max(lat) if lat else float("nan"),
            "by_kind": by_kind,
            "wall_s": self.wall_s,
            "throughput_per_s": len(self.samples) / self.wall_s if self.wall_s > 0 else 0.0,
            "concurrency_per_region": self.concurrency,
            "read_mode": self.read_mode,
            "max_in_flight": self.max_in_flight,
            "gateways": self.gateways,
            "suspended": self.suspended,
            "suspend_gap_s": self.suspend_gap_s,
            "stalls": len(self.stalls),
        }


def check_gateway(sql: Sql, region: int, stores: StoreMap) -> int:
    """Ask the server which node this connection reached; refuse the wrong region."""
    rows = sql.query("SHOW node_id")
    node = int(rows[0][0])
    # store_id == node_id is asserted by resolve_stores.
    if node not in stores.store_of_region or stores.region_of(node) != region:
        raise DriverError(f"connection for {stores.region_names[region]} reached node {node}, "
                          f"which is not that region's node "
                          f"{stores.store_of_region[region]}")
    return node


class Driver:
    """Per-region pools of pinned connections that run sampled requests.

    ``connect(region)`` returns a fresh :class:`Sql` to that region's node. On
    the docker cluster that is port ``26257 + region``
    (scripts/gen_cluster.py); :func:`port_connector` builds it.
    """

    def __init__(self, connect: Callable[[int], Sql], stores: StoreMap,
                 layout: TableLayout, concurrency: int = 2, seed: int = 0,
                 max_attempts: int = 8, stall_ms: float = 30_000.0,
                 read_mode: str = "leaseholder") -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        if read_mode not in ("leaseholder", "follower"):
            raise ValueError(f"unknown read mode {read_mode!r}")
        self.read_mode = read_mode
        self.stores, self.layout = stores, layout
        self.concurrency, self.max_attempts, self.stall_ms = concurrency, max_attempts, stall_ms
        self.n_regions = len(stores.region_names)
        self._seed = seed
        self._pools: list[list[Sql]] = []
        self.gateways: dict[str, int] = {}
        for r in range(self.n_regions):
            pool = []
            for _ in range(concurrency):
                sql = connect(r)
                self.gateways[stores.region_names[r]] = check_gateway(sql, r, stores)
                pool.append(sql)
            self._pools.append(pool)

    def close(self) -> None:
        for pool in self._pools:
            for sql in pool:
                close = getattr(sql, "close", None)
                if close:
                    close()

    def drive(self, requests: Sequence[Request]) -> DriveResult:
        """Run every request; return per-request samples in completion order."""
        queues = [queue.SimpleQueue() for _ in range(self.n_regions)]
        for req in requests:
            queues[req.origin].put(req)
        samples: list[Sample] = []
        errors: list[BaseException] = []
        lock = threading.Lock()
        in_flight = [0, 0]  # current, max
        stop = threading.Event()

        def work(region: int, slot: int, sql: Sql) -> None:
            rng = random.Random(self._seed * 1_000_003 + region * 1_009 + slot)
            q = queues[region]
            while not stop.is_set():
                try:
                    req = q.get_nowait()
                except queue.Empty:
                    return
                with lock:
                    in_flight[0] += 1
                    in_flight[1] = max(in_flight[1], in_flight[0])
                try:
                    s = run_one(sql, req, self.layout, rng, self.max_attempts,
                                read_mode=self.read_mode)
                except BaseException as exc:  # noqa: BLE001 - surfaced after join
                    with lock:
                        errors.append(exc)
                    stop.set()
                    return
                finally:
                    with lock:
                        in_flight[0] -= 1
                with lock:
                    samples.append(s)

        watch = SuspendWatch()
        t0 = time.perf_counter()
        threads = [threading.Thread(target=work, args=(r, i, sql), daemon=True)
                   for r, pool in enumerate(self._pools) for i, sql in enumerate(pool)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        wall = time.perf_counter() - t0
        if errors:
            raise DriverError(str(errors[0])) from errors[0]
        stalls = [s.latency_ms for s in samples if s.latency_ms > self.stall_ms]
        return DriveResult(samples, wall, self.concurrency, dict(self.gateways),
                           read_mode=self.read_mode, suspended=watch.suspended, suspend_gap_s=watch.gap_s(),
                           max_in_flight=in_flight[1], stalls=stalls)


def port_connector(base_port: int = 26257, host: str = "127.0.0.1") -> Callable[[int], Sql]:
    """Region ``i`` -> a connection to ``host:base_port + i`` (the docker layout)."""
    from fragalloc.harness.placement import PsycopgSql

    return lambda region: PsycopgSql.connect(host=host, port=base_port + region)


# ------------------------------------------------------------- choosing N

def p95_standard_error(latencies: Sequence[float], sizes: Sequence[int], iters: int = 1000,
                       seed: int = 0) -> dict[int, float]:
    """Bootstrap standard error of the p95 estimate at each subsample size.

    Section 5 of the design: hold placement fixed, drive a large sample, and ask
    how noisy p95 would be had only ``n`` transactions been timed.
    """
    xs = np.asarray(latencies, dtype=np.float64)
    if xs.size < 2:
        raise ValueError("need at least two latencies")
    rng = np.random.default_rng(seed)
    out = {}
    for n in sizes:
        draws = rng.choice(xs, size=(iters, int(n)), replace=True)
        p95 = np.sort(draws, axis=1)[:, min(int(n) - 1, int(round(0.95 * (int(n) - 1))))]
        out[int(n)] = float(p95.std(ddof=1))
    return out


def mean_standard_error(latencies: Sequence[float], sizes: Sequence[int]) -> dict[int, float]:
    """Standard error of the mean latency at each sample size: ``sd / sqrt(n)``.

    The reward is built from the mean, so this, not the p95 error, decides N.
    Pilot #5 showed why they differ: latency is multimodal (reads, writes and
    transactions sit about 170, 430 and 500 to 900 ms apart), so the p95 lands
    in the gap between modes and its estimate is far noisier than the mean's.
    """
    xs = np.asarray(latencies, dtype=np.float64)
    if xs.size < 2:
        raise ValueError("need at least two latencies")
    sd = float(xs.std(ddof=1))
    return {int(n): sd / float(np.sqrt(int(n))) for n in sizes}


def choose_n(se_by_size: dict[int, float], target_se_ms: float) -> int | None:
    """Smallest size whose p95 standard error is at or below the target; None if none is."""
    ok = [n for n, se in sorted(se_by_size.items()) if se <= target_se_ms]
    return ok[0] if ok else None
