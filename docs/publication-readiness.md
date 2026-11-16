# CCGrid 2027: publication readiness, 16 November 2026

Audit of `paper/ccgrid.tex` at commit `ac89a12`, and what commit `5bfcfec`
(branch `publish-readiness`) changed. Method: the research-integrity rules
(every number traced to a run, every check able to fail), the architecture
and coding guidelines, and two in-project AI reviews saved in `paper/reviews/`.
Those reviews are readings by separate AI sessions. They are not peer review.

## Verdict

Submittable after the blockers below. The paper is honest about a modest
result, the arithmetic is right, and the sweep reproduces exactly. The weak
points a CCGrid reviewer will press are the n = 1 cluster comparison, the
untested fragmentation claim, and the Lion-style baseline. Those need
experiments, not wording.

## Dates (EasyChair, all AoE)

| | Date |
|---|---|
| Abstract registration | 24 November 2026 |
| Paper | 1 December 2026 |
| Notification | 1 February 2027 |

10 letter pages including references, IEEE template, double-blind, and IEEE's
rule that AI-generated content is disclosed in the acknowledgments. Track 2
(Software Systems) lists distributed storage, replication and placement.

## Blockers

1. **Archive the Actions artifacts. The cluster ones expire 15 December**,
   before notification; the training ones expire 13 February. Tables I and V
   rest on them. From Git Bash in the repo:

   ```bash
   mkdir -p results/archive
   for id in 43751004009 43751092905 43674067630 43674455394 43674558770 43674597349; do
     gh run download "$id" -R TinoTheGiant/COSC-6315-project -D "results/archive/$id"
   done
   du -sh results/archive/*
   ```

   About 40 MB, mostly the four models. Commit them, or deposit them on Zenodo
   and commit the DOI.

2. **Fill the agent's missing numbers from those artifacts.** The training
   runs' `summary.csv` already holds the agent per seed on 2000 to 2007, which
   gives its imbalance (so Table IV can use the full Eq. 1) and its simulator
   latency on seed 2000 (the "--" in Table V). No retraining needed:

   ```bash
   python - <<'EOF'
   import glob, pandas as pd
   for f in sorted(glob.glob("results/archive/436*/**/summary.csv", recursive=True)):
       s = pd.read_csv(f); a = s[s.policy == "agent"]
       print(f, "imbalance", round(a.load_imbalance.mean(), 3),
             "seed 2000 ms", a[a.seed == 2000].mean_latency_ms.round(2).tolist())
   EOF
   ```

3. **Confirm the AI acknowledgment.** It names Claude only. If Codex, Gemini
   or any other tool wrote, checked or reviewed anything, add it and what it
   did (the TODO comment in `ccgrid.tex` marks the spot).

4. **Switch to `IEEEtran.bst` on Overleaf** (one line, commented in
   `ccgrid.tex`) and check the page count again. The local build is exactly
   10 pages with `ieeetr`, with one 7.8 pt overfull line.

5. **Anonymised artifact link.** The paper cites `results/recorded/*.csv` in
   captions but links nothing. Build the anonymised repository (planned for
   later) and add an anonymous.4open.science link before 1 December, or drop
   the file paths from the captions.

6. **Register the abstract by 24 November.** `paper/ccgrid-abstract.md` matches
   the paper's new abstract.

## What commit 5bfcfec changed

Wrong or stale statements, now corrected:

| Where | Was | Now | Evidence |
|---|---|---|---|
| Intro | gap is "41%" of follow's latency | 36% | 57.531 / 160.376, `sweep.csv` |
| Intro | follow "within half a millisecond" of the reference at slow drift | within 2 ms | -1.73 and 1.72 ms |
| IV-C | gap 25.9 ms at volatility 2 | 25.8 | 25.846, unrounded |
| III-E, IV | "bound", "lowest latency reachable", "moves leases only" | per-window oracle; not a lower bound | `run_experiment.py:161-166` sets each primary greedily and `set_primary` adds a replica |
| Fig. 1, III-J | agent "fine-tuned" on the cluster | run unchanged; fine-tuning is future work | Cluster evaluation 1; ADR-0020 |
| Abstract, I, V | ranking of all four policies carries over | heuristic cheapest and static dearest on both; agent and Lion-style not separable | cost gap 0.014, latency gap 1.2 ms, sampling error 1 to 2 ms |
| III-D, IV-A | observation is per-region request shares | per-shard demand by region of origin | `observation.py:41-47` |
| III-D | evicts the replica furthest from r | the non-primary replica | `catalog.py` `move_replica_to` |
| III-E | static hash is "what production does today" | key-hash floor; follow-traffic is the idea behind CockroachDB's follow-the-workload | CockroachDB docs |
| III-J | CockroachDB chosen "over sixteen" systems "on one criterion" | from more than twenty, because it has a synchronous statement for each action | ADR-0008 table, ADR-0009 |
| III-I | all runs on Actions | training and cluster on Actions; simulator runs deterministic | sweep manifests |
| III-H | every result has a bootstrap CI | CIs where a comparison turns on a difference | none were reported |
| II-D | repository path in a double-blind paper | the indexes named | |

