# MDP specification

**Status:** week 1 deliverable. Satisfies Objective 1.
**Date:** 2026-09-20
**Implements:** `fragalloc.simulator`, `fragalloc.env`, `fragalloc.cost`

This document states the control problem formally and records where each design
choice answers a limitation in the base papers. Every symbol here corresponds to
something in the code, and the correspondence is named at the end of each
section.

---

## 1. The problem, informally

A dataset is spread over `R` geographic regions. Requests arrive continuously
and are tagged with the region they originate from. The geographic centre of
gravity of those requests moves: slowly and cyclically over a diurnal period,
abruptly during localized events.

An agent observes the traffic and the current layout, and at fixed intervals
issues one instruction changing how the data is fragmented or where a fragment
sits. It is trying to minimize the latency users experience, while not moving
so much data that the cure costs more than the disease.

---

## 2. Formal definition

The problem is a Markov Decision Process `(S, A, P, r, gamma)` over discrete
decision windows `t = 0, 1, 2, ...`.

### 2.1 Underlying objects

| Symbol | Meaning | Default |
|--------|---------|---------|
| `R` | regions | 6 |
| `K` | keyspace cells, the atomic unit of data | 256 |
| `F_max` | fragment cap | 20 |
| `F_t` | fragments at window `t`, `1 <= F_t <= F_max` | starts at 6 |
| `L` | `R x R` inter-region RTT matrix, milliseconds, symmetric | `topology.DEFAULT_RTT_MS` |
| `phi_r` | angular position of region `r`, from its longitude | |
| `psi_k` | angular position of cell `k` | correlated random walk |
| `p_k` | popularity of cell `k`, summing to 1 | Zipf, `s = 0.9` |

A **fragment** is a contiguous half-open run of cells `[b_i, b_{i+1})`. The
catalogue is therefore a strictly increasing boundary vector
`b_0 = 0 < b_1 < ... < b_{F_t} = K`, a primary region per fragment, and a
replica set per fragment.

### 2.2 Workload process

The workload is **exogenous**: it depends on `t` and the seed, never on the
agent's actions (ADR-0006). At window `t` the angular field is rotated by

```
theta(t) = 2*pi * laps * nu * t / T
```

with `T` the diurnal period in windows (96), `laps` the revolutions per period
(1) and `nu` the volatility (the primary sweep dimension). The intensity of
traffic from region `r` to cell `k` is

```
lambda(k, r, t)  proportional to  p_k * exp(kappa * cos(psi_k + theta(t) - phi_r)) * s(r, t)
```

normalized to sum to one over `(k, r)`. `kappa` is a von Mises concentration
controlling how tightly a cell's traffic clusters geographically;
`s(r, t) >= 1` is a localized spike multiplier, drawn as a Poisson-like process
whose rate and magnitude also scale with `nu`.

A fraction `1 - txn_fraction` of requests are single-key operations, split into
reads and writes by `read_fraction`. The remainder are **transactions** drawn
from a fixed set of `T_n` templates, each a set of `arity` co-accessed cells
with fixed read/write roles, standing in for a TPC-C-style transaction class.

### 2.3 State space `S`

The full state is the tuple

```
s_t = ( catalogue_t , demand_t , churn_t , t )
```

where `catalogue_t` is the boundary vector, primary vector and replica matrix;
`demand_t` is the `(K, R)` read and write counts and the `(T_n, R)` transaction
counts of the window just served; and `churn_t` is the recent per-window
migration volume.

The agent does not see `s_t` directly. It sees an encoding `o_t` in `[0, 1]^d`,
`d = 703` at the default configuration. The blocks are, in order: per-fragment
read, write and transaction demand by origin region (`3 * F_max * R`), the
replica matrix and primary one-hot (`2 * F_max * R`), a fragment active mask and
size vector (`2 * F_max`), per-region served-operation share and storage
utilization (`2R`), recent churn (`8`), the latency matrix (`R^2`), and seven
scalars: mean and tail latency, cross-region transaction fraction, load and
storage imbalance, fragment count and episode progress.

Everything is normalized into the unit interval, and fragment-indexed blocks are
padded to `F_max` with an explicit active mask, because the fragment count is
itself something the agent changes while the observation width cannot.

**This is where Lion's first gap is answered.** Lion's cost model is expressed in
bytes moved and contains no notion of where a request came from. Here, the
geographic access distribution is three of the twelve observation blocks and the
latency matrix is a fourth.

