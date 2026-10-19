"""Reference policies used to exercise and sanity-check the environment.

These are NOT the Phase 2 baselines. They exist so the environment can be
driven without an agent and so the tests have something whose behaviour is
predictable. The characterized baselines -- consistent hashing, nearest-region,
threshold rebalancing and a Lion-style cost-model rebalancer -- belong in
``shardmind/baselines/`` and are scheduled for week 3.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

from shardmind.actions import ActionKind, ActionSpace
from shardmind.simulator import ClusterSimulator


class Policy(Protocol):
    """Anything that can choose an action index given the simulator's state."""

    def act(self, sim: ClusterSimulator) -> int: ...

    def reset(self) -> None: ...


class StaticHashPolicy:
    """Never acts. This is what a production database does today.

    Named for what it *is*, not for what it omits: the initial placement is
    what a consistent-hash partitioner produces, and the policy holds that
    placement for the whole episode. Every other policy is measured against it.

    It is the floor every learned policy must clear, and the cleanest
    statement of the problem: a fixed schema does not notice that the workload
    has migrated away from it.
    """

    def __init__(self, action_space: ActionSpace) -> None:
        self._noop = action_space.noop_index

    def act(self, sim: ClusterSimulator) -> int:
        return self._noop

    def reset(self) -> None:
        return None


class RandomPolicy:
    """Uniform over the action space. The ceiling on how bad churn can get."""

    def __init__(self, action_space: ActionSpace, seed: int = 0) -> None:
        self.action_space = action_space
        self._seed = seed
        self._rng = np.random.default_rng(seed)

    def act(self, sim: ClusterSimulator) -> int:
        return int(self._rng.integers(self.action_space.n))

    def reset(self) -> None:
        self._rng = np.random.default_rng(self._seed)


class FollowTrafficPolicy:
    """Move the worst-placed fragment's primary towards its traffic.

    The name states the rule: each window it follows the traffic for one
    fragment and nothing else. It is the simple reactive heuristic an operator
    would write by hand, and the first thing a learned policy has to beat.

    Each window it scores every fragment by the latency its current primary
    costs relative to the best available region, and issues a single action for
    the worst offender. It is myopic by construction: it weighs no migration
    cost and anticipates no drift, so it churns under volatility. Its purpose
    here is to demonstrate that the reward signal points somewhere -- a policy
    that follows the traffic should beat one that does not -- not to serve as a
    serious opponent.

    **It takes two windows to do what it used to do in one.** Under the action
    space of ADR-0002 as amended, a lease can only move to a region that
    already holds a replica, because that is what CockroachDB enforces. So when
    the best region holds no replica this policy must first issue
    ``MOVE_REPLICA_TO`` and only then, next window, ``MOVE_LEASE``. The earlier
    ``SET_PRIMARY`` fused both into one step, which no single cluster statement
    can do. The baseline is slower as a result, and that is the honest
    comparison: the baseline and the agent must share an action space or the
    contest is rigged.
    """

    def __init__(self, action_space: ActionSpace) -> None:
        self.action_space = action_space

    def act(self, sim: ClusterSimulator) -> int:
        catalog = sim.catalog
        rtt = sim.topology.rtt
        window = sim.last.window

        demand = catalog.aggregate_cells(window.reads + window.writes)  # (F, R)
        cost_by_target = demand @ rtt  # (F, R): total ms if region r held it
        best_region = cost_by_target.argmin(axis=1)
        current = cost_by_target[np.arange(catalog.n_fragments), catalog.primary]
        gain = current - cost_by_target[np.arange(catalog.n_fragments), best_region]

        if not np.any(gain > 0.0):
            return self.action_space.noop_index
        fragment = int(gain.argmax())
        target = int(best_region[fragment])

        # A lease only moves to a region already holding a replica. If the best
        # region holds none, put one there first and take the lease next window.
        if catalog.replicas[fragment, target]:
            return self.action_space.encode(
                ActionKind.MOVE_LEASE, fragment=fragment, region=target)
        return self.action_space.encode(
            ActionKind.MOVE_REPLICA_TO, fragment=fragment, region=target)

    def reset(self) -> None:
        return None


def rollout(sim: ClusterSimulator, policy: Policy, seed: int | None = None) -> list[dict[str, float]]:
    """Run one full episode under ``policy`` and return the per-step records."""
    sim.reset(seed=seed)
    policy.reset()
    records = [sim.snapshot()]
    while not sim.last.done:
        sim.step(policy.act(sim))
        records.append(sim.snapshot())
    return records
