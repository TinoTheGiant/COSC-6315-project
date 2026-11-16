"""Reference policies used to exercise and sanity-check the environment.

These are NOT the Phase 2 baselines. They exist so the environment can be
driven without an agent and so the tests have something whose behaviour is
predictable. The characterized baselines -- consistent hashing, nearest-region,
threshold rebalancing and a Lion-style cost-model rebalancer -- belong in
``fragalloc/baselines/`` and are scheduled for week 3.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

from fragalloc.actions import ActionKind, ActionSpace
from fragalloc.simulator import ClusterSimulator


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


class ThrottledFollowPolicy:
    """Follow traffic, but start a move only every ``every`` windows.

    A control for the agent's main result. The agent moves about a fifth of the
    data follow traffic moves; this asks whether simply slowing the heuristic
    down buys the same trade, in which case the trade is not something the
    agent learned.

    Follow traffic often needs two windows for one relocation: a replica move,
    then the lease move onto it. A throttle that cut that pair in half would
    pay for the copy and never collect the latency, which would make the
    control look worse than slowing the heuristic really is. So a window right
    after a replica move is always allowed to act.
    """

    def __init__(self, action_space: ActionSpace, every: int) -> None:
        if every < 1:
            raise ValueError("every must be at least 1")
        self.action_space = action_space
        self.every = every
        self._follow = FollowTrafficPolicy(action_space)
        self._window = 0
        self._finish = False

    def act(self, sim: ClusterSimulator) -> int:
        window, self._window = self._window, self._window + 1
        if window % self.every and not self._finish:
            return self.action_space.noop_index
        action = self._follow.act(sim)
        self._finish = self.action_space.decode(action).kind is ActionKind.MOVE_REPLICA_TO
        return action

    def reset(self) -> None:
        self._window = 0
        self._finish = False


class ApplicableRandomPolicy:
    """Uniform over the actions that are applicable in the current state.

    The plain random baseline draws from all 261 actions, so most of its draws
    change nothing. This one draws only from moves that change the placement,
    which is the fair control for "moving data without looking at the traffic".
    """

    def __init__(self, action_space: ActionSpace, seed: int = 0) -> None:
        self.action_space = action_space
        self._seed = seed
        self._rng = np.random.default_rng(seed)

    def act(self, sim: ClusterSimulator) -> int:
        mask = self.action_space.applicable_mask(sim.catalog)
        mask[self.action_space.noop_index] = False
        legal = np.flatnonzero(mask)
        if legal.size == 0:
            return self.action_space.noop_index
        return int(self._rng.choice(legal))

    def reset(self) -> None:
        self._rng = np.random.default_rng(self._seed)


def rollout(sim: ClusterSimulator, policy: Policy, seed: int | None = None) -> list[dict[str, float]]:
    """Run one full episode under ``policy`` and return the per-step records."""
    sim.reset(seed=seed)
    policy.reset()
    records = [sim.snapshot()]
    while not sim.last.done:
        sim.step(policy.act(sim))
        records.append(sim.snapshot())
    return records


class LionStylePolicy:
    """A co-location rebalancer after Lion (Lion.pdf, sections III and IV-A/B).

    Lion minimises distributed transactions by placing the partitions that are
    accessed together on one node, choosing that node with a cost model that
    prefers a node already holding secondary replicas (a cheap remaster) over
    one that would need data copied (a migration), then rebalancing load.
    This is that planner, adapted to this action space and stated plainly:

    1. **Workload analysis.** Every ``replan_every`` windows, build the
       co-access graph of fragments from the window's transaction counts
       (vertices weighted by accesses, edges by co-accessing transactions) and
       grow clumps greedily from the hottest unvisited fragment, admitting a
       neighbour when its edge weight is at least ``alpha`` times the seed's
       strongest edge.
    2. **Plan generation.** Place each clump on the region minimising Lion's
       Equation 3, ``w_r * sum cnt_r + w_m * sum cnt_m``, where ``cnt_r`` is
       ``1 + log2(f + 1)`` for a fragment whose replica there is secondary
       (``f`` its normalised access frequency) and ``cnt_m`` is 1 for a
       fragment with no replica there. Then, while a region's clump load
       exceeds ``theta`` times the mean, move its lightest clump to the
       cheapest region under the mean (Lion's second step).
    3. **Execution.** The difference between plan and placement becomes a
       queue of ``MOVE_REPLICA_TO`` and ``MOVE_LEASE`` actions, issued one per
       window, the same budget as every other policy here.

    Two deliberate departures, both in Lion's disfavour and both to keep the
    comparison fair: the workload-prediction component (pre-replication) is
    omitted, and Lion's objective has **no term for where clients are**,
    because Lion targets nodes in one data centre. The second is the point of
    including it: it shows what co-location alone buys when the cost is
    geographic.
    """

    def __init__(self, action_space: ActionSpace, *, replan_every: int = 10,
                 alpha: float = 0.3, theta: float = 1.5, w_remaster: float = 1.0,
                 w_migrate: float = 5.0) -> None:
        self.action_space = action_space
        self.replan_every, self.alpha, self.theta = replan_every, alpha, theta
        self.w_r, self.w_m = w_remaster, w_migrate
        self.reset()

    def reset(self) -> None:
        self._queue: list[tuple[int, int, int]] = []   # (kind, fragment, region)
        self._windows = 0
        self._plan_boundaries: list[int] | None = None

    # ---------------------------------------------------------------- analysis

    @staticmethod
    def coaccess(catalog, generator, window) -> tuple[np.ndarray, np.ndarray]:
        """``(F,)`` access weight and ``(F, F)`` co-access weight."""
        n = catalog.n_fragments
        cell_to_frag = catalog.cell_to_fragment()
        vertex = catalog.aggregate_cells(window.reads + window.writes).sum(axis=1)
        edges = np.zeros((n, n))
        per_template = window.txn_counts.sum(axis=1)
        for t, count in enumerate(per_template):
            if count <= 0:
                continue
            frags = np.unique(cell_to_frag[generator.template_cells[t]])
            vertex[frags] += count
            for i in frags:
                for j in frags:
                    if i != j:
                        edges[i, j] += count
        return vertex, edges

    def clumps(self, vertex: np.ndarray, edges: np.ndarray) -> list[list[int]]:
        unvisited = set(range(vertex.size))
        out = []
        for seed in np.argsort(-vertex, kind="stable"):
            seed = int(seed)
            if seed not in unvisited:
                continue
            unvisited.discard(seed)
            clump, frontier = [seed], [seed]
            strongest = edges[seed].max()
            while frontier:
                v = frontier.pop()
                for u in np.flatnonzero(edges[v] >= max(self.alpha * strongest, 1e-12)):
                    u = int(u)
                    if u in unvisited and edges[v, u] > 0:
                        unvisited.discard(u)
                        clump.append(u)
                        frontier.append(u)
            out.append(sorted(clump))
        return out

    # ---------------------------------------------------------------- planning

    def placement_cost(self, catalog, clump: list[int], region: int,
                       freq: np.ndarray) -> float:
        cost = 0.0
        for f in clump:
            if catalog.primary[f] == region:
                continue                                   # already the primary
            if catalog.replicas[f, region]:
                cost += self.w_r * (1.0 + np.log2(freq[f] + 1.0))
            else:
                cost += self.w_m
        return cost

    def plan(self, catalog, generator, window) -> dict[int, int]:
        """Destination region for every fragment."""
        vertex, edges = self.coaccess(catalog, generator, window)
        freq = vertex / vertex.sum() if vertex.sum() > 0 else vertex
        n_regions = catalog.replicas.shape[1]
        groups = self.clumps(vertex, edges)
        cost = np.array([[self.placement_cost(catalog, c, r, freq) for r in range(n_regions)]
                         for c in groups])
        dest = cost.argmin(axis=1)
        weight = np.array([vertex[c].sum() for c in groups])
        # Lion's second step: shed load from overloaded regions.
        for _ in range(len(groups) * n_regions):
            load = np.bincount(dest, weights=weight, minlength=n_regions)
            mean = load.mean()
            over = int(load.argmax())
            if mean <= 0 or load[over] <= self.theta * mean:
                break
            movable = [i for i in np.argsort(weight) if dest[i] == over]
            under = [r for r in range(n_regions) if load[r] < mean]
            moved = False
            for i in movable:
                r = min(under, key=lambda r: (cost[i, r], r))
                if load[r] + weight[i] <= self.theta * mean:
                    dest[i] = r
                    moved = True
                    break
            if not moved:
                break
        return {f: int(dest[i]) for i, c in enumerate(groups) for f in c}

    # ---------------------------------------------------------------- acting

    def act(self, sim) -> int:
        catalog, window = sim.catalog, sim.last.window
        boundaries = catalog.boundaries.tolist()
        if self._windows % self.replan_every == 0 or boundaries != self._plan_boundaries:
            dest = self.plan(catalog, sim.generator, window)
            self._plan_boundaries = boundaries
            # Hottest fragments first: their placement matters most.
            self._queue = []
            for f, r in dest.items():
                if catalog.primary[f] == r:
                    continue
                if not catalog.replicas[f, r]:
                    self._queue.append((int(ActionKind.MOVE_REPLICA_TO), f, r))
                self._queue.append((int(ActionKind.MOVE_LEASE), f, r))
        self._windows += 1
        mask = self.action_space.applicable_mask(catalog)
        while self._queue:
            kind, f, r = self._queue.pop(0)
            index = self.action_space.encode(ActionKind(kind), fragment=f, region=r)
            if mask[index]:
                return index
        return self.action_space.noop_index
