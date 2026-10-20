# Reinforcement Learning for Dynamic Data Fragmentation and Allocation

Teaching a neural network to be a database administrator: one that watches where
traffic is coming from and continuously moves the data to meet it.

Course project, COSC 6315. Tinotenda Kaseke, September to November 2026.
Repository: `TinoTheGiant/COSC-6315-project`.

---

## What this is, in plain language

A large database does not live on one machine. It is cut into pieces, called
**shards**, and the pieces are spread across servers in different parts of the
world. Two things are decided when the database is designed: **how** it is cut
up (fragmentation) and **where** each piece lives (allocation).

Almost every database decides both of those once, at design time, and never
revisits them. The pieces are placed by a mathematical function of the key, which
has no idea where in the world the requests are actually coming from.

Traffic, meanwhile, moves constantly. It follows the sun: Asia is busy whilst
North America sleeps. It spikes locally when something happens in one city. So a
layout that was sensible on day one slowly becomes mismatched with the traffic it
is serving, and users wait longer because their data is on the wrong continent.

**The research question.** Can a reinforcement learning agent act as an
autonomous database administrator, continuously re-cutting and re-placing the
shards so the layout tracks the traffic instead of lagging behind it?

### Why that is hard, and why it is interesting

Moving data is not free. Every migration costs bandwidth and time, so an agent
that chases every fluctuation is worse than one that does nothing. The real task
is a trade-off: **reduce latency by more than the cost of the moves you make.**

There is a second, subtler payoff. When one transaction touches several shards
that live in different regions, the database has to run a two-phase commit across
continents, which is slow. If the agent learns to keep shards that are *used
together* in the *same place*, those transactions commit locally and the cost
disappears. That is the mechanism the project is really chasing.

### What "reinforcement learning" means here

The agent is not told the right answer. Every few minutes of simulated time it
picks one action (move a shard, move which copy is in charge, split a shard in
two), then gets a score: good if transactions got faster, bad if they got slower
or if it moved a lot of data to get there. Over many thousands of these it learns
which moves tend to pay off.

The specific method is a **Deep Q-Network (DQN)**: a neural network that looks at
the current state of the cluster and estimates, for each possible action, how
much total future reward that action leads to. The agent picks the highest
estimate. "Deep" just means a neural network does the estimating rather than a
lookup table, which matters because there are far too many possible cluster
states to tabulate.

---

## The three stages, and why there are three

This is the part that looks complicated from outside. It is three stages because
each one fixes a problem the previous one has.

```
  STAGE 1                    STAGE 2                      STAGE 3
  Python simulator           Real CockroachDB cluster     GitHub Actions
  ~3,000 steps/second        ~1 step every 2-6 seconds    runs stage 2 for you

  Learn cheaply       -->    Prove it on a real DB  <--   No laptop required
```

### Stage 1: a simulated cluster, to learn cheaply

A model of a six-region database cluster written in plain Python. It knows the
network delay between regions, where traffic is coming from, and how to compute
what a transaction would cost under a given layout.

It runs at **about 3,000 steps per second** (measured: 0.356 ms per step), so the
agent can take 50,000 practice actions in under twenty seconds. That is where the
agent learns the basic shape of the problem, and it costs essentially nothing.

**The catch:** it is a model. The numbers come from a formula, not from a
database. A reviewer is entitled to ask whether any of it is true.

### Stage 2: a real CockroachDB cluster, to prove it

Six actual **CockroachDB** servers running in Docker containers, one per
simulated region, with artificial network delay injected between them so that
"Frankfurt to Singapore" really does take 180 ms. The agent issues real SQL:

```sql
ALTER RANGE 45 RELOCATE LEASE TO 4;          -- move which copy is in charge
ALTER RANGE 45 RELOCATE VOTERS FROM 2 TO 4;  -- move the data itself
ALTER TABLE t SPLIT AT VALUES (5000);        -- cut a shard in two
```

Then it runs real transactions and times them with a stopwatch. No formula.

**Why CockroachDB specifically.** Twenty-one databases were screened. Most hide
placement from the operator on purpose, because deciding placement automatically
is their selling point. The decisive requirement was that the move command must
**finish before it returns** so the latency measured afterwards belongs to the
new layout and not the old one. CockroachDB's `RELOCATE` blocks until the
destination has actually received the data. Only five of the twenty-one do that,
and three of those have no cross-shard transactions to measure. Full screen in
[ADR-0008](docs/adr/ADR-0008-database-selection.md).

