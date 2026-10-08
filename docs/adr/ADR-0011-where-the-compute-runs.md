# ADR-0011: Where the compute runs, and why it is not a GPU

**Status:** Accepted.
**Date:** 2026-10-08
**Deciders:** Tinotenda Kaseke
**Extends:** [ADR-0010](ADR-0010-session-scoped-cluster-and-resumable-runs.md)

## Context

Three questions, and two of them dissolve once the numbers are measured rather
than assumed: can Kaggle's GPUs be used, is it acceptable to drop pre-training,
and what is the workaround for a laptop that cannot stay on.

### The measurement that settles the first two

The simulator was timed on the actual machine, 3,000 steps at the default
configuration:

```
3000 steps in 1.07s = 0.356 ms/step = 2,807 steps/s
50,000 env steps = 18 s of environment time
```

**Pre-training is 18 seconds of environment time.** Add a gradient step per
environment step on a small MLP and the whole pre-training run is single-digit
minutes on a CPU. It was never the expensive part, and an earlier note in this
project describing it as "hours of wall clock" was wrong.

Two conclusions follow directly.

**Dropping pre-training saves nothing.** It costs minutes and it buys the
de-risking that [ADR-0009](ADR-0009-cockroachdb-for-sim-to-real-parity.md) is
built on: if the cluster work fails, there is still a complete set of simulator
results to report. Keep it.

**A GPU would not help.** The network is a small multilayer perceptron over a
703-dimensional observation. On the cluster each environment step is a placement
statement plus a few hundred transactions over links with injected wide-area
delay, so the step is dominated by **network wait**, not arithmetic. A GPU
accelerates the part of the loop that already takes under a millisecond and
leaves the part that takes two to six seconds untouched. Kaggle's GPUs are free
and they are the wrong tool.

### What the laptop problem actually requires

Not GPU hours. A machine that can hold six CockroachDB processes, a latency
injector and a Python agent for a few hours, and that does not stop when the
laptop lid closes.

## Decision

**Keep pre-training. Use no GPU. Run the cluster in GitHub Codespaces when the
laptop is not available, and on the laptop when it is. The two are the same
environment, because both run the same Docker Compose stack.**

### Where each phase runs

| Phase | Cost | Runs on |
|---|---|---|
| Pre-training in the simulator | minutes, CPU | anywhere, including the laptop between classes |
| Cluster pilot and falsification test | ~1 hour | laptop or Codespaces |
| Fine-tuning, ~2000 steps | 1 to 3.5 hours | Codespaces, or laptop across several sessions |
| Sweeps and figures | minutes, CPU | laptop |

### Why Codespaces

- **Docker works**, so the Compose stack is byte-identical to the laptop's.
  There is one environment definition, not two.
- **State survives a stop.** Stop the codespace, walk to class, start it again
  and the containers, the checkpoint directory and the shell history are as they
  were. That is precisely the walk-between-buildings workflow, and it is better
  than the laptop, where [ADR-0010](ADR-0010-session-scoped-cluster-and-resumable-runs.md)
  has to rebuild the cluster each session.
- **It is free at the scale needed.** A personal GitHub Free account includes
  **120 compute hours and 15 GB-month of storage**. The included-usage multiplier
  is 4 for a 4-core machine, so that is **30 hours per month on 4 cores and
  16 GB**, which fits six nodes at 2.3 GB with room to spare. A stopped codespace
  accrues no compute time, only storage.
- **It runs from any machine**, including a lab PC, with nothing installed.

Thirty hours a month against fine-tuning runs of one to three and a half hours is
roughly ten full runs. That is enough, but it is not unlimited: stop the
codespace when not using it, and do not leave one idling.

### Why not Kaggle

Kaggle was examined seriously and rejected for a specific, checkable reason.

The cluster needs a **true inter-region latency matrix**, not a single delay per
node. The project's whole subject is geographic locality, and the signal it must
detect includes two regions being *near each other*: `eu-west-1` and
`eu-central-1` sit 20 ms apart whilst both are roughly 68 ms from `us-east-1`.

Injecting a real matrix requires per-destination traffic shaping inside each
node, which means `tc`/`netem`, which needs the `NET_ADMIN` capability. Kaggle
notebooks give no root and no container capabilities, so the only thing available
there is a userspace TCP proxy with one delay per node. That yields a **star
metric**, where the round trip between regions `i` and `j` is forced to be
`L_i + L_j`. A star metric cannot express "these two regions are close to each
other", so it would delete the very structure the agent is supposed to learn.

Kaggle would also be of no use for pre-training, which takes minutes, and its
GPUs are irrelevant as established above. **Kaggle is rejected on capability,
not on cost.**

