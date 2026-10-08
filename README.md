# Reinforcement Learning for Dynamic Data Fragmentation and Allocation

A Deep Q-Network agent for continuous re-fragmentation and re-allocation of
database shards under geographically migrating workloads.

**Research question.** How effectively can a DQN continuously re-fragment and
re-allocate database shards across cloud nodes under highly volatile, localized
read/write workloads?

Distributed databases fix their fragmentation schema at design time and hand
allocation to key-dependent functions that never observe where requests come
from. When the geographic centre of gravity of a workload migrates, as it does
daily in multi-region services and abruptly during localized events, the
placement drifts out of step with the traffic and global transaction latency
degrades. This project asks whether a reinforcement learning agent, acting as an
autonomous database administrator inside a simulated multi-region cluster, can
learn to make sharding and replication decisions that track the workload rather
than lag behind it.

Course project, COSC 6315. Tinotenda Kaseke, September to November 2026.

---

## Quick start

Python 3.10 or later. No GPU, no cloud account, 8 GB of RAM is plenty.

```bash
# Windows PowerShell, from the project folder
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev,analysis]"

# macOS or Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,analysis]"
```

Then:

```bash
pytest                                    # 115 tests, about one second
python scripts/smoke_run.py               # one episode under each reference policy
python scripts/volatility_probe.py        # how each policy responds to volatility
```

`smoke_run.py` should print something close to this. The numbers move with the
seed; the ordering should not.

```
volatility=1.0  windows=200  episodes=1
401 actions over 6 regions, fragment cap 20
policy                   mean ms    p95 ms   GB moved  xregion  frags
---------------------------------------------------------------------
no-op (static hash)       156.93    554.60        0.0    43.1%    6.0
random                    126.71    484.84      220.1    21.6%    4.0
greedy primary             94.19    400.35      450.7    34.1%    6.0
```

Reading that: a placement that follows the traffic cuts mean latency by about
40% against the static hash partitioner it started from, and pays for it by
moving 451 GB over the episode. Closing that gap at a fraction of the churn is
what the agent is for.

Keep `.venv/` out of OneDrive's way; `.gitignore` already excludes it, along
with model checkpoints and TensorBoard runs.

---

## Seeing it

Three ways, in the order you probably want them.

**Watch it run.** A live matplotlib window with a real world map: Natural Earth
coastlines and borders under Web Mercator, every data centre at its true
coordinates, request volume as bubble size, chunks as squares, and a great-circle
arc drawn every time one migrates. Beside it, a running latency chart for all
three strategies. Sliders along the bottom set volatility, seed, chunk count,
episode length and speed; buttons add and remove regions and switch which
strategy the map follows.

The basemap is bundled in `src/shardmind/data/`, so it needs no network and no
extra packages. It is the same projection and the same geometry the web replay
uses, so the two agree.

```bash
python scripts/live_dashboard.py
python scripts/live_dashboard.py --regions 8 --volatility 4
python scripts/live_dashboard.py --save results/figures/live-episode.gif
```

Up to ten regions are available. The first six carry the measured latency table;
beyond those, latencies come from a distance model fitted to it, which the
subtitle says plainly and `docs/` explains.

**Ask it questions.** Nine statistical panels over several seeds plus a
volatility sweep: distribution and tail, cumulative curve, means with confidence
intervals, the latency-against-bandwidth cost curve, the daily rhythm, where the
load comes from, how long a chunk stays put, load balance, and how far each
strategy sits behind a moving optimum.

```bash
python scripts/analysis_dashboard.py            # -> results/figures/analysis.png
python scripts/analysis_dashboard.py --show     # open a window instead
```

**A real map.** The same episode on OpenStreetMap tiles, with every data centre
at its actual coordinates and migrations drawn along the great circles the data
crosses. One self-contained file, no API key, no account.

```bash
python scripts/export_episode.py
python scripts/make_atlas.py        # -> results/atlas.html
start results\\atlas.html            # 'open' on macOS
```

Leaflet is vendored in `vendor/leaflet/` and inlined, so the file works offline
apart from the tiles themselves.

**Paper figures.** Four clean PNGs from one exported episode.

```bash
python scripts/export_episode.py    # one episode per policy -> results/episode.json
python scripts/plot_figures.py      # four PNGs -> results/figures/
```

`results/episode.json` also feeds the interactive web replay, where you can scrub
through the episode. Regenerate the JSON and the page can be rebuilt from it.

All four scripts take `--volatility`, `--seed` and `--windows`, so any figure can
be reproduced for a different world.

---

## Using the environment

```python
from shardmind.config import ShardMindConfig
from shardmind.env import ShardMindEnv

env = ShardMindEnv(ShardMindConfig())
obs, info = env.reset(seed=0)                      # obs: 703 floats in [0, 1]
obs, reward, terminated, truncated, info = env.step(env.action_space.sample())
print(env.render())
```