**The catch:** each step takes seconds instead of milliseconds. A full training
run here would take weeks.

### Why both: pre-train in stage 1, fine-tune in stage 2

The agent learns the general shape for free in the simulator, then transfers
those learned weights to the real cluster and only *refines* them there. This cuts
the expensive stage from weeks to a couple of hours.

For the transfer to work, the two stages have to agree on the shape of the
problem: same inputs, same list of possible actions, same definition of the
score. That constraint drives a surprising amount of the design, and it is why
the cluster's geography is **generated from the simulator's own distance table**
rather than written by hand. They cannot drift apart.

### Stage 3: GitHub Actions, because the laptop cannot stay on

Stage 2 needs a machine running for hours. The laptop moves between buildings and
is needed for other classes.

So the work runs on **GitHub Actions** instead: press a button in the Actions
tab (the phone app works), and GitHub provides a Linux machine that runs the
whole thing for up to six hours and hands back the results. The laptop is not
involved at all. There are two workflows:

- **Experiments** runs the simulator under the reference policies. Seeds,
  episode length and volatility are fields in the form. It prints the result
  table into the run summary and uploads the figures and the full record.
- **Train agent** trains the DQN and then scores it against every baseline on
  held-out seeds, in one job.
- **Cluster pilot** brings up the six-node CockroachDB cluster, proves the
  injected latency is real, and runs the gate below.

### The gate: checking the idea is real before building on it

Before any agent work, one question gets answered: **on a real cluster, does
where the data sits actually change how long a transaction takes, by more than
the normal run-to-run noise?**

`scripts/falsification_test.py` answers it. It puts every shard in one region and
times 200 transactions, spreads them across six regions and times 200 more, then
computes a confidence interval on the difference. If that interval includes zero,
there is no signal to learn from and no amount of clever agent code creates one.

Finding that out in week 5 is a publishable negative result. Finding it out in
week 8 is a disaster. That is the whole reason the test exists.

---

## Tech stack, in plain language

| What | Why it is here |
|---|---|
| **Python 3.10+** | The whole project. The only language in the repo |
| **NumPy** | Fast array maths. The simulator's cost calculations |
| **Gymnasium** | The standard interface for reinforcement learning environments. Makes the simulator and the real cluster interchangeable to the agent |
| **PyTorch** (CPU only) | The neural network underneath the DQN. No GPU needed, see below |
| **Stable-Baselines3** | A tested, published DQN implementation. Writing one from scratch means a non-converging run has two suspects instead of one ([ADR-0003](docs/adr/ADR-0003-stable-baselines3-over-hand-rolled-dqn.md)) |
| **CockroachDB** | The real distributed database in stage 2. Chosen because its placement commands block until the data has moved |
| **Docker / Docker Compose** | Runs the six database servers as six containers on one machine |
| **`tc` / netem** (Linux) | Injects fake network delay between the containers, so the cluster has realistic geography |
| **psycopg** | The Python driver that talks to CockroachDB and times transactions |
| **pytest** | The test suite. ~150 tests, about a second |
| **matplotlib / pandas** | Charts: the live dashboard and the paper figures |
| **GitHub Actions** | Runs the cluster experiment on GitHub's hardware instead of the laptop |

**No GPU, deliberately.** The network is small, and on the real cluster each step
is dominated by waiting for the network, not by arithmetic. A GPU would speed up
the part that already takes under a millisecond. Measured and recorded in
[ADR-0011](docs/adr/ADR-0011-where-the-compute-runs.md).

---

## Getting started

Two tracks. The first needs only a laptop; the second needs Docker or a GitHub
account.

### Track 1: the simulator, on any machine

Python 3.10 or later. No GPU, no cloud account, no database. 8 GB of RAM is
plenty.

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

Check it works, then watch it do something:

```bash
pytest                            # ~150 tests, about a second
python scripts/smoke_run.py       # one episode under each reference policy
python scripts/volatility_probe.py
```

`smoke_run.py` prints roughly this. The numbers move with the seed; the ordering
should not.

```
volatility=1.0  windows=200  episodes=1
261 actions over 6 regions, fragment cap 20
policy                   mean ms    p95 ms   GB moved  xregion  frags
---------------------------------------------------------------------
static hash               156.93    554.60        0.0    43.1%    6.0
random                    157.42    573.99      185.6    45.3%   20.0
follow traffic            110.54    474.84      759.8    32.9%    6.0
```

