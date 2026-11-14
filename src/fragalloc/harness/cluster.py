"""Cluster conditions every measurement assumes: replica count and a frozen rebalancer.

Cluster pilot #4 (14 November 2026) found every range of the harness table on
two voters, not three. The pilot froze CockroachDB's replicate queue about ten
seconds after start-up, before up-replication had finished, so ranges kept
whatever count they had reached. Nothing chose two; it was an accident of
timing. This module makes the count a decision (ADR-0015):

1. set the table's ``num_replicas`` zone configuration;
2. let the replicate queue move every range to that count;
3. confirm that every range has exactly that many voters and no learners;
4. only then freeze the rebalancer, and read each setting back.

Every setting is read back after it is set, rather than trusted, as the
cluster-settings guidance requires: four of the five are absent from the
public settings documentation (ADR-0009).
"""

from __future__ import annotations

import time
from typing import Callable

from fragalloc.harness.placement import Sql, TableLayout, parse_store_list


class ClusterError(RuntimeError):
    """The cluster is not in the state an experiment requires."""


#: The rebalancer, off. Values as ``SHOW CLUSTER SETTING`` reports them.
REBALANCER_OFF: dict[str, str] = {
    "kv.allocator.load_based_rebalancing": "off",
    "kv.replicate_queue.enabled": "false",
    "kv.lease_queue.enabled": "false",
    "kv.split_queue.enabled": "false",
    "kv.range_merge.queue.enabled": "false",
}


def _literal(value: str) -> str:
    return value if value in ("true", "false") else f"'{value}'"


def set_and_verify(sql: Sql, name: str, value: str) -> None:
    """``SET CLUSTER SETTING``, then read it back and refuse a mismatch."""
    if name not in REBALANCER_OFF:
        raise ValueError(f"not a setting this module manages: {name}")
    sql.query(f"SET CLUSTER SETTING {name} = {_literal(value)}")
    rows = sql.query(f"SHOW CLUSTER SETTING {name}")
    got = str(rows[0][0]).strip().lower() if rows else "<missing>"
    if got != value:
        raise ClusterError(f"{name} reads back as {got!r} after setting it to {value!r}")


def freeze_rebalancer(sql: Sql) -> None:
    """Turn the allocator off and verify every setting individually."""
    for name, value in REBALANCER_OFF.items():
        set_and_verify(sql, name, value)


def voter_counts(sql: Sql, layout: TableLayout) -> list[tuple[int, int, int]]:
    """``(range_id, voters, learners)`` per range. No ``DETAILS``: cheap."""
    rows = sql.query(f"SELECT range_id, voting_replicas, learner_replicas "
                     f"FROM [SHOW RANGES FROM TABLE {layout.table}]")
    return [(int(rid), len(parse_store_list(v)), len(parse_store_list(lr)))
            for rid, v, lr in rows]


def converge_replication(sql: Sql, layout: TableLayout, n_replicas: int, *,
                         timeout_s: float = 300.0, poll_s: float = 2.0,
                         sleep: Callable[[float], None] = time.sleep,
                         clock: Callable[[], float] = time.monotonic) -> float:
    """Bring every range of the table to ``n_replicas`` voters, then freeze.

    Returns the seconds convergence took. The rebalancer is frozen on the way
    out whether or not convergence succeeded, so a failure never leaves the
    cluster rebalancing behind the experiment's back.
    """
    if not 1 <= int(n_replicas) <= 7:
        raise ValueError("n_replicas must lie in [1, 7]")
    n = int(n_replicas)
    t0 = clock()
    sql.query(f"ALTER TABLE {layout.table} CONFIGURE ZONE USING num_replicas = {n}")
    set_and_verify(sql, "kv.replicate_queue.enabled", "true")
    try:
        while True:
            counts = voter_counts(sql, layout)
            if counts and all(v == n and lr == 0 for _, v, lr in counts):
                return clock() - t0
            if clock() - t0 > timeout_s:
                off = {rid: v for rid, v, lr in counts if v != n or lr}
                raise ClusterError(
                    f"after {timeout_s:.0f} s, ranges not at {n} voters: {off}")
            sleep(poll_s)
    finally:
        freeze_rebalancer(sql)
