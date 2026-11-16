*In-project reading by a separate AI session (constructive role). This is NOT peer review.*

## Summary

An honest, carefully instrumented paper. The strengths are the volatility-conditioned headroom result (paired bootstrap on the existing `summary.csv` files: follow-to-bound gap 57.5 ms [54.3, 61.6] at vol. 4, -1.7 ms [-2.9, -0.7] at 0.5), a harness that executes, reads back and records refusals, and a measured ~13% sim-to-cluster offset. The text leans on the learned policy (Title, II-D, Fig. 1), its least supported claim.

## Major Issues

1. **Framing (Q1, Q5).** The paper promises "RL for fragmentation and allocation", then shows the agent losing on its own objective. Pitch three contributions instead. (a) A measured condition under which learning has room to win (Q3, tight CIs). (b) A Track 2 software artifact for sim-to-cluster placement evaluation: synchronous relocation, read-back, refusal accounting, the systematic 13% offset, the unmodeled Raft-snapshot refusal rule. (c) A learned policy at a **distinct point on the latency/movement frontier**: in Table III static, Lion, agent and follow are all non-dominated. Claim (c) holds only if Experiment 1 does not overturn it.
2. **The transfer claim is weaker than the wording (V-E, Abstract "ranking ... unchanged").** On the cluster, agent against Lion differs by 0.014 cost and 1.2 ms. That is inside noise and driven by imbalance. Lion also lost 20 actions to refusals. The "simulator order" being compared against is the 8-seed mean with imbalance omitted, because the agent cell in Table V is "--". Safer wording: "follow first, static last, agent and Lion-style indistinguishable." Alternatively, fill the cell (Exp. 2).
3. **Confidence intervals are promised but not delivered.** III-H says every result is a mean with a bootstrap CI, but only Q1 has one. Seed variance matters here: follow is 160.4 ms on seeds 0-7 and 148.8 ms on 2000-2007, a gap comparable to the 17.1 ms agent-to-follow difference. Report **paired** per-seed differences. The unpaired follow CI at vol. 4 is [151.4, 170.1], which is too wide to separate anything.
4. **The joint-fragmentation claim is unsupported.** The title and II-D rest on learning splits jointly, but the only evidence is "14 of 200 actions split" (IV-D). There is no ablation (Exp. 5). Either test it or soften II-D to "the action space includes splits".
5. **Internal contradictions.**
   - Intro paragraph 3 says the gap is "41% of its own latency"; IV-C says 36% (57.5/160.4 = 35.9%).
   - Intro says the rule is "within half a millisecond" at slow drift; the data show -1.7 and 1.7 ms.
   - The Fig. 1 caption and III-J describe fine-tuning on the cluster, which was not done. It appears only in V-A as future work.
6. **Title and abstract** oversell the method and undersell the measurement. Possible title: *"When Does Learned Shard Placement Pay Off? Volatility, Movement, and Sim-to-Cluster Transfer on CockroachDB."* Open the abstract with the headroom finding, present the agent as a movement-frugal frontier point (21% of the data at +17 ms; cheapest in simulation for w in 0.50 to 1.82), and say "one episode per policy".

## Minor Issues

- **Hyperparameter sentence** (from `agent/config.py`; check the run manifests for overrides). [256,256] MLP, lr 1e-4, buffer 1e5, batch 128, gamma 0.99, target update 2,000, learning starts 1e4, epsilon 1.0 to 0.05 over the first 30%, 3-step returns, 1e6 steps. Also add that the checkpoint is selected every 1e4 steps on validation seeds 1000-1002, disjoint from test seeds 2000-2007. This heads off a leakage objection. Config defaults are 300k steps and n_steps=1, so confirm the runs' overrides.
- **Strawman risk.** CockroachDB reviewers know its locality-aware lease rebalancing ("follow-the-workload"), so "Static hash ... what production systems do today" (III-E) invites objection. Acknowledge it, say follow-traffic approximates it, and explain why the native rebalancer is frozen (IV-A).
- **Lion-style fairness.** Note the refusal handicap in the Table V caption, not only the text.
- Table III lists the bound at "0.0 GB". Use "n/a", because it relocates for free.
- **Citation spot-check.**
  - Lion's "2.7x / 76.4%" matches its arXiv abstract.
  - "Factor of four in adaptation speed" (II-B) is not in the abstract. Cite the page or cut it.
  - RLRP (II-C) is described in internal detail (reward definitions, zero-initialization). The file header says that every source except Lion and GeoTP was read at abstract level only, which breaks the section's own rule. Confirm that the PDF was read or trim the description.
  - GeoTP "17.7x" was not checked here.