**The three reference policies.**

| Name | What it does | Why it is here |
|---|---|---|
| **Static hash** | Never moves anything. The placement a consistent-hash partitioner produced at setup, held for the whole episode. | This is what production databases do today. It is the thing to beat. |
| **Random** | Picks a legal action uniformly at random. | A control. It proves any gain comes from choosing *where* to move data, not merely from moving it. |
| **Follow traffic** | Each window, finds the single worst-placed fragment and moves its primary towards the region reading it. | The obvious hand-written heuristic. It looks only at the current window, so it reacts but never anticipates. |
| **Best per window** | Not a policy. The lowest latency reachable in each window if migration were free and instant. | A ceiling drawn on the figures. No real policy can reach it, so the gap to it measures how much is left on the table. |

**Reading that.** "Static hash", which is what a normal database does, averages
157 ms. A simple policy that just follows the traffic gets to 110 ms, a 30%
improvement, but pays by shifting 760 GB over the episode. Closing that gap at a
fraction of the churn is what the agent is for.

The follow-traffic policy is deliberately handicapped in a way that matters: a lease can
only move to a region that already holds a replica, which is what CockroachDB
enforces, so relocating one takes two windows. A myopic policy therefore tracks
drifting traffic a window behind. An agent that anticipates drift should beat it
by more than it could have beaten the older, unrealistic one-step baseline. The
amendment to [ADR-0002](docs/adr/ADR-0002-flat-declarative-action-space.md)
records the measurement.

### Recording a result that the paper can cite

Everything above is for looking at things. `scripts/run_experiment.py` is for
producing numbers that will be quoted, and it is the only script that should
ever do so.

```bash
python scripts/run_experiment.py --seeds 8 --windows 200 --figures
```

One invocation is one **run**, and a run writes one self-contained directory
under `results/runs/`:

| File | What it holds |
|---|---|
| `manifest.json` | The commit, whether the tree was dirty, the fully resolved configuration, the seed list, package versions, the machine, and how long it took |
| `config.json` | The same configuration on its own, reloadable with `--config` to repeat the run exactly |
| `steps.csv` | One row per policy, seed and decision window. The raw record |
| `summary.csv` | One row per policy and seed. The unit of statistics |
| `report.md` | The aggregated table with 95% bootstrap intervals, and the command that reproduces it |
| `figures/` | Print-ready PNGs in the project's figure style |

Every row in every CSV carries `run_id`, `policy` and `seed`, so two runs can be
concatenated without ambiguity and no number is ever separated from the
configuration that produced it. The methods section of the paper is then a
transcription of `manifest.json` rather than an act of memory.

**Sweeps.** A sweep is several runs that differ in exactly one setting. The
**Sweep** workflow runs every value in one job and uploads the assembled table
and figure, which is one button rather than four downloads. Locally, run them
one at a time and join them:

```bash
python scripts/assemble_sweep.py --over volatility
python scripts/assemble_sweep.py --over w_migration
```

It refuses to combine runs that differ in more than the swept setting, which is
the reason it exists rather than a spreadsheet: a sweep assembled from runs with
different episode lengths is not a sweep, and the figure is wrong in a way
nobody notices until a reviewer asks.

**On GitHub, with no laptop.** Open the **Actions** tab, choose **Experiments**,
and press *Run workflow*. Set the seeds, the episode length and the volatility
in the form. The job runs the test suite first, then the experiment, prints the
report into the run summary, and uploads two artifacts: the whole run, and the
figures on their own so they can be dropped straight into the paper. More runs
is a button press.

### Training the agent

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install stable-baselines3 tensorboard

python scripts/train.py --timesteps 300000
```

About 170 environment steps a second on an ordinary CPU, so 300,000 steps is
roughly half an hour. There is no GPU in this; the network is two hidden layers
of 256 and the bottleneck is the simulator, not the gradient.

The run writes one directory under `results/models/` holding the weights, both
configurations, the evaluation history and a manifest. Two details matter and
are easy to get wrong:

- **Training resets onto a rotating set of 64 workload seeds**, not one. An
  agent trained on a single realization learns that realization.
- **Evaluation uses a disjoint block of seeds** and acts greedily, so the curve
  reported is generalization rather than recall, and the agent is not penalized
  for exploring.

Score the result against the baselines, through the same episode loop they use:

```bash
python scripts/run_experiment.py --policies static follow best agent \
    --model results/models/<id>/best_model.zip --seeds 8
