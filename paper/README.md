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

Three figures, and none of them needs drawing by hand.

| | Figure | Where it comes from | What you do |
|---|---|---|---|
| 1 | Architecture | Drawn in TikZ, inline in `sections/03-system-model.tex` | Nothing. It compiles with the paper |
| 2 | Volatility sweep, two panels | `sweep.png` in the **Sweep** artifact | Download the artifact, copy the file into `figures/` |
| 3 | Training curve with baselines | `figures/training-curve.png` in the **Train agent** artifact | Download, copy in |

Figures 2 and 3 are produced by the workflow runs that produced their data,
which is deliberate. A figure reconstructed later from a downloaded archive is
how a curve ends up plotted against baselines measured in a different
environment.

The cluster gate is a **table**, not a figure. Its source records only summary
statistics, so a bar chart would show three numbers in more space than the
three numbers take.

Both generated figures use the project's figure style, documented in
`docs/figure-design-system.md` and built to survive a grayscale print: one
chromatic series for the agent against graded grays, every series carrying a
mandatory dash pattern.

### Adding them to the text

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=\columnwidth]{sweep-volatility.png}
  \caption{...}
  \label{fig:sweep}
\end{figure}
```

Figure 2 is two panels wide, so it may read better as `figure*` spanning both
columns with `width=\textwidth`. Decide that when you see it in place.

### If a figure needs regenerating locally

```bash
python scripts/assemble_sweep.py --over volatility
python scripts/plot_training_curve.py results/models/<id> \
    --baselines results/runs/<eval-run-id> \
    --out paper/figures/training-curve.png
```

The `--baselines` argument is not optional in practice. Without it the curve
has no reference lines, and a learning curve without them tells a reader that a
number went down without telling them whether it went down far enough.

## On the writing

The audience is assumed to have no background in distributed databases. Every
term is explained plainly where it first appears: shard, replica, primary,
two-phase commit, Q-network. Keep that up in the sections still to be written.
A reader who has to look something up has been failed by the paper.

## Building the PDF locally

`IEEEtran.cls` v1.8b sits in this directory because CTAN is unreachable from
both the build container and the development machine, and `texlive-publishers`
has no installation candidate on this image. The file came from the npm package
`latex-paper-skills`, at
`package/skills/latex-paper-skills/references/skills/arxiv-paper-writer/assets/template/IEEEtran.cls`.

That copy arrived with exactly one corruption, and it will kill the build if it
is ever restored from the same source: line 2257 read

    \def\@endIEEEitemize“{\endlist}

with a stray left curly quote, which makes every `\end{itemize}` a fatal error.
The copy here has it removed. A scan for non-ASCII bytes over the whole file now
returns nothing, so the rest of it is byte-clean.

`IEEEtran.bst` is not obtainable here at all, so `main.tex` uses
`\bibliographystyle{ieeetr}`, which ships with texlive base and produces IEEE
numbered references. Overleaf has `IEEEtran`, so that one line can be switched
back there.

    pdflatex main && bibtex main && pdflatex main && pdflatex main

Last clean build: 10 pages, no errors, no undefined references, one overfull
hbox of 14.2 pt.
