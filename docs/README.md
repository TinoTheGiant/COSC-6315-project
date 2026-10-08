# Documentation index

Start here depending on what you need.

| If you want to | Read |
|----------------|------|
| Understand the research problem formally | [mdp-specification.md](mdp-specification.md) |
| Understand how the code is put together | [architecture.md](architecture.md) |
| Understand the real-cluster half | [harness-architecture.md](harness-architecture.md) |
| Make a figure that matches the rest | [figure-design-system.md](figure-design-system.md) |
| Know why something is the way it is | [adr/](adr/) |
| Know what is tested and what is not | [testing-strategy.md](testing-strategy.md) |
| Know what is still wrong or unsettled | [open-questions.md](open-questions.md) |
| Know what happens next | [roadmap.md](roadmap.md) |
| Know what is rotting and what it costs | [tech-debt.md](tech-debt.md) |

## Architecture decision records

| ADR | Decision |
|-----|----------|
| [0001](adr/ADR-0001-simulate-rather-than-measure.md) | Simulate the cluster rather than measure a real one |
| [0002](adr/ADR-0002-flat-declarative-action-space.md) | A flat, declarative action space with no masking |
| [0003](adr/ADR-0003-stable-baselines3-over-hand-rolled-dqn.md) | Use Stable-Baselines3 rather than implement DQN |
| [0004](adr/ADR-0004-analytic-cost-model.md) | An analytic expected-cost model, not discrete-event |
| [0005](adr/ADR-0005-simulator-independent-of-gymnasium.md) | Keep the simulator independent of Gymnasium |
| [0006](adr/ADR-0006-cell-based-fragments-and-open-loop-workload.md) | Cell-based fragments, and an open-loop workload |
| [0007](adr/ADR-0007-real-database-validation.md) | Train in simulation, validate on a real database, and use CockroachDB for it. **Superseded by 0008; contains two corrected factual errors** |
| [0008](adr/ADR-0008-database-selection.md) | Citus over CockroachDB, with a twenty-one-system screen. **Superseded by 0009; the screen stands, the conclusion does not** |
| [0009](adr/ADR-0009-cockroachdb-for-sim-to-real-parity.md) | Reverse to CockroachDB, because sim-to-real transfer requires cost-model parity |
| [0010](adr/ADR-0010-session-scoped-cluster-and-resumable-runs.md) | A session-scoped cluster and episode-checkpointed runs, for a laptop that cannot stay on |
| [0011](adr/ADR-0011-where-the-compute-runs.md) | Keep pre-training, use no GPU, run the cluster in Codespaces; `netem` over Toxiproxy |

## Reading order for someone new

1. `mdp-specification.md` sections 1 and 2, for what the problem is.
2. `architecture.md`, for how the code maps onto it.
3. ADR-0002 and ADR-0004, which are the two decisions that constrain everything
   else, then ADR-0009 for where the project is heading, and
   `harness-architecture.md` for the cluster half. ADR-0007 and ADR-0008 are
   the record of how the database decision was reached, corrected and
   reversed; read them only for that history.
4. `open-questions.md`, which is the honest list of what is not settled.
