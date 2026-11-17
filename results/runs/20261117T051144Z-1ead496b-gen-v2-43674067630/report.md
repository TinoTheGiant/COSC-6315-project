# Run `20261117T051144Z-1ead496b-gen-v2-43674067630`

- **When** 2026-11-17T05:11:44.660174+00:00
- **Commit** `153f6b8059` on `main` (working tree dirty: yes)
- **Config digest** `1ead496b`
- **Seeds** [2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007]
- **Windows per episode** 200, volatility 2.0
- **Machine** Windows-11-10.0.26300-SP0, python 3.14.7

## Aggregate over seeds

Mean of the per-seed episode means, with a 95% percentile bootstrap
interval over seeds. `best` is the exact per-window minimum latency at
the starting shard boundaries, with movement free. It is not an
achievable policy; only a policy that splits a shard can sit below it.

| Policy | Mean latency (ms) | 95% CI | p95 (ms) | GB moved | Cross-region txns |
|---|---|---|---|---|---|
| Learned policy | 170.50 | [166.38, 174.73] | 247.65 | 127.0 | 33.7% |
| Static hash | 192.83 | [189.31, 196.48] | 241.36 | 0.0 | 34.1% |
| Follow traffic | 126.93 | [120.63, 135.54] | 170.73 | 877.4 | 22.3% |
| Per-window oracle (fixed shards) | 88.56 | [84.15, 94.29] | 115.68 | 0.0 | 9.4% |
| Lion-style co-location | 177.24 | [168.02, 185.54] | 239.54 | 25.0 | 4.5% |

Follow traffic improves on static hash by **34.2%** of mean latency.
Headroom between follow traffic and the fixed-shard bound: **38.38 ms** (30.2% of follow traffic). A small number here means the reactive heuristic is already close to the best that lease movement alone can do, and that what is left for a learned policy is movement cost rather than latency.

## What each policy did with its windows

Share of decision windows spent on each kind of action, and the share
of chosen actions that were inapplicable in the state they met. An
inapplicable action costs a small penalty and changes nothing.

| Policy | Move lease | Move replica | Split | Nothing | Inapplicable |
|---|---|---|---|---|---|
| Learned policy | 65.6% | 27.4% | 6.8% | 0.3% | 0.0% |
| Static hash | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |
| Follow traffic | 54.1% | 43.9% | 0.0% | 2.1% | 0.0% |
| Per-window oracle (fixed shards) | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |
| Lion-style co-location | 8.8% | 1.2% | 0.0% | 90.0% | 0.0% |

## Reproducing this run

```
git checkout 153f6b8059
python scripts/run_experiment.py --config results/runs/20261117T051144Z-1ead496b-gen-v2-43674067630/config.json \
    --seeds 8 --seed-start 2000 \
    --model C:\Users\tinok\OneDrive\Desktop\COSC 6315\Initial Project Details\Project\results\archive\43674067630\model-20261115T035018Z\best_model.zip
```