**Partial observability.** The rotation phase `theta(t)` is not in the
observation. The agent can infer drift only from the demand history it sees, and
it sees one window at a time, so strictly the problem is a POMDP presented to
the agent as an MDP over the current window. That is a deliberate limitation: it
means a vanilla DQN cannot anticipate a shift the way Lion's LSTM predictor
does, only react to it. Frame stacking, a recurrent policy or an explicit drift
estimate are the obvious remedies, and belong in future work rather than in the
eight-week scope. It should be named in the paper, because Lion's reported
4x faster adaptation comes precisely from anticipation.

### 2.4 Action space `A`

A single flat discrete space of `2 * F_max * R + F_max + 1 = 261` actions, every
one of which is a **desired end state** rather than an operation (ADR-0002, as
amended 19 October):

| Action | Effect | Bytes moved | Cluster statement |
|--------|--------|-------------|-------------------|
| `MOVE_LEASE(f, r)` | region `r` becomes primary of `f` | **0 always** | `ALTER RANGE <id> RELOCATE LEASE TO <store>` |
| `MOVE_REPLICA_TO(f, r)` | `f` has a replica in `r`; the non-primary replica farthest from `r` is released | fragment size | `ALTER RANGE <id> RELOCATE VOTERS FROM <s> TO <s>` |
| `SPLIT(f)` | `f` is cut at its midpoint cell | 0 | `ALTER TABLE ... SPLIT AT VALUES (k)` |
| `NOOP` | nothing | 0 | none |

The replication factor is **fixed** (ADR-0009), which is why `ENSURE_REPLICA`
and `DROP_REPLICA` are gone: at fixed RF they were measured 0.0% applicable in
every state. `MERGE` is gone because CockroachDB has no synchronous counterpart,
so `F_t` is monotone within an episode.

`MOVE_LEASE` is refused when `r` holds no replica, mirroring the database. The
two placement blocks therefore partition: for any `(f, r)` at most one is live.
This is what keeps the cheap tier (a lease move, one round trip, no bytes)
distinct from the expensive one (a replica move, one fragment), which the
reward's migration term depends on.

`MOVE_REPLICA_TO` names only a destination; the released replica is chosen for
the agent by RTT distance. That tie-break is part of the action's semantics.
Breadth-first search over the replica-set state space confirms it costs no
reachability, at a worst-case cost of two extra actions.

Constraints refuse rather than raise: `F_t <= F_max`, the primary is always a
replica, a single-cell fragment cannot split, a lease needs a replica at its
target. A refused action changes nothing and is charged
`inapplicable_action_cost`.

**This is where the joint claim lives.** Lion moves replicas of a partition and
never splits or merges one; GeoTP never moves data at all. `SPLIT` and `MERGE`
sitting in the same flat action space as `SET_PRIMARY` and the replica actions
is the joint fragmentation-and-allocation control the project claims.

### 2.5 Transition `P`

Deterministic given the seed, in two stages:

1. The action is applied to the catalogue at the window boundary. It takes
   effect immediately and completely.
2. The clock advances, `demand_{t+1}` is drawn from the workload process, and
   it is served under the **new** catalogue.

So the placement chosen at step `t` is evaluated against window `t+1`. Migration
is instantaneous but not free: it costs bytes, not time (ADR-0004). A real
cluster serves degraded traffic during the copy, which this model does not
represent.

### 2.6 Cost model

Given a catalogue and a window, each request class has a closed-form latency.

**Read** of fragment `f` from origin `o`, served by the nearest replica:

```
lat_read(f, o) = min over s in replicas(f) of L[o, s]
```

Under `read_consistency = "primary_only"` the minimum is replaced by
`L[o, primary(f)]`.

**Write** of fragment `f` from origin `o`, reaching the leader and then waiting
for acknowledgements:

```
lat_write(f, o) = L[o, primary(f)] + ack(f)

ack(f) = 0                                        write_ack = "primary"
       = q-th smallest of { L[p, s] : s in replicas(f) \ {p} },  "majority"
         with q = ceil((n+1)/2) - 1 and n = |replicas(f)|
       = max of that same set                     write_ack = "all"
```

**Transaction** of template `T` from origin `o`, whose member operations are
issued in sequence and whose participants are the primaries of the fragments it
touches:

```
lat_txn(T, o) = sum over members m of lat_read or lat_write (f(m), o)
              + commit(T, o)

commit(T, o) = 0   if all participants sit in one region
             = min over c in participants of ( L[o, c] + 2 * max over p in participants of L[c, p] )
```

