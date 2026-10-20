# The paper

IEEE conference format. Build with:

```
pdflatex main && bibtex main && pdflatex main && pdflatex main
```

Overleaf works too: upload the whole `paper/` folder and set `main.tex` as
the root document.

## State of the draft

| Section | State |
|---|---|
| Abstract | Not written. **Write it last**, after Evaluation |
| 1 Introduction | Written |
| 2 Related Work | Written, with three `TODO` groups of citations to add |
| 3 System Model and Methodology | Written |
| 4 Evaluation | **Outline only.** Every number is in the comments, with its source |
| 5 Conclusion and Future Work | **Outline only** |

Evaluation and Conclusion are outlines on purpose. The midterm rubric awards
zero points for their content and awards the structure separately, so they
exist, they show the shape of the argument, and they carry every measured
number with the run that produced it.

## Where the numbers come from

Never take a number from these files or from memory. Take it from the run
directory, which holds the configuration, the seeds and the commit alongside
the result.

| Result | Source |
|---|---|
| Cluster gate | `docs/results-log.md`, run 2. Actions → Cluster pilot #2 |
| Baseline comparison | Actions → Experiments #1, artifact `run-...-baseline` |
| Volatility sweep | Actions → Sweep #1, artifact `sweep-volatility-...` |
| Agent, with migration penalty | Actions → Train agent #1 |
| Agent, without migration penalty | Actions → Train agent #2 |

## Figures

`figures/` is empty. Three are needed:

1. **Architecture.** Simulator on the left, CockroachDB cluster on the right,
   the three parity constraints between them. Draw this by hand.
2. **Volatility sweep**, two panels. Already rendered: it is `sweep.png` in
   the Sweep artifact. Copy it in.
3. **Training curve**, held-out latency against timestep for both agent runs.
   Plot it from `eval_history.json` in each model artifact.

Figures 2 and 3 use the project's figure style, which is documented in
`docs/figure-design-system.md` and is built to survive a grayscale print.

## On the writing

The audience is assumed to have no background in distributed databases. Every
term is explained plainly where it first appears: shard, replica, primary,
two-phase commit, Q-network. Keep that up in the sections still to be written.
A reader who has to look something up has been failed by the paper.
