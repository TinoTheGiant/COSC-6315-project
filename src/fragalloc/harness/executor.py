"""Turn an agent action into CockroachDB statements, run them, and verify.

Steps 1, 3, 4 and 5 of the step protocol in docs/harness-architecture.md.

**One implementation of the action semantics.** The executor never decides for
itself what an action means. It applies the action to a copy of the intended
catalogue with the simulator's own ``ActionSpace.apply``, the function the
simulator steps with, and turns the difference between the catalogue before
and after into SQL. So which replica ``MOVE_REPLICA_TO`` evicts (the farthest
non-primary from the destination), when ``SPLIT`` is refused and where it cuts,
and when ``MOVE_LEASE`` is refused are the simulator's rules by construction,
not a restatement that could drift.

Translation, per ADR-0009 and the ``FragmentCatalog`` docstrings:

=================  =================================================================
``MOVE_LEASE``     ``ALTER RANGE r RELOCATE LEASE TO <store of region>``
``MOVE_REPLICA_TO`` ``ALTER RANGE r RELOCATE VOTERS FROM <evicted> TO <destination>``
``SPLIT``          ``ALTER TABLE t SPLIT AT VALUES (<first key of the midpoint cell>)``
``NOOP``           nothing
=================  =================================================================

Outcomes, never retried silently (design doc, step 3):

* ``applied``: every statement reported success;
* ``rejected``: the catalogue said the action applies, the database refused it;
* ``no-op``: the catalogue says the action changes nothing, so nothing is sent.

Whatever the outcome, the placement is then read back from the cluster
(step 4) and compared with what the outcome implies (step 5). The read-back,
not the intent, is what the step returns: on any divergence the cluster wins.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np

from fragalloc.actions import Action, ActionKind, ActionSpace
from fragalloc.catalog import FragmentCatalog, MutationResult
from fragalloc.config import FragAllocConfig
from fragalloc.harness.placement import (
    Divergence, PlacementError, Sql, StoreMap, TableLayout, is_connection_error,
    read_ranges, relocate, settle,
)
from fragalloc.topology import build_topology

APPLIED = "applied"
REJECTED = "rejected"
NO_OP = "no-op"


@dataclass(frozen=True)
class StepOutcome:
    """Everything one executed action produced, for the environment and the log."""

    action: Action
    outcome: str                         # APPLIED, REJECTED or NO_OP
    statements: tuple[str, ...]          # what was sent, in order
    detail: str                          # "ok", the refusal, or the catalogue's reason
    bytes_moved: float                   # the catalogue's account; 0 unless applied
    catalog: FragmentCatalog             # the cluster's placement after the step
    divergences: tuple[Divergence, ...]  # read-back against what the outcome implies
    elapsed_s: float

    @property
    def diverged(self) -> bool:
        return bool(self.divergences)


class Executor:
    """Runs agent actions against the harness table."""

    def __init__(self, sql: Sql, stores: StoreMap, layout: TableLayout,
                 cfg: FragAllocConfig, *, settle_tries: int = 15,
                 settle_wait_s: float = 1.0,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if len(stores.region_names) != cfg.n_regions:
            raise ValueError("store map and config disagree on the region count")
        self.sql, self.stores, self.layout, self.cfg = sql, stores, layout, cfg
        self.space = ActionSpace(cfg.catalog.max_fragments, cfg.n_regions)
        self.rtt = build_topology(cfg.topology, cfg.catalog.dataset_bytes).rtt
        self.settle_tries, self.settle_wait_s, self.sleep = settle_tries, settle_wait_s, sleep

    # ------------------------------------------------------------ planning

    def plan(self, intent: FragmentCatalog, index: int, range_ids: Sequence[int],
             ) -> tuple[FragmentCatalog, MutationResult, list[str]]:
        """What the action means, and the statements that bring it about.

        Pure: touches no database. ``range_ids[f]`` must be the range holding
        fragment ``f``.
        """
        expected = intent.copy()
        result = self.space.apply(expected, index, self.rtt)
        if not result.applied:
            return expected, result, []
        if len(range_ids) != intent.n_fragments:
            raise PlacementError(
                f"{len(range_ids)} ranges for {intent.n_fragments} fragments")

        action = self.space.decode(index)
        f = int(action.fragment)
        if action.kind is ActionKind.SPLIT:
            cut = int(expected.boundaries[f + 1])
            return expected, result, [
                f"ALTER TABLE {self.layout.table} SPLIT AT VALUES ({self.layout.cell_key(cut)})"]

        rid = int(range_ids[f])
        store = self.stores.store_of_region
        if action.kind is ActionKind.MOVE_LEASE:
            return expected, result, [
                f"ALTER RANGE {rid} RELOCATE LEASE TO {store[int(action.region)]}"]

        # MOVE_REPLICA_TO: exactly one region loses a replica, one gains it.
        lost = np.flatnonzero(intent.replicas[f] & ~expected.replicas[f])
        gained = np.flatnonzero(expected.replicas[f] & ~intent.replicas[f])
        if lost.size != 1 or gained.size != 1:
            raise AssertionError(f"replica move changed {lost.size} and {gained.size} regions")
        statements = [f"ALTER RANGE {rid} RELOCATE VOTERS FROM {store[int(lost[0])]} "
                      f"TO {store[int(gained[0])]}"]
        if expected.primary[f] != intent.primary[f]:
            # Only when the evicted replica was the primary (replication factor 1):
            # the lease must land where the catalogue says it does.
            statements.append(
                f"ALTER RANGE {rid} RELOCATE LEASE TO {store[int(expected.primary[f])]}")
        return expected, result, statements

    # ----------------------------------------------------------- executing

    def _run(self, stmt: str) -> tuple[bool, str]:
        if stmt.startswith("ALTER RANGE"):
            return relocate(self.sql, stmt)
        try:
            self.sql.query(stmt)
        except Exception as exc:  # noqa: BLE001 - classified here
            if is_connection_error(exc):
                raise
            text = str(exc).strip()
            return False, text.splitlines()[-1][:200] if text else repr(exc)
        return True, "ok"

    def step(self, intent: FragmentCatalog, index: int) -> StepOutcome:
        """Plan, execute, read back and compare. Raises if the cluster is gone."""
        t0 = time.monotonic()
        action = self.space.decode(index)
        ranges = read_ranges(self.sql, self.layout)
        starts = [r.start_cell for r in ranges]
        if starts != intent.boundaries[:-1].tolist():
            raise PlacementError(
                f"cluster ranges start at cells {starts} but intent has fragments at "
                f"{intent.boundaries[:-1].tolist()}; resync the catalogue before acting")

        expected, result, statements = self.plan(intent, index, [r.range_id for r in ranges])
        sent: list[str] = []
        if not statements:
            outcome, detail, target = NO_OP, result.reason, intent
        else:
            outcome, detail = APPLIED, "ok"
            for stmt in statements:
                sent.append(stmt)
                ok, msg = self._run(stmt)
                if not ok:
                    outcome, detail = REJECTED, msg
                    break
            target = expected if outcome == APPLIED else intent

        observed, divergences = settle(
            self.sql, self.stores, self.layout, self.cfg, target,
            tries=self.settle_tries if outcome == APPLIED else 3,
            wait_s=self.settle_wait_s, sleep=self.sleep)
        return StepOutcome(
            action=action, outcome=outcome, statements=tuple(sent), detail=detail,
            bytes_moved=float(result.bytes_moved) if outcome == APPLIED else 0.0,
            catalog=observed, divergences=tuple(divergences),
            elapsed_s=time.monotonic() - t0)
