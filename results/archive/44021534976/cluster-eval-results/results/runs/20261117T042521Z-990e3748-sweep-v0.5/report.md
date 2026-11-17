# Run `20261117T042521Z-990e3748-sweep-v0.5`

- **When** 2026-11-17T04:25:21.450133+00:00
- **Commit** `713f46c405` on `main` (working tree dirty: yes)
- **Config digest** `990e3748`
- **Seeds** [0, 1, 2, 3, 4, 5, 6, 7]
- **Windows per episode** 200, volatility 0.5
- **Machine** Linux-6.18.44-fc-v553-x86_64-with-glibc2.39, python 3.13.18

## Aggregate over seeds

Mean of the per-seed episode means, with a 95% percentile bootstrap
interval over seeds. `best` is the exact per-window minimum latency at
the starting shard boundaries, with movement free. It is not an
achievable policy; only a policy that splits a shard can sit below it.

| Policy | Mean latency (ms) | 95% CI | p95 (ms) | GB moved | Cross-region txns |
|---|---|---|---|---|---|
| Static hash | 196.80 | [190.44, 204.44] | 231.18 | 0.0 | 36.6% |
| Random | 196.37 | [190.74, 202.01] | 236.36 | 162.7 | 35.4% |
| Follow traffic | 116.97 | [108.55, 124.39] | 147.31 | 322.5 | 31.1% |
| Per-window oracle (fixed shards) | 100.10 | [93.36, 106.35] | 122.32 | 0.0 | 10.9% |
| Lion-style co-location | 183.04 | [172.47, 193.64] | 228.16 | 15.0 | 3.6% |

Follow traffic improves on static hash by **40.6%** of mean latency.
Headroom between follow traffic and the fixed-shard bound: **16.87 ms** (14.4% of follow traffic). A small number here means the reactive heuristic is already close to the best that lease movement alone can do, and that what is left for a learned policy is movement cost rather than latency.

## What each policy did with its windows

Share of decision windows spent on each kind of action, and the share
of chosen actions that were inapplicable in the state they met. An
inapplicable action costs a small penalty and changes nothing.

| Policy | Move lease | Move replica | Split | Nothing | Inapplicable |
|---|---|---|---|---|---|
| Static hash | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |
| Random | 43.5% | 47.2% | 8.9% | 0.4% | 77.1% |
| Follow traffic | 23.8% | 16.1% | 0.0% | 60.1% | 0.0% |
| Per-window oracle (fixed shards) | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |
| Lion-style co-location | 3.8% | 0.8% | 0.0% | 95.4% | 0.0% |

## Reproducing this run

```
git checkout 713f46c405
python scripts/run_experiment.py --config results/runs/20261117T042521Z-990e3748-sweep-v0.5/config.json \
    --seeds 8 --seed-start 0
```