It registers as `ShardMind-v0` and passes
`gymnasium.utils.env_checker.check_env`.

Sweeping a parameter:

```python
from dataclasses import replace

base = ShardMindConfig()
volatile = base.evolve(workload=replace(base.workload, volatility=4.0))
patient  = base.evolve(reward=replace(base.reward, w_migration=1.0))
```

Working below the RL layer, which is where the baselines and the validation
harness live:

```python
from shardmind.simulator import ClusterSimulator

sim = ClusterSimulator(ShardMindConfig())
sim.step(sim.action_space.noop_index)
print(sim.last.cost.mean_latency_ms, sim.last.cost.tail_latency_ms)
print(sim.catalog.summary())
```

---

## What is in here

```
src/shardmind/
  config.py       every tunable, in frozen dataclasses; JSON round-trip
  topology.py     regions, the RTT matrix, the geographic circle
  workload.py     drifting demand over keyspace cells; spikes; transactions
  catalog.py      fragment boundaries, placement, the five declarative mutators
  cost.py         analytic latency, exact tail percentiles, load accounting
  actions.py      the 401-action flat space
  observation.py  state to a 703-element unit-box vector, layout published
  simulator.py    clock, transition, episode
  env.py          the Gymnasium adapter: observation, action, reward
  policies.py     reference policies for exercising the environment
tests/            115 tests
scripts/          smoke_run.py, volatility_probe.py
configs/          named reference configurations, JSON
vendor/           third-party code checked in, with its licence
docs/             specification, architecture, ADRs, testing strategy, open questions
results/          experiment records, gitignored
```

The boundary that matters is between `simulator.py` and `env.py`. Everything
below it models a database cluster and imports only NumPy; everything above it
is reinforcement learning. Four of the six research objectives live below the
line, which is why it is drawn there ([ADR-0005](docs/adr/ADR-0005-simulator-independent-of-gymnasium.md)).

---

## The model in one page

Six regions with a fixed inter-region RTT matrix. The keyspace is 256 atomic
cells; a fragment is a contiguous run of them. Each cell sits at an angular
position on the same circle as the regions, and the whole angular field rotates
over a diurnal period, so traffic to a given cell migrates between regions.
Localized Poisson spikes sit on top. Volatility scales the rotation speed and
the spike process together.

Requests are single-key reads and writes, plus multi-fragment transactions drawn
from fixed templates. A read costs the RTT to its nearest replica; a write costs
the RTT to the primary plus a quorum acknowledgement; a transaction costs its
member operations plus, if its fragments' primaries span more than one region, a
two-phase commit charge. That last term is why co-locating co-accessed fragments
is worth something, and it is the mechanism Lion exploits.

The agent acts once per decision window, choosing from 401 actions. Every action
names a desired end state, not an operation, so every one of them is defined in
every state. That matters because DQN offers no way to mask invalid actions
([ADR-0002](docs/adr/ADR-0002-flat-declarative-action-space.md)).

Reward is the negative weighted sum of mean latency, bytes migrated and load
imbalance. Sweeping the migration weight traces the frontier between an agent
too sluggish to capture the benefit and one that thrashes.

Full formal treatment: [docs/mdp-specification.md](docs/mdp-specification.md).

---

## Status

Weeks 1 and 2 of eight are complete, five days ahead of schedule.

Done: the simulator, the Gymnasium wrapper, seeded reproducibility, the flat
action space, the MDP specification, six ADRs, and 115 tests.

Next, week 3: the four baselines, a tabular Q-learning sanity check, and an
ablation of how heterogeneous the keyspace has to be before splitting a fragment
is worth anything. See [docs/roadmap.md](docs/roadmap.md).

**Read [docs/open-questions.md](docs/open-questions.md) before trusting any
number here.** It records seven things that are unsettled, the most important
being that the volatility sweep does not move the static baseline, for a reason
that turns out to be structural rather than a bug.

---

## Base papers

1. Q. Zheng et al., "Lion: Minimizing Distributed Transactions Through Adaptive
   Replica Provision," ICDE 2024, pp. 2012-2025.
   Adapts replica placement so transactions commit locally. Heuristic, and
   geography appears nowhere in its cost function.
2. Q. Zhuang et al., "GeoTP: Latency-Aware Geo-Distributed Transaction
   Processing in Database Middlewares," ICDE 2025, pp. 433-445.
   Treats wide-area latency as a first-class target, but optimizes execution
   over a layout it never changes.

The gap this project occupies: a learned policy jointly controlling
fragmentation and geographic allocation, optimizing transaction latency net of
migration cost under continuously drifting workloads.
# COSC-6315-project