- **AI-use acknowledgment.** Keep it anonymous for double-blind review.

## Editorial

- Spelling is mixed. Unify to American: "centre" (I, IV-C, V), "minimises" (IV-A), "generalised" (IV-G) sit beside "center", "modeled" and "behavior".
- Remove the in-text path `docs/literature-log.md` (II-D).
- Switch `ieeetr` to `IEEEtran` before submission.
- Fig. 1 caption, final clause ("rather than for its popularity"): cut it.

## Suggested cuts (target 0.3 to 0.5 column; this list gives roughly 0.8)

| Location | Action | Approx. saving |
|---|---|---|
| Fig. 2 (`cluster.png`, IV-B) | Delete; Table I carries the same numbers | 0.30 col |
| Fig. 3 (`figure*`) | Make single-column (right panel only, or both stacked small) | ~0.25 col of page |
| II-D, third paragraph ("Two statements...") | Replace with: "We know of no prior work that learns both jointly; on latency alone the agent does not beat the heuristic." | 0.08 |
| II-A, third paragraph ("The weakness is in the word once") | Delete; II-B opening covers it | 0.07 |
| II-B ("Lion establishes three things") | Merge into the "three openings" paragraph | 0.06 |
| II-C ("The common argument across these systems") | Delete | 0.05 |
| III-H Metrics | Drop the p95 and cross-region bullets (unused in Q2 to Q5); make it one sentence | 0.08 |
| III-I Apparatus | Compress to one sentence | 0.06 |
| III-J first paragraph (robotics) | Delete, since no fine-tuning was done | 0.07 |
| IV-A paragraphs 2 and 4 | Delete the re-description of Lion, the bound and masking (duplicates III-E and III-F) | 0.10 |
| V, second paragraph | Compress; it restates the abstract | 0.06 |

**Figure/table changes that pay most.**
1. Replace Fig. 2 with a latency-vs-GB scatter (held-out sim): four agent points, follow, Lion, static, plus the throttled-follow curve. That one picture carries the contribution. `figures/frontier-v4.png` may already be close.
2. Add paired-difference CIs to Tables II and III.
3. Fill in the agent's simulator ms in Table V.
4. Add "imbalance omitted" to the simulator-row header in Table IV.

## Ranked cheap experiments (before 1 Dec)

1. **Throttled follow-traffic in simulation**: act every k in {2, 4, 8} windows, or only above a gain threshold. Seeds 2000-2007, laptop, minutes. Decides whether the agent's frontier point is unique; run before claiming it.
2. **Re-evaluate the four saved agents per seed** on 2000-2007 with imbalance, plus seed 2000 alone. Minutes. Gives paired CIs, full Eq. (1) in Table IV, and Table V's missing cell.
3. **Cluster, workload seeds 2001 and 2002**, all four policies, parallel Actions jobs (~3.3 h each). Turns the ranking into a spread.
4. **Native-rebalancer cluster episode**: static placement with CockroachDB's lease/load rebalancing on, seed 2000, ~3 h. Answers the strawman objection.
5. **Split-masked agent**, 1 to 2 learner seeds at 1e6 steps (~1.6 h each at ~170 steps/s). Tests the joint-fragmentation claim.
6. **Lion-style with retry-on-refusal** on the cluster, seed 2000, ~1 h. Removes the fairness caveat.
7. **Train at w = 0.6**, two learner seeds, ~1.6 h each. Turns the Table IV rescoring into evidence.
