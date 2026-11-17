# Run `20261116T032622Z-f4870a4f-sweep-v4`

- **When** 2026-11-16T03:26:22.131639+00:00
- **Commit** `18b0c0fdb5` on `main` (working tree dirty: yes)
- **Config digest** `f4870a4f`
- **Seeds** [0, 1, 2, 3, 4, 5, 6, 7]
- **Windows per episode** 200, volatility 4.0
- **Machine** Linux-6.18.44-fc-v470-x86_64-with-glibc2.39, python 3.13.18

## Aggregate over seeds

Mean of the per-seed episode means, with a 95% percentile bootstrap
interval over seeds. `best` is the lowest latency reachable by moving
every lease for free each window at the starting shard boundaries. It
is not an achievable policy, and it is not a global optimum either: a
policy that splits a shard can sit below it.

| Policy | Mean latency (ms) | 95% CI | p95 (ms) | GB moved | Cross-region txns |
|---|---|---|---|---|---|
| Static hash | 196.15 | [189.05, 204.18] | 236.04 | 0.0 | 37.2% |
| Random | 203.04 | [197.37, 209.14] | 256.72 | 162.7 | 35.8% |
| Follow traffic | 160.38 | [151.27, 170.27] | 223.86 | 873.7 | 28.0% |
| Best per window (fixed shards) | 102.85 | [95.29, 109.86] | 144.90 | 0.0 | 24.4% |
| Lion-style co-location | 177.80 | [171.00, 184.91] | 252.67 | 23.8 | 4.5% |

Follow traffic improves on static hash by **18.2%** of mean latency.
Headroom between follow traffic and the fixed-shard bound: **57.53 ms** (35.9% of follow traffic). A small number here means the reactive heuristic is already close to the best that lease movement alone can do, and that what is left for a learned policy is movement cost rather than latency.

## What each policy did with its windows

Share of decision windows spent on each kind of action, and the share
of chosen actions that were inapplicable in the state they met. An
inapplicable action costs a small penalty and changes nothing.

| Policy | Move lease | Move replica | Split | Nothing | Inapplicable |
|---|---|---|---|---|---|
| Static hash | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |
| Random | 43.5% | 47.2% | 8.9% | 0.4% | 77.1% |
| Follow traffic | 55.9% | 43.7% | 0.0% | 0.4% | 0.0% |
| Best per window (fixed shards) | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |
| Lion-style co-location | 9.3% | 1.2% | 0.0% | 89.5% | 0.0% |

## Reproducing this run

```
git checkout 18b0c0fdb5
python scripts/run_experiment.py --config results/runs/20261116T032622Z-f4870a4f-sweep-v4/config.json \
    --seeds 8 --seed-start 0
```
