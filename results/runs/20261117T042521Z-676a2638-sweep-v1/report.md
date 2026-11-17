# Run `20261117T042521Z-676a2638-sweep-v1`

- **When** 2026-11-17T04:25:21.470504+00:00
- **Commit** `713f46c405` on `main` (working tree dirty: yes)
- **Config digest** `676a2638`
- **Seeds** [0, 1, 2, 3, 4, 5, 6, 7]
- **Windows per episode** 200, volatility 1.0
- **Machine** Linux-6.18.44-fc-v553-x86_64-with-glibc2.39, python 3.13.18

## Aggregate over seeds

Mean of the per-seed episode means, with a 95% percentile bootstrap
interval over seeds. `best` is the exact per-window minimum latency at
the starting shard boundaries, with movement free. It is not an
achievable policy; only a policy that splits a shard can sit below it.

| Policy | Mean latency (ms) | 95% CI | p95 (ms) | GB moved | Cross-region txns |
|---|---|---|---|---|---|
| Static hash | 196.28 | [189.84, 204.16] | 231.93 | 0.0 | 36.7% |
| Random | 201.65 | [196.05, 206.74] | 248.80 | 162.7 | 35.4% |
| Follow traffic | 119.75 | [110.20, 127.87] | 152.56 | 632.6 | 30.7% |
| Per-window oracle (fixed shards) | 99.34 | [92.64, 105.43] | 123.40 | 0.0 | 11.2% |
| Lion-style co-location | 181.69 | [170.24, 193.13] | 227.17 | 16.2 | 3.7% |

Follow traffic improves on static hash by **39.0%** of mean latency.
Headroom between follow traffic and the fixed-shard bound: **20.41 ms** (17.0% of follow traffic). A small number here means the reactive heuristic is already close to the best that lease movement alone can do, and that what is left for a learned policy is movement cost rather than latency.

## What each policy did with its windows

Share of decision windows spent on each kind of action, and the share
of chosen actions that were inapplicable in the state they met. An
inapplicable action costs a small penalty and changes nothing.

| Policy | Move lease | Move replica | Split | Nothing | Inapplicable |
|---|---|---|---|---|---|
| Static hash | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |
| Random | 43.5% | 47.2% | 8.9% | 0.4% | 77.1% |
| Follow traffic | 43.7% | 31.6% | 0.0% | 24.7% | 0.0% |
| Per-window oracle (fixed shards) | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |
| Lion-style co-location | 4.6% | 0.8% | 0.0% | 94.6% | 0.0% |

## Reproducing this run

```
git checkout 713f46c405
python scripts/run_experiment.py --config results/runs/20261117T042521Z-676a2638-sweep-v1/config.json \
    --seeds 8 --seed-start 0
```
