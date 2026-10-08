"""The flat action space: the coding, and the promise that nothing ever raises."""

from __future__ import annotations

import numpy as np
import pytest

from shardmind.actions import Action, ActionKind, ActionSpace
from shardmind.catalog import FragmentCatalog


@pytest.fixture
def space(tiny_config) -> ActionSpace:
    return ActionSpace(tiny_config.catalog.max_fragments, tiny_config.n_regions)


def test_size_matches_the_documented_formula(space, tiny_config) -> None:
    f, r = tiny_config.catalog.max_fragments, tiny_config.n_regions
    assert space.n == 3 * f * r + 2 * f + 1
    assert len(space) == space.n


def test_the_default_configuration_stays_within_a_few_hundred_actions(default_config) -> None:
    space = ActionSpace(default_config.catalog.max_fragments, default_config.n_regions)
    assert space.n == 401


def test_encode_and_decode_are_inverse(space) -> None:
    for index in range(space.n):
        action = space.decode(index)
        assert space.encode(action.kind, action.fragment, action.region) == index


def test_every_index_decodes_to_a_distinct_action(space) -> None:
    decoded = {(a.kind, a.fragment, a.region) for a in map(space.decode, range(space.n))}
    assert len(decoded) == space.n


def test_all_six_kinds_are_reachable(space) -> None:
    kinds = {space.decode(i).kind for i in range(space.n)}
    assert kinds == set(ActionKind)


def test_noop_is_the_last_index(space) -> None:
    assert space.noop_index == space.n - 1
    assert space.decode(space.noop_index).kind is ActionKind.NOOP


def test_out_of_range_indices_are_rejected(space) -> None:
    with pytest.raises(IndexError):
        space.decode(space.n)
    with pytest.raises(IndexError):
        space.decode(-1)


def test_encoding_rejects_impossible_targets(space, tiny_config) -> None:
    with pytest.raises(ValueError, match="fragment"):
        space.encode(ActionKind.SPLIT, fragment=tiny_config.catalog.max_fragments)
    with pytest.raises(ValueError, match="region"):
        space.encode(ActionKind.SET_PRIMARY, fragment=0, region=tiny_config.n_regions)


def test_describe_is_readable(space) -> None:
    text = space.describe(space.encode(ActionKind.SET_PRIMARY, 2, 3))
    assert text == "SET_PRIMARY(f2, r3)"
    assert str(Action(ActionKind.NOOP)) == "NOOP"


# ------------------------------------------------------------ applicability


def test_no_action_ever_raises_in_any_reachable_state(space, tiny_config) -> None:
    """The central promise of declarative semantics.

    DQN cannot mask invalid actions, so the environment must define every one of
    them in every state. This walks a long random trajectory and fires every
    action index at every state visited, checking that nothing raises and no
    invariant breaks.
    """
    catalog = FragmentCatalog(
        tiny_config.catalog, tiny_config.workload.n_cells, tiny_config.n_regions
    )
    rng = np.random.default_rng(0)

    for _ in range(40):
        probe = catalog.copy()
        for index in range(space.n):
            trial = probe.copy()
            space.apply(trial, index)
            trial.validate()
        space.apply(catalog, int(rng.integers(space.n)))
        catalog.validate()


def test_addressing_a_fragment_that_does_not_exist_is_a_quiet_no_op(space, tiny_config) -> None:
    catalog = FragmentCatalog(
        tiny_config.catalog, tiny_config.workload.n_cells, tiny_config.n_regions
    )
    beyond = catalog.n_fragments  # exists in the action space, not in the catalogue
    index = space.encode(ActionKind.SET_PRIMARY, fragment=beyond, region=0)
    result = space.apply(catalog, index)
    assert not result.applied
    assert result.reason == "fragment does not exist"
    assert result.bytes_moved == 0.0


def test_the_inapplicable_residue_is_bounded_and_understood(space, tiny_config) -> None:
    """Quantify the residue rather than assume it away.

    In the initial state, of the actions addressing a fragment that exists,
    roughly half apply. The shortfall is concentrated and explainable:

    * ``SET_PRIMARY`` refuses only the incumbent, so 5 of 6 apply;
    * ``ENSURE_REPLICA`` refuses the regions already holding a replica;
    * ``DROP_REPLICA`` refuses everything, because a freshly built catalogue
      sits exactly at ``min_replicas`` and has nothing to give up.

    The last of those is the interesting one: the drop action is dead at the
    start and becomes live only once the agent has over-replicated something.
    That is a real property of the action space, recorded in ADR-0002, and the
    fraction of no-op steps is worth watching as a training diagnostic.
    """
    catalog = FragmentCatalog(
        tiny_config.catalog, tiny_config.workload.n_cells, tiny_config.n_regions
    )
    n_frag, n_regions = catalog.n_fragments, tiny_config.n_regions

    by_kind: dict[ActionKind, int] = {kind: 0 for kind in ActionKind}
    addressable = 0
    for index in range(space.n):
        action = space.decode(index)
        if action.fragment is not None and action.fragment >= n_frag:
            continue
        addressable += 1
        trial = catalog.copy()
        if space.apply(trial, index).applied:
            by_kind[action.kind] += 1

    assert by_kind[ActionKind.SET_PRIMARY] == n_frag * (n_regions - 1)
    assert by_kind[ActionKind.DROP_REPLICA] == 0, "nothing to drop at min_replicas"
    assert by_kind[ActionKind.SPLIT] == n_frag
    assert by_kind[ActionKind.MERGE] == n_frag - 1
    assert sum(by_kind.values()) / addressable > 0.5


def test_dropping_a_replica_becomes_possible_once_one_is_added(space, tiny_config) -> None:
    catalog = FragmentCatalog(
        tiny_config.catalog, tiny_config.workload.n_cells, tiny_config.n_regions
    )
    spare = int(np.flatnonzero(~catalog.replicas[0])[0])
    assert not space.apply(catalog.copy(), space.encode(ActionKind.DROP_REPLICA, 0, spare)).applied

    space.apply(catalog, space.encode(ActionKind.ENSURE_REPLICA, 0, spare))
    assert space.apply(catalog, space.encode(ActionKind.DROP_REPLICA, 0, spare)).applied


def test_split_and_merge_reach_the_catalogue(space, tiny_config) -> None:
    catalog = FragmentCatalog(
        tiny_config.catalog, tiny_config.workload.n_cells, tiny_config.n_regions
    )
    before = catalog.n_fragments
    assert space.apply(catalog, space.encode(ActionKind.SPLIT, fragment=0)).applied
    assert catalog.n_fragments == before + 1
    assert space.apply(catalog, space.encode(ActionKind.MERGE, fragment=0)).applied
    assert catalog.n_fragments == before
