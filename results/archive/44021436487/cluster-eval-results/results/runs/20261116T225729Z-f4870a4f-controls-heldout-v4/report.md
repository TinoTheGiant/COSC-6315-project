# Run `20261116T225729Z-f4870a4f-controls-heldout-v4`

- **When** 2026-11-16T22:57:29.542105+00:00
- **Commit** `6b71d1fab3` on `publish-readiness` (working tree dirty: yes)
- **Config digest** `f4870a4f`
- **Seeds** [2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007]
- **Windows per episode** 200, volatility 4.0
- **Machine** Linux-6.18.44-fc-v509-x86_64-with-glibc2.39, python 3.13.18

## Aggregate over seeds

Mean of the per-seed episode means, with a 95% percentile bootstrap
interval over seeds. `best` is the lowest latency reachable by moving
every lease for free each window at the starting shard boundaries. It
is not an achievable policy, and it is not a global optimum either: a
policy that splits a shard can sit below it.

| Policy | Mean latency (ms) | 95% CI | p95 (ms) | GB moved | Cross-region txns |
|---|---|---|---|---|---|
| Static hash | 192.11 | [187.95, 196.33] | 249.80 | 0.0 | 33.9% |
| Random | 195.46 | [190.28, 200.94] | 263.79 | 134.6 | 35.8% |
| Follow traffic | 148.81 | [143.82, 153.69] | 220.17 | 867.7 | 21.5% |
| Best per window (fixed shards) | 91.02 | [85.90, 97.02] | 136.64 | 0.0 | 15.6% |
| Lion-style co-location | 179.98 | [166.22, 195.61] | 258.85 | 28.8 | 4.1% |
| follow2 | 157.18 | [152.25, 162.02] | 228.64 | 696.3 | 22.3% |
| follow4 | 171.82 | [165.54, 178.10] | 242.32 | 405.1 | 25.7% |
| follow8 | 185.84 | [179.74, 192.44] | 257.16 | 157.6 | 27.2% |
| random-valid | 210.76 | [206.71, 215.40] | 269.84 | 438.5 | 55.6% |

Follow traffic improves on static hash by **22.5%** of mean latency.
Headroom between follow traffic and the fixed-shard bound: **57.79 ms** (38.8% of follow traffic). A small number here means the reactive heuristic is already close to the best that lease movement alone can do, and that what is left for a learned policy is movement cost rather than latency.

## What each policy did with its windows

Share of decision windows spent on each kind of action, and the share
of chosen actions that were inapplicable in the state they met. An
inapplicable action costs a small penalty and changes nothing.

| Policy | Move lease | Move replica | Split | Nothing | Inapplicable |
|---|---|---|---|---|---|
| Static hash | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |
| Random | 46.2% | 46.2% | 7.1% | 0.4% | 81.4% |
| Follow traffic | 56.0% | 43.4% | 0.0% | 0.6% | 0.0% |
| Best per window (fixed shards) | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |
| Lion-style co-location | 10.1% | 1.4% | 0.0% | 88.5% | 0.0% |
| follow2 | 43.3% | 34.8% | 0.0% | 21.9% | 0.0% |
| follow4 | 24.9% | 20.2% | 0.0% | 54.8% | 0.0% |
| follow8 | 12.5% | 7.9% | 0.0% | 79.6% | 0.0% |
| random-valid | 37.4% | 55.6% | 7.0% | 0.0% | 0.0% |

## Reproducing this run

```
git checkout 6b71d1fab3
python scripts/run_experiment.py --config results/runs/20261116T225729Z-f4870a4f-controls-heldout-v4/config.json \
    --seeds 8 --seed-start 2000
```