```

**On GitHub, with no laptop.** Actions tab, **Train agent**, *Run workflow*. It
trains, then evaluates against every baseline on held-out seeds, puts the
comparison table in the job summary and uploads both the model and the
evaluation.

### Track 2: the real cluster

**The easy way, no local setup.** Push, then open the repository's **Actions**
tab, choose **Cluster pilot**, and press *Run workflow*. It builds the cluster,
proves the injected latency is real, turns off CockroachDB's own automatic
rebalancer so the agent is the only thing moving data, runs the gate, and posts
the results to the run summary. Up to six hours, and nothing is needed from your
machine.

**Locally**, if you have Docker:

```bash
python scripts/gen_cluster.py     # writes docker/docker-compose.yml from the
                                  # simulator's distance table
scripts/cluster.sh up             # six nodes + settings
scripts/cluster.sh latency        # CHECK THIS before trusting any number
python scripts/falsification_test.py
scripts/cluster.sh down
```

`scripts/cluster.sh latency` is not optional. A cluster whose delay injection
silently failed returns perfectly plausible numbers that mean nothing at all.

> **None of the Docker, netem or cluster SQL has ever been executed.** It was
> written without a Docker daemon available. Treat the first run as a debugging
> session, not a smoke test.

### Seeing it

**Watch it run.** A live matplotlib window with a real world map: Natural Earth
coastlines under Web Mercator, every data centre at its true coordinates, request
volume as bubble size, shards as squares, and a great-circle arc drawn whenever
one migrates. Sliders set volatility, seed, shard count and speed.

```bash
python scripts/live_dashboard.py
python scripts/live_dashboard.py --regions 8 --volatility 4
```

**Ask it questions.** Nine statistical panels across several seeds plus a
volatility sweep.

```bash
python scripts/analysis_dashboard.py       # -> results/figures/analysis.png
```

**A real map, and paper figures.**

```bash
python scripts/export_episode.py
python scripts/make_atlas.py               # -> results/atlas.html, OpenStreetMap
python scripts/plot_figures.py             # -> results/figures/*.pdf
```

Figures follow a documented design system so they survive a black-and-white
print, which an IEEE submission has to assume
([docs/figure-design-system.md](docs/figure-design-system.md)).

---

## Using the environment directly

```python
from shardmind.config import ShardMindConfig
from shardmind.env import ShardMindEnv

env = ShardMindEnv(ShardMindConfig())
obs, info = env.reset(seed=0)                 # obs: 703 floats in [0, 1]
obs, reward, terminated, truncated, info = env.step(env.action_space.sample())
```

It registers as `ShardMind-v0` and passes
`gymnasium.utils.env_checker.check_env`. Sweeping a parameter:

```python
from dataclasses import replace
base = ShardMindConfig()
volatile = base.evolve(workload=replace(base.workload, volatility=4.0))
patient  = base.evolve(reward=replace(base.reward, w_migration=1.0))
```

---

## What is in here

```
src/shardmind/
  config.py       every tunable, frozen dataclasses, JSON round-trip
  topology.py     regions and the inter-region delay matrix
  workload.py     drifting demand over the keyspace; spikes; transactions
  catalog.py      shard boundaries, placement, the declarative mutators
  cost.py         analytic latency, exact tail percentiles, load accounting
  actions.py      the flat 261-action space
  observation.py  cluster state -> a 703-element vector
  simulator.py    clock, transition, episode
  env.py          the Gymnasium adapter
  policies.py     reference policies to compare the agent against
  agent/          the DQN: hyperparameters, training loop, and a wrapper that
                  makes a trained model satisfy the same Policy protocol as
                  the baselines, so both are scored by one evaluation path
  viz.py          the shared plotting vocabulary and the print-safe palette
docker/           Dockerfile and the generated six-node Compose file
scripts/
  run_experiment.py  the only script whose output may be cited: one run,
                     one directory, config and seeds recorded with every row
  assemble_sweep.py  joins several runs into one sweep table and figure
  smoke_run.py       a quick look under each reference policy
  live_dashboard.py  the animated world map
  analysis_dashboard.py, plot_figures.py, make_atlas.py, export_episode.py
  train.py           trains the DQN
  gen_cluster.py, cluster.sh, falsification_test.py   stage 2
  measure_action_space.py  reproduces the figures in ADR-0002
