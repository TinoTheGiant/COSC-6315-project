"""The two control baselines added for the CCGrid revision."""

import numpy as np
import pytest

from fragalloc.actions import ActionKind, ActionSpace
from fragalloc.config import FragAllocConfig
from fragalloc.policies import (ApplicableRandomPolicy, FollowTrafficPolicy,
                                ThrottledFollowPolicy)
from fragalloc.simulator import ClusterSimulator


def _sim(seed=3):
    cfg = FragAllocConfig()
    sim = ClusterSimulator(cfg)
    sim.reset(seed=seed)
    return sim, ActionSpace(cfg.catalog.max_fragments, cfg.n_regions)


def test_throttled_follow_starts_moves_only_on_multiples_of_every():
    sim, space = _sim()
    throttled, follow = ThrottledFollowPolicy(space, every=4), FollowTrafficPolicy(space)
    finish = False
    for window in range(24):
        if window % 4 == 0 or finish:
            expected = follow.act(sim)
            finish = space.decode(expected).kind is ActionKind.MOVE_REPLICA_TO
        else:
            expected = space.noop_index
        assert throttled.act(sim) == expected
        sim.step(expected)


def test_throttled_follow_finishes_a_two_window_relocation():
    sim, space = _sim()
    p, saw_finish = ThrottledFollowPolicy(space, every=8), False
    for window in range(200):
        a = p.act(sim)
        kind = space.decode(a).kind
        if window % 8 == 1 and kind is not ActionKind.NOOP:
            saw_finish = True
        sim.step(a)
        if sim.last.done:
            break
    assert saw_finish, "a lease move should follow a replica move off the throttle grid"


def test_throttled_follow_every_one_is_follow():
    sim, space = _sim()
    throttled, follow = ThrottledFollowPolicy(space, every=1), FollowTrafficPolicy(space)
    for _ in range(10):
        a = follow.act(sim)
        assert throttled.act(sim) == a
        sim.step(a)


def test_throttled_follow_reset_restarts_the_count():
    sim, space = _sim()
    p = ThrottledFollowPolicy(space, every=3)
    p.act(sim)
    p.reset()
    assert p.act(sim) == FollowTrafficPolicy(space).act(sim)


def test_throttled_follow_rejects_zero():
    _, space = _sim()
    with pytest.raises(ValueError):
        ThrottledFollowPolicy(space, every=0)


def test_applicable_random_only_draws_applicable_non_noop_actions():
    sim, space = _sim()
    p = ApplicableRandomPolicy(space, seed=7)
    for _ in range(60):
        mask = space.applicable_mask(sim.catalog)
        a = p.act(sim)
        assert mask[a] and a != space.noop_index
        assert sim.step(a).mutation.applied


def test_applicable_random_is_reproducible_after_reset():
    sim, space = _sim()
    p = ApplicableRandomPolicy(space, seed=7)
    first = [p.act(sim) for _ in range(5)]
    p.reset()
    assert [p.act(sim) for _ in range(5)] == first
