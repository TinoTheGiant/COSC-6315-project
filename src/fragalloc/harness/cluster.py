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


#: CockroachDB's own rebalancing, on: the ``crdb`` baseline (ADR-0021). Leases
#: and replicas follow load; splits and merges stay off, so ranges keep the
#: catalogue's boundaries and every policy is compared on the same shards.
REBALANCER_CRDB: dict[str, str] = {
    "kv.allocator.load_based_rebalancing": "leases and replicas",
    "kv.replicate_queue.enabled": "true",
    "kv.lease_queue.enabled": "true",
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


def release_rebalancer(sql: Sql) -> None:
    """Hand placement back to CockroachDB (the ``crdb`` baseline), verified."""
    for name, value in REBALANCER_CRDB.items():
        set_and_verify(sql, name, value)


def voter_counts(sql: Sql, layout: TableLayout) -> list[tuple[int, int, int]]:
    """``(range_id, voters, learners)`` per range. No ``DETAILS``: cheap."""
    rows = sql.query(f"SELECT range_id, voting_replicas, learner_replicas "
                     f"FROM [SHOW RANGES FROM TABLE {layout.table}]")
    return [(int(rid), len(parse_store_list(v)), len(parse_store_list(lr)))
            for rid, v, lr in rows]


def converge_replication(sql: Sql, layout: TableLayout, n_replicas: int, *,
                         timeout_s: float = 600.0, poll_s: float = 2.0,
                         sleep: Callable[[float], None] = time.sleep,
                         clock: Callable[[], float] = time.monotonic) -> float:
    """Bring every range of the table to ``n_replicas`` voters, then freeze.

    Returns the seconds convergence took. The rebalancer is frozen on the way
    out whether or not convergence succeeded, so a failure never leaves the
    cluster rebalancing behind the experiment's back.
    """
    n = int(n_replicas)
    if n == 2 or not 1 <= n <= 7:
        # Pilot #5: CockroachDB rejects num_replicas = 2 outright ("at least 3
        # replicas are required for multi-replica configurations").
        raise ValueError("n_replicas must be 1 or lie in [3, 7]; CockroachDB refuses 2")
    t0 = clock()
    sql.query(f"ALTER TABLE {layout.table} CONFIGURE ZONE USING num_replicas = {n}")
    # The split queue too, not only the replicate queue. With splits frozen, the
    # table's first range can stay joined to the system range before it and
    # inherit that range's five voters (pilot #5: "ranges not at 3 voters:
    # {74: 5}"). The split queue cuts it at the table boundary; nothing else
    # is splittable here (load-based splitting stays off, the table is small).
    set_and_verify(sql, "kv.split_queue.enabled", "true")
    set_and_verify(sql, "kv.replicate_queue.enabled", "true")
    try:
        stable = 0
        while True:
            counts = voter_counts(sql, layout)
            if counts and all(v == n and lr == 0 for _, v, lr in counts):
                # Two consecutive clean polls: a voter swap in flight shows up
                # as a learner on the next poll, and placing ranges on top of
                # one fails ("already has a VOTER_FULL", pilot #5).
                stable += 1
                if stable >= 2:
                    return clock() - t0
            else:
                stable = 0
            if clock() - t0 > timeout_s:
                off = {rid: v for rid, v, lr in counts if v != n or lr}
                raise ClusterError(
                    f"after {timeout_s:.0f} s, ranges not at {n} voters: {off}")
            sleep(poll_s)
    finally:
        freeze_rebalancer(sql)
