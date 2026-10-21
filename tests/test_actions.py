"""The flat action space: the coding, and the promise that nothing ever raises."""

from __future__ import annotations

import numpy as np
import pytest

from fragalloc.actions import Action, ActionKind, ActionSpace
from fragalloc.catalog import FragmentCatalog
from fragalloc.topology import build_topology


@pytest.fixture
def space(tiny_config) -> ActionSpace:
    return ActionSpace(tiny_config.catalog.max_fragments, tiny_config.n_regions)


@pytest.fixture
def rtt(tiny_config) -> np.ndarray:
    return build_topology(tiny_config.topology, tiny_config.catalog.dataset_bytes).rtt


@pytest.fixture
def catalog(tiny_config) -> FragmentCatalog:
    return FragmentCatalog(
        tiny_config.catalog, tiny_config.workload.n_cells, tiny_config.n_regions
    )


# ------------------------------------------------------------------- coding


def test_size_matches_the_documented_formula(space, tiny_config) -> None:
    f, r = tiny_config.catalog.max_fragments, tiny_config.n_regions
    assert space.n == 2 * f * r + f + 1
    assert len(space) == space.n


def test_the_default_configuration_stays_within_a_few_hundred_actions(default_config) -> None:
    """261, down from 401. The amendment to ADR-0002 records the measurement
    that chose this shape over the naive 861-action alternative."""
    space = ActionSpace(default_config.catalog.max_fragments, default_config.n_regions)
    assert space.n == 261


def test_encode_and_decode_are_inverse(space) -> None:
    for index in range(space.n):
        action = space.decode(index)
        assert space.encode(action.kind, action.fragment, action.region) == index


def test_every_index_decodes_to_a_distinct_action(space) -> None:
    decoded = {(a.kind, a.fragment, a.region) for a in map(space.decode, range(space.n))}
    assert len(decoded) == space.n


def test_all_kinds_are_reachable(space) -> None:
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
        space.encode(ActionKind.MOVE_LEASE, fragment=0, region=tiny_config.n_regions)


def test_describe_is_readable(space) -> None:
    assert space.describe(space.encode(ActionKind.MOVE_LEASE, 2, 3)) == "MOVE_LEASE(f2, r3)"
    assert str(Action(ActionKind.NOOP)) == "NOOP"


# ------------------------------------------------------------ applicability


def test_no_action_ever_raises_in_any_reachable_state(space, catalog, rtt) -> None:
    """The central promise of declarative semantics.

    DQN cannot mask invalid actions, so the environment must define every one
    of them in every state. This walks a trajectory and fires every action
    index at every state visited, checking that nothing raises and no invariant
    breaks.
    """
    rng = np.random.default_rng(0)
    for _ in range(40):
        probe = catalog.copy()
        for index in range(space.n):
            trial = probe.copy()
            space.apply(trial, index, rtt)
            trial.validate()
        space.apply(catalog, int(rng.integers(space.n)), rtt)
        catalog.validate()


def test_addressing_a_fragment_that_does_not_exist_is_a_quiet_no_op(
    space, catalog, rtt
) -> None:
    beyond = catalog.n_fragments  # exists in the action space, not the catalogue
    result = space.apply(catalog, space.encode(ActionKind.MOVE_LEASE, beyond, 0), rtt)
    assert not result.applied
    assert result.reason == "fragment does not exist"
    assert result.bytes_moved == 0.0


def test_the_two_placement_blocks_partition(space, catalog, rtt) -> None:
    """For any (fragment, region) at most one placement action is live.

    This is what the restriction on MOVE_LEASE buys. A lease moves only to a
    region that already holds a replica; MOVE_REPLICA_TO applies only where one
    does not. The sole dead case is the region that is already primary, which
    is both held and occupied.
    """
    for f in range(catalog.n_fragments):
        for r in range(catalog.n_regions):
            lease = space.apply(catalog.copy(), space.encode(ActionKind.MOVE_LEASE, f, r), rtt)
            move = space.apply(catalog.copy(), space.encode(ActionKind.MOVE_REPLICA_TO, f, r), rtt)
            assert not (lease.applied and move.applied), f"both live at f{f} r{r}"
            if int(catalog.primary[f]) == r:
                assert not lease.applied and not move.applied
            else:
                assert lease.applied or move.applied, f"neither live at f{f} r{r}"


