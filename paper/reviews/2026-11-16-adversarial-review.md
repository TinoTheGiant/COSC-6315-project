This is an in-project adversarial reading by a separate AI session; it is NOT peer review.

Role: Reviewer 2 (adversarial). Manuscript: paper/ccgrid.tex with sections/full/01 to 05, PDF ccgrid-built.pdf (10 pages). Date: 2026-11-16. Unit tests were not run (gymnasium absent; nothing installed).

## Summary

The paper trains a masked, 3-step DQN for shard lease/replica/split decisions in a six-region simulator and runs one checkpoint on a netem CockroachDB cluster. Arithmetic is largely traceable to results/recorded/*.csv. The difficulty is what the numbers support: at the trained weight the agent loses to the heuristic in both environments; the "bound" is not a bound; the Lion-style baseline is geography-blind and idle 90 to 95% of the time; and the transfer claim rests on one episode whose only informative pair (agent vs Lion) is decided by a term that is counted, not measured. Recommendation: reject in current form.

## Major Issues

1. **The "bound" is neither lease-only nor a lower bound.** Sec. III-E and IV-A say it relocates every lease/primary for free. Code calls `set_primary` (catalog.py:153-174), which acquires a replica and evicts the old primary's, and picks each target greedily from reads+writes only, ignoring transactions, 2PC and the replication term (run_experiment.py:161-166). Follow beats it on 7 of 8 seeds at volatility 0.5 (sweep-v0.5 summary.csv). The text's explanation ("bound moves leases only", Sec. IV-D) is contradicted by the code. The headline "57.5 ms room" depends on it. *Fix:* compute a true per-window minimum at fixed boundaries (exhaustive or ILP over 6^6 lease assignments including 2PC), or rename it "greedy oracle" and drop "bound" language.

2. **Lion-style baseline is a strawman, undisclosed.** Its cost (policies.py:221-231) has no client-location term and omits Lion's predictor (docstring, policies.py:147-152); it plans from one window, and noops in 89.5 to 95.4% of windows (summary.csv `frac_noop`). The paper calls it "the strongest published idea we could adapt" (Sec. III-E) without disclosing either departure. Beating a geography-blind planner on a geographic problem is not evidence. *Fix:* disclose departures; add a geography-aware variant (Lion grouping + latency-minimizing destination) and a forecast-driven variant.

3. **Primary hypothesis is falsified at the trained weight; the rescue is post hoc.** At w=0.30 agent 1.686 vs follow 1.618 (sim), 2.027 vs 1.890 (cluster). The w>0.50 "win" (Table IV) rescores fixed trajectories, omits imbalance in the sim rows, and is not supported by the cluster (agent never cheapest). The abstract and conclusion foreground the rescoring. *Fix:* train at w in {0.6, 1.0}; report full Eq. (1) including the agent's imbalance (summary.csv can be regenerated cheaply).

4. **Transfer claim is unsupported beyond n=1.** Static-worst and follow-best are near certain a priori; the only informative comparison is agent vs Lion. Their latency differs by 1.16 ms (inside 1 to 2 ms SE); on latency + migration alone Lion wins (1.921 vs 1.947); ordering at w=0.30 is produced by imbalance (0.801 vs 1.202), which on the cluster is "counted, not measured" (harness/env.py:23-28). At w=0.6 the cluster order (follow, Lion, agent, static) differs from the sim order (agent, follow, Lion, static). The sim reference is an eight-seed mean of four agents without imbalance, compared to a single cluster seed with imbalance; the agent's own sim latency on seed 2000 was "not run" (cluster-eval.csv), although it costs seconds. *Fix:* run the agent in sim on seed 2000; at least 5 workload seeds x 2 learner seeds on cluster; report Kendall tau with an interval; restrict the claim.

5. **Cluster "GB moved" and imbalance are catalogue accounting.** `bytes_moved` is the catalogue's account (harness/executor.py:179), so 771.6 GB on a 1 GB cluster and "data moved agrees to the decimal" (Sec. IV-F) is tautological. *Fix:* say so; measure physical bytes from range stats.

6. **"Joint fragmentation" is the novelty claim but is untested.** Splits are midpoint-only, irreversible (no merge), capped at 20; the agent's 14 splits exactly exhaust the cap from 6 shards. No ablation shows splitting helps. *Fix:* split-disabled ablation; otherwise retitle around placement.

7. **Model description does not match code.** (a) Eviction is the farthest *non-primary* replica (catalog.py:248-252); paper omits "non-primary" although the docstring says the paper must state it. (b) Observation (Sec. III-D) omits the three fragment x origin demand blocks, the main signal (observation.py:41-47); Sec. IV-A says "per-region read and write counts", also wrong. (c) Migration term is bytes/(dataset x 1/6) per window (reward.py:27, config.py:160); Eq. (1)'s 2000 = 200 windows x 10 GB is unexplained, and "fraction of the dataset" is inexact. (d) Checkpoint selection is on latency only over 3 episodes, seeds 1000-1002 (train.py `_Eval`; agent/config.py:72-78), not on the objective the paper says the agent is judged on. (e) Code defaults are n_steps=1 and nearest_replica (agent/config.py:54, config.py:126); heldout-rf3.csv records neither n_steps nor learner seed.

8. **Controls and statistics.** Random is 77.1% inapplicable (sweep-v4) and moves 5x less than follow, so "movement by itself buys nothing" (Q2) is confounded. Use a movement-matched random over applicable actions. Sec. III-H promises bootstrap CIs over eight seeds; no table reports one, and p95 and cross-region fraction are never reported. Four learner seeds give no interval; "plateau" (160 to 190 ms band, best checkpoints at 60k to 170k) indicates instability or early overfitting, not a plateau; show the curves.

9. **Missing related work a CCGrid reviewer will expect:** Akkio (OSDI 2018, locality-driven geo data placement), SLOG (VLDB 2019) and DynaMast (ICDE 2021) dynamic remastering (exactly `move_lease`), Facebook Shard Manager (SOSP 2021), CockroachDB multi-region (SIGMOD 2022, which also governs the "strong read at leaseholder" assumption), and NeuroShard (MLSys 2023, learned sharding). Location-aware replicated state machines (e.g., WPaxos) and P-Store (predictive repartitioning) also bear on "anticipation". Sec. II-B's statement that none of the cited systems' cost models "carries a term for geographic distance" holds for those systems only; Akkio and SLOG show it does not hold for the area, and the gap framing (Sec. II-E) leans on it.

## Minor Issues

- Intro: follow is "within half a millisecond" of the bound at slow drift; CSV gives -1.7 and +1.7 ms.
- Intro: gap is "41% of its own latency"; Sec. IV-D says 36% (57.531/160.376 = 35.9%). 41% is untraceable.
- Sec. IV-D: 25.9 ms gap at vol 2; CSV gives 25.846 (25.8). Computed from rounded table values.
- Conclusion "stopped improving early in every run" vs Sec. IV-E "three of four".
- Table III learner seeds labelled 1 to 4; results-log records run IDs only (earlier round used 0 to 3). Untraceable.
- Sec. III-I "Runs execute on GitHub Actions" contradicts the sweep manifests (`ci: no`, `dirty: yes`; results-log: "Run in the sandbox"). The held-out and cluster numbers come "from the job summaries", not run directories.
- Fig. 1 says "fine-tuned on the right"; no fine-tuning was done.
- Follow GB "rising ... to about 900" is non-monotone (900.2 then 873.7).
- Split renumbers fragment indices (catalog.py:276-278), so action index f changes meaning mid-episode; discuss.
- Simulator charges migration as instantaneous with no latency (simulator.py:14-17); relevant to the Lion refusal finding.
- `niu2026allocation` lacks arXiv ID; `huang2022masking` and `zahavy2018elimination` in bib but uncited, although masking is a stated contribution.
- Policies docstring calls follow-traffic "not a serious opponent" and says baselines belong in a nonexistent `fragalloc/baselines/` (stale).

## Editorial

- Sec. II-E ("What is new here") then states the contribution "is not claimed to be new"; this reads as self-defeating. State scope precisely instead.
- Sec. II cites `docs/literature-log.md`, an internal path reviewers cannot see. Remove.
- Bibliography style is `ieeetr`, not `IEEEtran`; fix before submission.
- PDF metadata carries a CST timestamp; harmless but scrub. No other identifying strings found in PDF text.
- **No acknowledgments section.** IEEE requires disclosure of AI-generated content (text, code, figures) in the acknowledgments; if AI tools were used, add an anonymous disclosure.
- No anonymized artifact link despite the reproducibility claims in Sec. III-I; provide one (e.g., anonymous.4open.science), and ensure any public repository or course deck does not de-anonymize.

## Methodological Assessment

Same seeds and loop: yes (`rollout` shared). Same action budget: nominal only (Lion idles; random mostly inapplicable). Lion faithfulness: low, undisclosed. Bound: mislabelled. Learner seeds: 4, no interval. Cluster: 1 episode, 1 seed, 1 checkpoint; two of three objective terms computed rather than measured. Reporting: CIs promised, absent. Provenance: good for the sweep; weaker (job summaries) for the agent and cluster rows. Desk-reject risk: moderate (style file, internal path, missing AI disclosure if applicable); rejection risk on substance: high.

## Falsification Test

The only pre-registered falsification (placement gate, scripts/falsification_test.py) passed: p95 gap 1337.8 ms, CI [1168.5, 1407.8]. The paper's hypothesis has no pre-registered criterion. Engaged honestly: (i) "better trade-off than a reactive heuristic" is falsified at the trained weight in both environments (sim 1.686 vs 1.618; cluster 2.027 vs 1.890); (ii) "ranking transfers" is not falsified but also not tested: n=1, the decisive pair is within noise on latency, flips without the imbalance term, and flips at w=0.6. The paper should state that (i) failed and that (ii) remains an anecdote, rather than reframing through rescoring.
