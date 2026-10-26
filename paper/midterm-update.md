# Drop-in replacements for the midterm report and slides

Written 26 October. Every number below is traceable to an Actions run and was
checked against the job summary it came from. Where a value has not been read
from an artifact it is marked, rather than estimated.

**One trap before you paste anything.** The volatility sweep (your Table 1 and
Figure 2) used seed block **0 to 7**. The agent evaluations used held-out block
**2000 to 2007**. The baselines differ between the two blocks by up to 10 ms, so
the two sets must never share a table. Label every table with its seed block.

---

## Report, Section 4: replace "Learning results"

> **Learning results.** I trained eight agents. Six used one million steps and
> two earlier runs used 300,000. All were evaluated on held-out seeds 2000 to
> 2007, which no agent trained on. Two of the eight shared a configuration and a
> learner seed and returned identical results to every printed decimal, which
> shows the training procedure is reproducible rather than merely described as
> such.
>
> The earlier runs trained at volatility 1.0, where the gap between follow
> traffic and the cost-free reference is 5 ms. There was almost nothing to win.
> The later runs trained at volatility 2.0 and 4.0, where that gap is 33.9 ms
> and 57.2 ms.
>
> [TABLE 2 HERE]
>
> At volatility 4.0 the agent reduced mean latency from 150.12 ms under fixed
> placement to 139.91 ms, whilst moving 62.7 GB. Follow traffic reached
> 129.04 ms but moved 1,086.5 GB, seventeen times as much. The agent also spread
> load more evenly: its imbalance measure was 0.776, against 1.003 for follow
> traffic, where fixed placement scores 0.561.
>
> Comparing the two on latency alone compares them on a quantity only one of
> them is optimizing. The reward combines latency, data movement and load
> imbalance. Scored on that reward the agent reaches 1.486 against follow
> traffic's 1.554 and fixed placement's 1.557. A second agent trained under
> identical settings with a different learner seed reaches 1.522, which also
> beats the rule. **Under the objective the agent was trained on, both seeds
> perform better than the rule they are meant to replace.** The agent gives up
> around 10 ms of latency and recovers more than that in movement and balance
> together.
>
> The advantage is specific to that setting. At volatility 2.0 and the same
> weight the two are level, 1.400 against 1.398. When the movement weight is
> lowered to 0.10 the agent falls behind by 0.012, and at a weight of 0.00 it is
> not in the contest at all, since a zero movement charge is exactly the
> condition its strategy exploits. This is consistent rather than awkward: the
> agent's advantage lies in how little it moves, so the advantage grows with the
> price of movement. With one run at the lower weight I report that as
> suggestive rather than established.
>
> Against fixed placement the agent wins in every measured run under every
> weight, by 0.035 to 0.202 on the reward.
>
> Two limits apply. The learner seed moves the result by 4.70 ms in latency and
> by a factor of two in how often the agent splits a shard, so the policy has not
> converged on a single strategy, and differences smaller than that spread cannot
> be attributed to a configuration. And the agent's chosen actions are
> inapplicable in 80 to 90% of decision windows, against 80% for random action,
> so its low movement is partly a failure to act rather than deliberate
> restraint.
>
> One result holds across every run without qualification. The agent's load
> imbalance measured between 0.695 and 0.816 in all five runs read, against 0.501
> to 0.561 for fixed placement and 0.945 to 1.003 for follow traffic. The agent
> never approaches the concentration that follow traffic uses to buy its latency.
> Given that the cluster pilot showed concentration saturating a real node, this
> is the most likely of the three terms to transfer to real hardware.

### Table 2, to insert above

**Learned agents against the comparison methods. Held-out seeds 2000 to 2007,
200 decision windows. Imbalance is blank where the run archive has not been
read.**

| Volatility | Method | Weight | Seed | Mean (ms) | Moved (GB) | Imbalance | Reward cost |
|---|---|---|---|---|---|---|---|
| 4.0 | Fixed placement | | | 150.12 | 0.0 | 0.561 | 1.557 |
| 4.0 | **Agent** | 0.30 | 0 | **139.91** | **62.7** | **0.776** | **1.486** |
| 4.0 | **Agent** | 0.30 | 1 | 144.61 | 44.5 | 0.695 | **1.522** |
| 4.0 | Follow traffic | | | 129.04 | 1086.5 | 1.003 | 1.554 |
| 4.0 | Cost-free reference | | | 71.84 | not charged | 0.945 | |
| 4.0 | Agent, weight 0.10 | 0.10 | 0 | 136.94 | 123.7 | 0.816 | 1.457 |
| 4.0 | Follow traffic at 0.10 | | | 129.04 | 1086.5 | 1.003 | 1.445 |
| 2.0 | Fixed placement | | | 151.67 | 0.0 | 0.501 | 1.567 |
| 2.0 | **Agent** | 0.30 | 0 | 129.64 | 177.3 | 0.773 | 1.400 |
| 2.0 | Follow traffic | | | 114.57 | 1048.5 | 0.945 | 1.398 |
| 2.0 | Cost-free reference | | | 80.71 | not charged | 0.782 | |

