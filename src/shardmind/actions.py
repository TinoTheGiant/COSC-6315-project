"""The flat, declarative action space.

DQN estimates a value for every action in a fixed discrete set and offers no
mechanism for masking the ones that do not apply. Two consequences follow, and
both shape the design here.

First, the space must be flat. A factored action -- choose a fragment, then an
operation, then a target -- would need either an architecture that DQN does not
have or a decomposition that breaks the Q-value's meaning. So every
``(operation, fragment, region)`` pair gets its own index.

Second, actions are named as desired end states rather than as operations.
"Put a replica of fragment 7 in region 3" is meaningful whatever the current
placement is; "migrate fragment 7 from region 1 to region 3" is meaningful only
when fragment 7 happens to sit in region 1. Inapplicable actions resolve to a
no-op carrying a small fixed cost rather than a large penalty, so the agent
learns these are dull rather than dangerous.

Shape, with ``F = max_fragments`` and ``R = n_regions``::

    [0,       F*R)      MOVE_LEASE       index = f * R + r
    [F*R,   2*F*R)      MOVE_REPLICA_TO  index = f * R + r
    [2*F*R, 2*F*R+F)    SPLIT            index = f
    2*F*R+F             NOOP

At the default shape, F=20 and R=6, that is **261 actions**.

Why these three, and not the earlier five
-----------------------------------------
ADR-0009 fixes the replication factor and maps each action onto exactly one
CockroachDB statement, which rules three of the previous five out:

===================  ===========================================  ===========
Action               Statement                                    Cost tier
===================  ===========================================  ===========
``MOVE_LEASE``       ``ALTER RANGE <id> RELOCATE LEASE TO <s>``    one round
                                                                  trip, no
                                                                  bytes
``MOVE_REPLICA_TO``  ``ALTER RANGE <id> RELOCATE VOTERS ...``      one fragment
``SPLIT``            ``ALTER TABLE ... SPLIT AT VALUES (k)``       no bytes
===================  ===========================================  ===========

``ENSURE_REPLICA`` and ``DROP_REPLICA`` change the replication factor, which is
now fixed, so they are dead in every state: measured 0.0% applicable across
1,200 sampled states. ``MERGE`` has no synchronous counterpart on CockroachDB,
which offers only ``UNSPLIT`` into a background queue (ADR-0008).

``MOVE_LEASE`` is deliberately refused when the target region holds no replica,
because that is what the database enforces. The two placement blocks therefore
partition: for any ``(fragment, region)`` at most one of them is live. Fusing
them would raise applicability from 29.2% to 44.7% but would collapse the
cheap-lease / expensive-replica distinction that ADR-0009 chose CockroachDB to
obtain, so the density is declined on purpose.

Measured applicability, 1,200 states over five seeds at fixed RF 3 (see the
amendment to ADR-0002):

======================  =======  =============
Encoding                 Size     Applicable
======================  =======  =============
previous five-kind        401        22.1%
naive ``(f, from, to)``   861        22.9%
**this one**              **261**    **29.2%**
======================  =======  =============
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import numpy as np

from shardmind.catalog import FragmentCatalog, MutationResult


class ActionKind(IntEnum):
    """The three end states the agent can assert, plus doing nothing."""

    MOVE_LEASE = 0
    MOVE_REPLICA_TO = 1
    SPLIT = 2
    NOOP = 3


@dataclass(frozen=True)
class Action:
    """A decoded action. ``region`` is ``None`` for the fragment-only kinds."""

    kind: ActionKind
    fragment: int | None = None
    region: int | None = None

    def __str__(self) -> str:
        if self.kind is ActionKind.NOOP:
            return "NOOP"
        if self.region is None:
            return f"{self.kind.name}(f{self.fragment})"
        return f"{self.kind.name}(f{self.fragment}, r{self.region})"


class ActionSpace:
    """Bidirectional map between integers and :class:`Action` values."""

    #: Kinds that take a region argument, in index order.
    PLACEMENT_KINDS = (ActionKind.MOVE_LEASE, ActionKind.MOVE_REPLICA_TO)

    def __init__(self, max_fragments: int, n_regions: int) -> None:
        if max_fragments < 1 or n_regions < 1:
            raise ValueError("max_fragments and n_regions must be positive")
        self.max_fragments = int(max_fragments)
        self.n_regions = int(n_regions)

        self._placement_block = self.max_fragments * self.n_regions
        self._split_base = len(self.PLACEMENT_KINDS) * self._placement_block
        self._noop = self._split_base + self.max_fragments

    def __len__(self) -> int:
        return self.n

    @property
    def n(self) -> int:
        """Total number of actions."""
        return self._noop + 1

    # ---------------------------------------------------------------- coding

    def decode(self, index: int) -> Action:
        i = int(index)
        if not 0 <= i < self.n:
            raise IndexError(f"action {i} out of range [0, {self.n})")
        if i == self._noop:
            return Action(ActionKind.NOOP)
        if i >= self._split_base:
            return Action(ActionKind.SPLIT, fragment=i - self._split_base)

        kind = self.PLACEMENT_KINDS[i // self._placement_block]
        within = i % self._placement_block
        return Action(kind, fragment=within // self.n_regions, region=within % self.n_regions)

    def encode(self, kind: ActionKind, fragment: int | None = None,
               region: int | None = None) -> int:
        if kind is ActionKind.NOOP:
            return self._noop
        if fragment is None or not 0 <= fragment < self.max_fragments:
            raise ValueError(f"fragment must lie in [0, {self.max_fragments})")
        if kind is ActionKind.SPLIT:
            return self._split_base + fragment
        if region is None or not 0 <= region < self.n_regions:
            raise ValueError(f"region must lie in [0, {self.n_regions})")
        return (self.PLACEMENT_KINDS.index(kind) * self._placement_block
                + fragment * self.n_regions + region)

    def describe(self, index: int) -> str:
        return str(self.decode(index))

    # --------------------------------------------------------------- effects

    def apply(self, catalog: FragmentCatalog, index: int,
              rtt: np.ndarray) -> MutationResult:
        """Apply an action to a catalogue, in place.

        ``rtt`` is the region round-trip matrix, needed because
        ``MOVE_REPLICA_TO`` names only a destination and picks the evicted
        replica as the one farthest from it.

        Never raises for an out-of-range fragment: addressing a fragment that
        does not currently exist is exactly the inapplicable case the
        declarative semantics are designed to absorb.
        """
        action = self.decode(index)

        if action.kind is ActionKind.NOOP:
            return MutationResult(False, 0.0, "no-op")

        assert action.fragment is not None
        if action.fragment >= catalog.n_fragments:
            return MutationResult(False, 0.0, "fragment does not exist")

        if action.kind is ActionKind.SPLIT:
            return catalog.split(action.fragment)

        assert action.region is not None
        if action.kind is ActionKind.MOVE_LEASE:
            return catalog.move_lease(action.fragment, action.region)
        return catalog.move_replica_to(action.fragment, action.region, rtt)

    @property
    def noop_index(self) -> int:
        return self._noop
