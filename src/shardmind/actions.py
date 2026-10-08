"""The flat, declarative action space.

DQN estimates a value for every action in a fixed discrete set and offers no
mechanism for masking the ones that do not apply. Two consequences follow, and
both shape the design here.

First, the space must be flat. A factored action -- choose a fragment, then an
operation, then a target -- would need either an architecture that DQN does not
have or a decomposition that breaks the Q-value's meaning. So every
``(operation, fragment, region)`` triple gets its own index. With twenty
fragments and six regions that is 401 actions, small enough for a single output
layer.

Second, actions are named as desired end states rather than as operations.
"Make region 3 the primary of fragment 7" is meaningful whatever the current
placement is; "migrate fragment 7 from region 1 to region 3" is meaningful only
when fragment 7 happens to sit in region 1. Under declarative semantics almost
every action is applicable in almost every state, so the value function is not
learning to avoid a shifting minefield of invalid indices. The residue that
genuinely cannot apply -- splitting when already at the fragment cap, addressing
a fragment index beyond the current count -- resolves to a no-op carrying a small
fixed cost rather than a large penalty, so the agent learns these are dull
rather than dangerous.

Layout, with ``F = max_fragments`` and ``R = n_regions``::

    [0,        F*R)      SET_PRIMARY     index = f * R + r
    [F*R,     2*F*R)     ENSURE_REPLICA
    [2*F*R,   3*F*R)     DROP_REPLICA
    [3*F*R,   3*F*R+F)   SPLIT           index = f
    [3*F*R+F, 3*F*R+2F)  MERGE           index = f  (absorbs f+1)
    3*F*R+2F             NOOP
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from shardmind.catalog import FragmentCatalog, MutationResult


class ActionKind(IntEnum):
    """The five end states the agent can assert, plus doing nothing."""

    SET_PRIMARY = 0
    ENSURE_REPLICA = 1
    DROP_REPLICA = 2
    SPLIT = 3
    MERGE = 4
    NOOP = 5


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

    def __init__(self, max_fragments: int, n_regions: int) -> None:
        if max_fragments < 1 or n_regions < 1:
            raise ValueError("max_fragments and n_regions must be positive")
        self.max_fragments = int(max_fragments)
        self.n_regions = int(n_regions)

        self._placement_block = self.max_fragments * self.n_regions
        self._split_base = 3 * self._placement_block
        self._merge_base = self._split_base + self.max_fragments
        self._noop = self._merge_base + self.max_fragments

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
        if i >= self._merge_base:
            return Action(ActionKind.MERGE, fragment=i - self._merge_base)
        if i >= self._split_base:
            return Action(ActionKind.SPLIT, fragment=i - self._split_base)

        kind = ActionKind(i // self._placement_block)
        within = i % self._placement_block
        return Action(kind, fragment=within // self.n_regions, region=within % self.n_regions)

    def encode(self, kind: ActionKind, fragment: int | None = None, region: int | None = None) -> int:
        if kind is ActionKind.NOOP:
            return self._noop
        if fragment is None or not 0 <= fragment < self.max_fragments:
            raise ValueError(f"fragment must lie in [0, {self.max_fragments})")
        if kind is ActionKind.SPLIT:
            return self._split_base + fragment
        if kind is ActionKind.MERGE:
            return self._merge_base + fragment
        if region is None or not 0 <= region < self.n_regions:
            raise ValueError(f"region must lie in [0, {self.n_regions})")
        return int(kind) * self._placement_block + fragment * self.n_regions + region

    def describe(self, index: int) -> str:
        return str(self.decode(index))

    # --------------------------------------------------------------- effects

    def apply(self, catalog: FragmentCatalog, index: int) -> MutationResult:
        """Apply an action to a catalogue, in place.

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
        if action.kind is ActionKind.MERGE:
            return catalog.merge(action.fragment)

        assert action.region is not None
        if action.kind is ActionKind.SET_PRIMARY:
            return catalog.set_primary(action.fragment, action.region)
        if action.kind is ActionKind.ENSURE_REPLICA:
            return catalog.ensure_replica(action.fragment, action.region)
        return catalog.drop_replica(action.fragment, action.region)

    @property
    def noop_index(self) -> int:
        return self._noop