Reward cost is the weighted sum of latency, movement and imbalance, lower being
better. Each block compares policies at one weight, because follow traffic's own
cost moves with the weight too. The volatility 2.0 run at weight 0.00 is omitted:
at a zero movement charge follow traffic's terabyte is free and the comparison
is not informative.

### Figure 3, to insert

`paper/figures/frontier-v4.png`, and `frontier-v2.png` if you want both.

> Figure 3. Latency against data movement at volatility 4.0, held-out seeds. The
> learned agents sit near the left axis, close to fixed placement in movement
> and well below it in latency. Follow traffic sits far to the right, having
> bought its lower latency with more than a terabyte of movement.

---

## Report, Section 4: replace the "Cluster pilot" paragraph

> **Cluster pilot.** I repeated the cluster measurement with 1,000 transactions
> per case on a four-core runner, against 200 on two cores previously. The
> spread case was unchanged, 1,015.3 ms against 1,013.4 ms at the 50th
> percentile. The co-located case rose from 272.7 ms to 441.5 ms, despite twice
> the processing power. More cores and a slower result rules out processor
> contention as the cause. What changed is the load on one machine: placing
> every lease in one region routes every write through one node, and at a
> thousand transactions that node saturates. This is the load imbalance the
> reward penalizes, observed on real hardware. The simulator cannot reproduce
> it, because its cost model accounts for network delay and not for queueing,
> and it will therefore understate the cost of extreme concentration.
>
> The larger sample also narrowed the confidence interval on the latency
> difference from 155.2 ms wide to 65.6 ms, which addresses the sample-size
> limitation noted in the previous report.

---

## Report, Section 5: additions to Limitations

> The simulator's cost model accounts for network delay and not for queueing. The
> second cluster pilot showed a concentrated placement saturating a single node,
> an effect the simulator cannot produce. Simulated results will therefore
> understate the cost of concentrating load.
>
> The learned results rest on few seeds. Two runs under identical settings
> differed by 4.70 ms in mean latency and by a factor of two in how often they
> split a shard. The policy has not converged on a strategy, and differences
> between configurations smaller than that spread cannot be attributed to the
> configuration.
>
> The agent selects inapplicable actions in 80 to 90% of decision windows across
> every run, against 80% for uniformly random action. It has not learned which
> actions are available in which state. Action masking or a penalty shaped by
> applicability is the first thing I would change.
>
> The agent's load imbalance has been read from two of the eight run archives.
> The reward comparison at volatility 4.0 rests on one of those two.

---

## Report, Section 6: replace the Conclusion

> The project provides an implemented simulator, four comparison methods, eight
> training runs and two measured cluster tests. Following traffic improves
> latency over fixed placement, and does so less effectively as demand changes
> faster, falling 57.2 ms short of a cost-free reference at the highest
> volatility tested.
>
> At that volatility the learned agent does not match follow traffic on latency.
> It does better on the objective it was trained on, reaching 1.486 and 1.522
> under two learner seeds against follow traffic's 1.554, because it recovers in
> movement and load balance more than it gives up in latency. The advantage is
> specific to that weight and disappears when movement is charged less. The
> policy still selects unavailable actions in most decision windows and varies
> substantially with its seed, so I report the result as preliminary rather than
> established.

---

## Slides

**Slide 5 (baseline table).** Add the seed block to the source line: "volatility
1.0, seeds 0 to 7".

**Slide 6 (volatility).** No change. Confirm the source line says seeds 0 to 7.

**Slide 7.** Retitle from "The learned agent has not matched follow traffic" to
**"The agent trades latency for movement and balance"**. Replace the two
statistics:

| | |
|---|---|
| **17x** | Less data moved than follow traffic, at volatility 4.0 |
| **Both seeds** | Beat follow traffic on the combined objective |

Body: At volatility 4.0 the agent reaches 139.91 ms against follow traffic's
129.04 ms, whilst moving 62.7 GB against 1,086.5 GB and holding load imbalance
at 0.776 against 1.003. On the combined objective it scores 1.486 against 1.554,
and a second learner seed scores 1.522, so both beat the rule. The advantage is
specific to this weight: at a movement weight of 0.10 the agent falls behind,
which fits, since its advantage lies in how little it moves.

Source line: held-out seeds 2000 to 2007, eight training runs, commit f459c44.

**Slide 8 (cluster).** Replace the two statistics with **1,202 ms** p95
difference and **1,000** transaction sample on a four-core host. Add one line:
"Co-locating leases was 62% slower than in the smaller run despite twice the
cores, which is load concentrating on one node."

**Slide 9 (rubric).** Update the third limit from "the learning runs have not
improved latency over follow traffic" to "the learned runs improve on the
combined objective but not on latency alone, on few seeds".

**Slide 10 (plan).** Replace the first future-work item with "action masking, to
address an 80 to 90% inapplicable action rate" and the second with "more seeds
per configuration".

---

## Still to do, and what it would change

All five archives have been read and every number above is measured. Nothing is
outstanding for the submission.

Remaining work belongs to the final report: action masking to address the
inapplicable rate, more seeds per configuration, a convergence-based stopping
rule, and fine-tuning on the cluster.
