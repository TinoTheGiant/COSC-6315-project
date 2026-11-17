# Run `20261117T042521Z-1ead496b-sweep-v2`

- **When** 2026-11-17T04:25:21.452952+00:00
- **Commit** `713f46c405` on `main` (working tree dirty: yes)
- **Config digest** `1ead496b`
- **Seeds** [0, 1, 2, 3, 4, 5, 6, 7]
- **Windows per episode** 200, volatility 2.0
- **Machine** Linux-6.18.44-fc-v553-x86_64-with-glibc2.39, python 3.13.18

## Aggregate over seeds

Mean of the per-seed episode means, with a 95% percentile bootstrap
interval over seeds. `best` is the exact per-window minimum latency at
the starting shard boundaries, with movement free. It is not an
achievable policy; only a policy that splits a shard can sit below it.

| Policy | Mean latency (ms) | 95% CI | p95 (ms) | GB moved | Cross-region txns |
|---|---|---|---|---|---|
| Static hash | 195.47 | [188.38, 203.84] | 234.54 | 0.0 | 36.8% |
| Random | 201.58 | [195.93, 207.57] | 247.17 | 162.7 | 35.7% |
| Follow traffic | 137.36 | [127.00, 146.73] | 180.90 | 900.2 | 29.4% |
| Per-window oracle (fixed shards) | 93.43 | [87.59, 98.82] | 122.67 | 0.0 | 9.9% |
| Lion-style co-location | 173.33 | [164.31, 182.53] | 227.74 | 18.8 | 4.1% |

Follow traffic improves on static hash by **29.7%** of mean latency.
Headroom between follow traffic and the fixed-shard bound: **43.93 ms** (32.0% of follow traffic). A small number here means the reactive heuristic is already close to the best that lease movement alone can do, and that what is left for a learned policy is movement cost rather than latency.

## What each policy did with its windows

Share of decision windows spent on each kind of action, and the share
of chosen actions that were inapplicable in the state they met. An
inapplicable action costs a small penalty and changes nothing.

| Policy | Move lease | Move replica | Split | Nothing | Inapplicable |
|---|---|---|---|---|---|
| Static hash | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |
| Random | 43.5% | 47.2% | 8.9% | 0.4% | 77.1% |
| Follow traffic | 53.9% | 45.0% | 0.0% | 1.1% | 0.0% |
| Per-window oracle (fixed shards) | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |
| Lion-style co-location | 7.5% | 0.9% | 0.0% | 91.6% | 0.0% |

## Reproducing this run

```
git checkout 713f46c405
python scripts/run_experiment.py --config results/runs/20261117T042521Z-1ead496b-sweep-v2/config.json \
    --seeds 8 --seed-start 0
```