.github/workflows/
  experiments.yml   simulator runs on GitHub's machines, figures uploaded
  sweep.yml         every value of one setting, assembled into one figure
  train.yml         trains the agent, then scores it against the baselines
  cluster-pilot.yml the whole stage-2 run, unattended
tests/            ~150 tests
docs/             specification, architecture, 11 ADRs, roadmap, debt audit
```

The boundary that matters is between `simulator.py` and `env.py`. Everything
below models a database cluster and imports only NumPy; everything above is
reinforcement learning ([ADR-0005](docs/adr/ADR-0005-simulator-independent-of-gymnasium.md)).

---

## The model in one page

Six regions with a fixed inter-region delay matrix. The keyspace is 256 atomic
cells; a shard is a contiguous run of them. Each cell sits at an angular position
on the same circle as the regions, and the whole field rotates over a daily
period, so traffic to a given cell migrates between regions. Localized Poisson
spikes sit on top. Volatility scales the rotation and the spikes together.

Requests are single-key reads and writes, plus multi-shard transactions from
fixed templates. A read costs the delay to its nearest copy; a write costs the
delay to the primary plus a quorum acknowledgement; a transaction costs its
member operations plus, if its shards' primaries span more than one region, a
two-phase commit charge. **That last term is why co-locating shards that are used
together is worth something**, and it is the mechanism this project is built on.

The agent acts once per decision window. Every action names a desired end state
rather than an operation, so every action is defined in every state, which
matters because DQN has no way to mask invalid actions
([ADR-0002](docs/adr/ADR-0002-flat-declarative-action-space.md)).

Reward is the negative weighted sum of latency, data moved and load imbalance.

Full formal treatment: [docs/mdp-specification.md](docs/mdp-specification.md).

---

## Status

Day 27 of 57. The simulator half is complete and tested. The real-cluster half is
written but has never been executed.

**Done:** simulator, workload model, cost model, action and observation spaces,
Gymnasium wrapper, seeded reproducibility, reference policies, dashboards, the
figure design system, eleven ADRs, ~150 tests.

**Next:** dispatch the cluster pilot, get past the gate, wire up the DQN. See
[docs/roadmap.md](docs/roadmap.md), which is honest about what has been cut.

**Measured results so far, all from the simulator and labelled as such:** a
traffic-following policy beats static hashing 94 ms against 157 ms whilst moving
451 GB per episode; traffic concentration is 53% per cell against an even split
of 16.7%, but only 41% per shard, and that gap is exactly what splitting
recovers.

> **Read [docs/open-questions.md](docs/open-questions.md) before trusting any
> number here.** It records what is unsettled, including that the volatility
> sweep does not move the static baseline, for a reason that turns out to be
> structural rather than a bug.

---

## Documentation

| If you want to | Read |
|---|---|
| The formal problem statement | [docs/mdp-specification.md](docs/mdp-specification.md) |
| How the code fits together | [docs/architecture.md](docs/architecture.md) |
| The real-cluster half | [docs/harness-architecture.md](docs/harness-architecture.md) |
| Why something is the way it is | [docs/adr/](docs/adr/) |
| What happens next | [docs/roadmap.md](docs/roadmap.md) |
| What actually happened on a real cluster | [docs/results-log.md](docs/results-log.md) |
| What is rotting | [docs/tech-debt.md](docs/tech-debt.md) |
| What is unsettled | [docs/open-questions.md](docs/open-questions.md) |
| How to make a figure that matches | [docs/figure-design-system.md](docs/figure-design-system.md) |

The decision history is worth reading in order if you want to understand the
project: the database choice was made, corrected on a factual error, reversed
after a screen of twenty-one systems, and reversed again once sim-to-real
pre-training was approved. ADRs 0007 through 0011 record all of it, including the
mistakes.

---

## Base papers

1. Q. Zheng et al., "Lion: Minimizing Distributed Transactions Through Adaptive
   Replica Provision," ICDE 2024, pp. 2012-2025. Adapts replica placement so
   transactions commit locally. Heuristic, and geography appears nowhere in its
   cost function.
2. Q. Zhuang et al., "GeoTP: Latency-Aware Geo-Distributed Transaction Processing
   in Database Middlewares," ICDE 2025, pp. 433-445. Treats wide-area latency as
   a first-class target, but optimizes execution over a layout it never changes.

**The gap this project occupies:** a learned policy jointly controlling
fragmentation and geographic allocation, optimizing transaction latency net of
migration cost under continuously drifting workloads, validated on a real
distributed database rather than only in simulation.