### Latency injection: `netem`, not Toxiproxy

This reverses the choice in [ADR-0007](ADR-0007-real-database-validation.md) and
[ADR-0009](ADR-0009-cockroachdb-for-sim-to-real-parity.md), which both specified
Toxiproxy on the grounds that the CockroachDB image ships no `iproute2`.

That reason is real and the fix is three lines of Dockerfile. The reason to
reverse is the one above: **Toxiproxy cannot express an arbitrary RTT matrix
between cluster nodes.** A proxy sits in front of a destination, and CockroachDB
nodes advertise their own addresses to each other, so every node reaches a given
peer through the same proxy and therefore the same delay. Per-pair latency
requires shaping at the source, which is what `netem` does and a proxy cannot.

Consequence: the image gains `iproute2`, each node container gains
`cap_add: NET_ADMIN`, and the shaping rules are generated rather than written by
hand (below). Toxiproxy's one advantage, changing latency mid-run for the
volatility experiments, is preserved: `tc qdisc change` does the same thing.

### The RTT matrix stops being a guess

`topology.py` carries a `TODO(paper)` saying its matrix is synthetic and must be
replaced before any reported result. On the cluster it is **not an estimate of
the world, it is the experiment's own configuration**, and the only requirement
is that the simulator and the cluster agree exactly.

So the Compose file and the shaping rules are **generated from
`DEFAULT_RTT_MS`** by `scripts/gen_cluster.py`, rather than written by hand. The
two cannot drift, and the parity requirement from
[ADR-0009](ADR-0009-cockroachdb-for-sim-to-real-parity.md) is enforced by
construction instead of by discipline. What still needs doing for the paper is
citing a public latency dataset for the chosen values and recording the date.

## Options Considered

| Option | Docker | State survives | Cost | True RTT matrix | Verdict |
|---|---|---|---|---|---|
| Laptop, session-scoped | yes | rebuilt each session | free | yes | **kept**, the default |
| **GitHub Codespaces** | yes | **yes** | free to 30 h/month at 4 cores | yes | **chosen** for off-laptop work |
| Kaggle notebooks | no | output files only | free | **no, star metric only** | rejected |
| Google Colab | no | no | free tier | no | rejected, same reason, less RAM |
| Cloud VM | yes | yes | costs money | yes | excluded by the no-charge constraint |

## Consequences

- **`.devcontainer/devcontainer.json`** defines the Codespaces machine: 4 cores,
  16 GB, Docker-in-Docker, and the project's dependencies installed on create.
  It is also usable locally with VS Code, so the laptop and Codespaces run the
  same definition.
- **`docker/Dockerfile.crdb`** adds `iproute2` to the CockroachDB image. Nothing
  else.
- **`scripts/gen_cluster.py`** emits the Compose file and the per-node `netem`
  rules from `DEFAULT_RTT_MS`, so the cluster's geography is the simulator's
  geography by construction.
- **`scripts/cluster.sh`** wraps `up`, `down`, `status` and `verify`, per
  [ADR-0010](ADR-0010-session-scoped-cluster-and-resumable-runs.md).
- **The pre-training story simplifies.** It is a few minutes on any CPU, so it is
  not scheduled as a block of work; it is something run before each fine-tuning
  session.
- **None of the Compose or `netem` configuration has been executed.** It was
  written without a Docker daemon available, so **the first run is a verification
  step, not a smoke test**. Expect to fix it. Budget half a day in block 1.
- The 30-hour Codespaces budget is a real constraint. Stop the codespace when not
  using it.

## Action Items

1. [ ] Push the repository to GitHub. Codespaces needs it there, and it is also
   the off-machine backup that [`tech-debt.md`](../tech-debt.md) ranks first.
2. [ ] Open a Codespace on a 4-core machine and run `scripts/cluster.sh up`.
   **Expect it to fail the first time**, and fix it. This replaces the earlier
   plan's assumption that the Compose stack would work as written.
3. [ ] Verify the injected latency with `ping` between containers before
   trusting any measurement. A silently un-shaped cluster produces plausible
   numbers that mean nothing.
4. [ ] Cite a public latency dataset for the values in `DEFAULT_RTT_MS` and
   record the collection date. Closes the `TODO(paper)` in `topology.py`.
5. [ ] Time one pre-training run end to end and record it, so the paper can state
   the training cost honestly rather than estimating it.

## Sources

- [GitHub Codespaces billing](https://docs.github.com/en/billing/concepts/product-billing/github-codespaces), for the 120 compute hours, 15 GB-month storage, and the 4x multiplier on a 4-core machine
- Simulator throughput measured in-repo on 8 October 2026: 3,000 steps in 1.07 s
