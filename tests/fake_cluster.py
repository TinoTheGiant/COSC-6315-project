"""A small stateful stand-in for CockroachDB, for harness tests.

It obeys the cluster's rules, not the catalogue's, so tests that pass through it
check the executor's translation against an independent model:

* a lease can move only to a store holding a voter;
* a voter can be added only where there is none, and removed only where there is;
* a split at an existing boundary changes nothing; a new range inherits its
  parent's lease and voters;
* ``RELOCATE`` reports failure in its result column, not by raising.

Knobs for failure tests: ``refuse_next`` (a result-column error for the next
``RELOCATE``), ``raise_next`` (an exception for the next statement of any kind),
``stale_reads`` (``SHOW RANGES`` returns the state before the last change this
many times) and ``down`` (every statement raises ``ConnectionRefusedError``).

Cluster settings are stored and read back; ``ignored_settings`` names settings
that silently keep their old value, as an unsupported setting would. While
``kv.replicate_queue.enabled`` is true, each read of voter counts moves every
range one voter towards the table's ``num_replicas``, so convergence takes
several polls, as on a real cluster.
"""

from __future__ import annotations

import copy
import re

import numpy as np

from fragalloc.catalog import FragmentCatalog
from fragalloc.harness.placement import StoreMap, TableLayout


class FakeCluster:
    def __init__(self, stores: StoreMap, layout: TableLayout) -> None:
        self.stores, self.layout = stores, layout
        self.ranges: list[dict] = []
        self.statements: list[str] = []
        self.refuse_next: str | None = None
        self.raise_next: BaseException | None = None
        self.stale_reads = 0
        self.down = False
        self._before: list[dict] | None = None
        self._next_id = 100
        self.settings: dict[str, str] = {"kv.replicate_queue.enabled": "true"}
        self.ignored_settings: set[str] = set()
        self.num_replicas: int | None = None
        #: range id -> polls for which it still reports a learner replica
        self.learner_polls: dict[int, int] = {}

    @classmethod
    def from_catalog(cls, cat: FragmentCatalog, stores: StoreMap,
                     layout: TableLayout) -> "FakeCluster":
        c = cls(stores, layout)
        for f in range(cat.n_fragments):
            start = int(cat.boundaries[f])
            c.ranges.append({
                "id": c._new_id(),
                "start": None if f == 0 else layout.cell_key(start),
                "lease": stores.store_of_region[int(cat.primary[f])],
                "voters": [stores.store_of_region[r] for r in np.flatnonzero(cat.replicas[f])],
            })
        return c

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _range(self, rid: int) -> dict:
        return next(r for r in self.ranges if r["id"] == rid)

    def _changed(self) -> None:
        self.stale_reads_left = self.stale_reads

    def _replicate_one_step(self) -> None:
        for r in self.ranges:
            voters = r["voters"]
            if len(voters) < self.num_replicas:
                spare = [st for st in self.stores.store_of_region if st not in voters]
                voters.append(spare[0])
            elif len(voters) > self.num_replicas:
                drop = next(v for v in reversed(voters) if v != r["lease"])
                voters.remove(drop)

    # ---------------------------------------------------------------- Sql

    def query(self, stmt, params=()):
        s = " ".join(stmt.split())
        self.statements.append(s)
        if self.down:
            raise ConnectionRefusedError("connection refused")
        if self.raise_next is not None:
            exc, self.raise_next = self.raise_next, None
            raise exc

        if "kv_store_status" in s:
            return [(st, st, f"region={n}") for n, st in
                    zip(self.stores.region_names, self.stores.store_of_region)]

        m = re.match(r"SET CLUSTER SETTING ([\w.]+) = '?([\w ]+?)'?$", s)
        if m:
            if m[1] not in self.ignored_settings:
                self.settings[m[1]] = m[2]
            return []
        m = re.match(r"SHOW CLUSTER SETTING ([\w.]+)$", s)
        if m:
            return [(self.settings.get(m[1], "default"),)]
        m = re.match(r"ALTER TABLE \w+ CONFIGURE ZONE USING num_replicas = (\d+)$", s)
        if m:
            if int(m[1]) == 2:           # as CockroachDB v25.3 does
                raise ValueError("could not validate zone config: at least 3 replicas "
                                 "are required for multi-replica configurations")
            self.num_replicas = int(m[1])
            return []
        if "learner_replicas" in s and "SHOW RANGES" in s:
            if self.settings.get("kv.replicate_queue.enabled") == "true" and self.num_replicas:
                self._replicate_one_step()
            rows = []
            for r in self.ranges:
                left = self.learner_polls.get(r["id"], 0)
                rows.append((r["id"], list(r["voters"]), [99] if left else []))
                if left:
                    self.learner_polls[r["id"]] = left - 1
            return rows

        if "SHOW RANGES" in s:
            state = self.ranges
            if getattr(self, "stale_reads_left", 0) > 0 and self._before is not None:
                self.stale_reads_left -= 1
                state = self._before
            return [("…/<TableMin>" if r["start"] is None else f"…/1/{r['start']}",
                     r["id"], r["lease"], list(r["voters"])) for r in state]

        if s.startswith("CREATE TABLE"):
            # A fresh table is one range on the first three regions' stores.
            st = self.stores.store_of_region
            self.ranges = [{"id": self._new_id(), "start": None, "lease": st[0],
                            "voters": list(st[:3])}]
            return []

        if re.match(r"ALTER TABLE \w+ SPLIT AT VALUES ", s):
            rows = []
            self._before = copy.deepcopy(self.ranges)
            for key in map(int, re.findall(r"\((\d+)\)", s)):
                starts = [0 if r["start"] is None else r["start"] for r in self.ranges]
                if key not in starts:
                    parent = max((r for r in self.ranges if (r["start"] or 0) < key),
                                 key=lambda r: r["start"] or 0)
                    self.ranges.append({"id": self._new_id(), "start": key,
                                        "lease": parent["lease"],
                                        "voters": list(parent["voters"])})
                rows.append((key, f"…/1/{key}", None))
            self._changed()
            return rows

        m = re.match(r"ALTER RANGE (\d+) RELOCATE LEASE TO (\d+)$", s)
        if m:
            r, to = self._range(int(m[1])), int(m[2])
            if self.refuse_next:
                msg, self.refuse_next = self.refuse_next, None
                return [(r["id"], "…", msg)]
            if to not in self.stores.store_of_region:
                return [(r["id"], "…", f"unable to find store {to}")]
            if to not in r["voters"]:
                return [(r["id"], "…", f"unable to transfer lease to s{to}: no voter there")]
            self._before = copy.deepcopy(self.ranges)
            r["lease"] = to
            self._changed()
            return [(r["id"], "…", "ok")]

        m = re.match(r"ALTER RANGE (\d+) RELOCATE VOTERS FROM (\d+) TO (\d+)$", s)
        if m:
            r, a, b = self._range(int(m[1])), int(m[2]), int(m[3])
            if self.refuse_next:
                msg, self.refuse_next = self.refuse_next, None
                return [(r["id"], "…", msg)]
            if b in r["voters"]:
                return [(r["id"], "…", "trying to add a voter to a store that already has a VOTER_FULL")]
            if a not in r["voters"]:
                return [(r["id"], "…", "trying to remove a replica that doesn't exist")]
            self._before = copy.deepcopy(self.ranges)
            r["voters"] = [b if v == a else v for v in r["voters"]]
            if r["lease"] == a:          # the leaseholder left; the lease follows the move
                r["lease"] = b
            self._changed()
            return [(r["id"], "…", "ok")]

        return []