The commit term is a two-phase commit charged as reaching a coordinator plus a
prepare and a commit round to the farthest participant, minimized over the
choice of coordinator. **This term is the mechanism Lion exploits**: a
transaction whose fragments all sit in one region commits locally and pays
nothing, and that is what makes co-locating co-accessed fragments valuable.
**It is also where GeoTP's contribution would sit**, as a reduction in this term
over a fixed layout.

Mean latency is the demand-weighted mean over all three classes. Because each
class has one known latency and one known count, the latency distribution is
discrete and exact, so the reported p95 is computed rather than sampled.

Load is the operations landing on each region: a read at its serving replica, a
write at every replica. Imbalance is the coefficient of variation of that
vector, and of the per-region storage vector.

### 2.7 Reward `r`

```
r_t = - ( w_lat * mean_latency_ms / latency_scale
        + w_mig * bytes_moved     / migration_scale
        + w_bal * load_imbalance
        + inapplicable_action_cost  if the action changed nothing )
```

Defaults: `w_lat = 1.0`, `w_mig = 0.30`, `w_bal = 0.10`,
`latency_scale = 100 ms`, `migration_scale = 10 GB`,
`inapplicable_action_cost = 0.02`.

The reward is bounded above by zero, since every term is a cost.

Two structural facts matter for learning. First, the reward is **delayed**: an
action's migration cost is charged in the window it happens, but its latency
benefit accrues over every subsequent window until the workload moves again.
Second, the trade-off is **explicitly parameterized**: `w_mig` is the knob whose
sweep is Objective 5, tracing the frontier between a policy too sluggish to
capture the benefit and one that thrashes.

### 2.8 Discount and episode

`gamma = 0.99` by default, which at a 200-window episode gives an effective
horizon comfortably longer than the 96-window diurnal period, so a policy can in
principle value an action whose payoff arrives most of a cycle later.

Episodes **truncate** at `windows_per_episode`; they never terminate. There is
no absorbing state, the episode simply stops being observed, so the value at the
boundary must be bootstrapped rather than zeroed. Gymnasium's separate
`terminated` and `truncated` flags carry this, and Stable-Baselines3 handles it
correctly only if the environment reports them correctly. `test_env.py` asserts
that `terminated` is never raised.

---

## 3. Why this is a reinforcement learning problem

The proposal's claim is that the defining conditions are present. Stated against
the formulation above:

- **Sequential.** An action changes the catalogue, which is state, which
  conditions every later decision. Splitting now makes a later per-half
  reallocation possible.
- **Non-stationary environment.** The demand distribution is a function of `t`.
  A policy optimal for window 10 is wrong by window 40.
- **Delayed reward.** Migration cost is immediate, latency benefit is spread
  over subsequent windows. A greedy one-step optimizer overpays for migration.
- **Large discrete action space.** 261 actions, beyond enumeration at every
  step of a planning horizon.
- **No available supervision.** There is no labelled optimal placement per
  window to imitate. Even computing one per window is a combinatorial problem;
  computing the optimal *sequence* is harder still.

The last point is the honest justification. If a per-window optimum were cheap
to compute, a greedy solver would be the right tool and RL would be overkill.
It is not cheap, and more importantly the per-window optimum is not the right
target, because it ignores what the migration to reach it costs and how long it
will remain optimal.

---

## 4. Correspondence with the code

| Concept | Where |
|---------|-------|
| `L`, `phi_r` | `fragalloc.topology.Topology` |
| `psi_k`, `p_k`, `lambda`, spikes, templates | `fragalloc.workload.WorkloadGenerator` |
| catalogue, the five mutators, bytes moved | `fragalloc.catalog.FragmentCatalog` |
| `lat_read`, `lat_write`, `lat_txn`, commit, load, tail | `fragalloc.cost` |
| action encoding and application | `fragalloc.actions.ActionSpace` |
| observation encoding, layout | `fragalloc.observation.ObservationEncoder` |
| transition, clock, episode | `fragalloc.simulator.ClusterSimulator` |
| reward, Gymnasium API | `fragalloc.env.FragAllocEnv` |
| every default | `fragalloc.config.FragAllocConfig` |

---

## 5. Open items

Tracked in `docs/open-questions.md`. The two that bear on this specification:

1. The volatility sweep does not degrade the static baseline, because rotating
   the demand field leaves a roughly uniform placement roughly as wrong as it
   was. The sweep needs a metric that responds to `nu`; regret against a
   per-window oracle is the candidate.
2. `cell_angle_walk_sigma` bounds how much the fragmentation action can
   possibly be worth. It has no measured ground truth and must be ablated
   rather than assumed.