def test_a_lease_never_moves_data(space, catalog, rtt) -> None:
    """The cheap tier stays cheap. If a lease move could acquire a replica it
    would cost a fragment, and the two-tier reward structure ADR-0009 depends
    on would collapse into one flat migration penalty."""
    for f in range(catalog.n_fragments):
        for r in range(catalog.n_regions):
            before = catalog.replicas.copy()
            trial = catalog.copy()
            result = space.apply(trial, space.encode(ActionKind.MOVE_LEASE, f, r), rtt)
            assert result.bytes_moved == 0.0
            np.testing.assert_array_equal(trial.replicas, before)


def test_a_replica_move_holds_the_replication_factor_constant(space, catalog, rtt) -> None:
    """ADR-0009 fixes RF, so acquiring a replica must release one."""
    for f in range(catalog.n_fragments):
        for r in range(catalog.n_regions):
            trial = catalog.copy()
            before = int(trial.replica_counts[f])
            space.apply(trial, space.encode(ActionKind.MOVE_REPLICA_TO, f, r), rtt)
            assert int(trial.replica_counts[f]) == before
            trial.validate()


def test_the_evicted_replica_is_the_one_farthest_from_the_target(catalog, rtt) -> None:
    """The source tie-break is part of the action's meaning, not an internal
    detail: the agent names only a destination, so this is what it gets."""
    f = 0
    target = int(np.flatnonzero(~catalog.replicas[f])[0])
    held = [r for r in range(catalog.n_regions)
            if catalog.replicas[f, r] and r != int(catalog.primary[f])]
    expected = max(held, key=lambda r: float(rtt[r, target]))

    assert catalog.move_replica_to(f, target, rtt).applied
    assert not catalog.replicas[f, expected], "farthest non-primary replica should go"
    assert catalog.replicas[f, target]


def test_a_replica_move_costs_the_fragment(space, catalog, rtt) -> None:
    f = 0
    target = int(np.flatnonzero(~catalog.replicas[f])[0])
    result = space.apply(catalog, space.encode(ActionKind.MOVE_REPLICA_TO, f, target), rtt)
    assert result.applied
    assert result.bytes_moved == pytest.approx(float(catalog.sizes_bytes[f]))


def test_split_reaches_the_catalogue(space, catalog, rtt) -> None:
    """There is no MERGE. CockroachDB offers only UNSPLIT into a background
    queue (ADR-0008), so shard count is monotone within an episode."""
    before = catalog.n_fragments
    assert space.apply(catalog, space.encode(ActionKind.SPLIT, fragment=0), rtt).applied
    assert catalog.n_fragments == before + 1
    assert not hasattr(ActionKind, "MERGE")


def test_the_inapplicable_residue_is_bounded_and_understood(space, catalog, rtt) -> None:
    """Quantify the residue rather than assume it away.

    Of the actions addressing a fragment that exists, the live fraction is
    concentrated and explainable: each fragment offers (RF - 1) lease moves,
    (R - RF) replica moves, and one split. Measured across 1,200 states at the
    default shape the mean is 29.2%, which the amendment to ADR-0002 records
    against 22.1% for the previous five-kind space.
    """
    n_frag, n_reg = catalog.n_fragments, catalog.n_regions
    rf = int(catalog.replica_counts[0])

    by_kind: dict[ActionKind, int] = {kind: 0 for kind in ActionKind}
    addressable = 0
    for index in range(space.n):
        action = space.decode(index)
        if action.fragment is not None and action.fragment >= n_frag:
            continue
        addressable += 1
        if space.apply(catalog.copy(), index, rtt).applied:
            by_kind[action.kind] += 1

    assert by_kind[ActionKind.MOVE_LEASE] == n_frag * (rf - 1)
    assert by_kind[ActionKind.MOVE_REPLICA_TO] == n_frag * (n_reg - rf)
    assert by_kind[ActionKind.SPLIT] == n_frag
    assert 0.25 < sum(by_kind.values()) / addressable < 0.75