Added: IEEE AI acknowledgment; hyperparameters and checkpoint rule (chosen
on latency, `agent/train.py:142`); paired 95% interval for the volatility-4 gap,
[54.3, 61.6] ms, from the new `scripts/sweep_gap_ci.py`; Lion-style
disclosures (no distance term, no predictor, idle in 90 to 95% of windows);
cluster accounting stated as counted, not measured; the random baseline's 77%
inapplicable draws; five citations (Fluidity, CockroachDB multi-region,
Neuroshard, Costa Filho et al., CockroachDB follow-the-workload); bib venue
fixes (Gymnasium, dueling, PER, Niu arXiv ID, two missing issue numbers).
Sweep figure relabeled "oracle". American spelling throughout.

Cut, to stay at 10 pages: Fig. 2 (it repeated Table I), the metrics list, the
re-description of baselines in IV-A, two restating paragraphs in II, the
Rainbow components' separate citations, and GeoTP's "17.7 times", which
nobody had checked.

Docs: ADR-0020 (zero-shot cluster evaluation, Proposed, needs your sign-off);
ADR-0017 marked Accepted on Run 6; ADR index now lists 0012 to 0020;
`docs/literature-log.md` has today's searches.

## Experiments that would most strengthen it, in order

| # | Experiment | Cost | Answers |
|---|---|---|---|
| 1 | Follow-traffic throttled to every 2, 4, 8 windows, held-out seeds | minutes, laptop | Whether the agent's latency/movement trade is unique or a slowed heuristic matches it. Run before leaning on "a fifth of the data" |
| 2 | Random over applicable actions only, movement-matched to follow | minutes | Closes the confound in Q2 (random moves 5x less than follow) |
| 3 | Cluster episodes on workload seeds 2001 and 2002, all four policies | about 3.3 h each, parallel Actions jobs | Turns the n = 1 ordering into a spread |
| 4 | Agent with splits masked, 1 to 2 learner seeds | about 1.6 h each | Whether fragmentation earns its place in the title |
| 5 | Train at w = 0.6, two learner seeds | about 1.6 h each | Turns the Table IV rescoring into evidence |
| 6 | Static placement with CockroachDB's own rebalancing on, seed 2000 | about 3 h | The production comparison a reviewer will ask for |

## Review findings still open (need your decision)

From the adversarial reading, checked against the code where marked:

- **Joint fragmentation is the headline but untested.** Splits are
  midpoint-only, irreversible, capped at 20; the agent's 14 splits exactly use
  the cap from 6 shards. Run experiment 4, or soften the title and II-D to
  "the action space includes splits". Checked: cap and counts match.
- **Lion-style is weak.** Now disclosed, but a geography-aware variant would
  make the comparison fair. Checked: `policies.py` cost has no distance term.
- **The oracle is not a minimum.** Renamed rather than replaced. An exact
  per-window minimum over lease assignments with the 2PC term would restore a
  true bound.
- **Missing related work named from memory by the reviewer, not yet
  verified:** Akkio (OSDI 2018), SLOG (VLDB 2019), DynaMast (ICDE 2021),
  Facebook Shard Manager (SOSP 2021), P-Store. Akkio and SLOG bear directly on
  the claim that no cost model in the area carries geographic distance. Look
  them up before adding. Shard Manager also turned up in today's Consensus
  search.
- Split renumbers fragment indices mid-episode; the simulator treats migration
  as instantaneous. Both worth one sentence in Threats to validity.
- `huang2022masking` and `zahavy2018elimination` are in the bib but uncited;
  cite them where masking is introduced if space allows.

From the constructive reading: reframe the title and abstract around the
measured condition and the movement-frugal trade (suggested: "When Does
Learned Shard Placement Pay Off? Volatility, Movement, and Sim-to-Cluster
Transfer on CockroachDB"); replace the freed figure slot with a
latency-against-GB scatter; make Fig. 3 single-column if space is needed.

## Integrity record

```
Check: test suite at 5bfcfec
Result: 239 passed (pytest, Python 3.13, CPU torch)

Check: sweep reproduces from a fresh checkout
Binds: commit ac89a12, config digest f4870a4f
Result: volatility-4 run regenerated; max |difference| 0.0 on latency, GB, imbalance

Check: held-out baselines (seeds 2000-2007) and seed-2000 simulator column
Result: static 192.108, random 195.464, follow 148.814, Lion 179.980, oracle 91.023;
seed 2000 follow 148.138, Lion 153.006, static 182.442. All match the recorded CSVs.

Check: scripts/sweep_gap_ci.py
Failure control: +10 ms planted on follow must move the gap by exactly 10. Observed: 57.53 -> 67.53.
```

Blocked: downloading the Actions artifacts from the audit workspace (storage
host not on its allowlist), so the agent rows rest on job summaries as
before. Nine references were checked against Crossref today and the dueling
paper against PMLR; the others rely on the 26 October Crossref verification. "Factor of four" (Lion) was cut from the
text; GeoTP's 17.7x was cut, unverified.

Fixes read by a third AI session (a verifier that made none of them; not peer
review). It confirmed every number, code description and the build, and found
six problems, all fixed in the same commit: Fluidity and Neuroshard sentences
that went past their abstracts, the Q5 sentence that did not name the
simulator source of its ordering, the cluster data-moved sentence (it is the
catalogue's account of each applied action), two leftover "pre-trained", and
the sweep table's 7.8 pt overrun. The final build is 10 pages with no
warnings. Still unverified: whether Neuroshard's published title carries a
subtitle (Crossref gives only "Neuroshard"); check it in the ACM Digital
Library.
