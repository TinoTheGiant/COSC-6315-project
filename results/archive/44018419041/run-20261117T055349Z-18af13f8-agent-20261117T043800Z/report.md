# Run `20261117T055349Z-18af13f8-agent-20261117T043800Z`

- **When** 2026-11-17T05:53:49.215159+00:00
- **Commit** `9d5de71160` on `main` (working tree dirty: no)
- **Config digest** `18af13f8`
- **Seeds** [2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007]
- **Windows per episode** 200, volatility 4.0
- **Machine** Linux-7.0.0-1014-aws-x86_64-with-glibc2.39, python 3.11.18

## Aggregate over seeds

Mean of the per-seed episode means, with a 95% percentile bootstrap
interval over seeds. `best` is the exact per-window minimum latency at
the starting shard boundaries, with movement free. It is not an
achievable policy; only a policy that splits a shard can sit below it.

| Policy | Mean latency (ms) | 95% CI | p95 (ms) | GB moved | Cross-region txns |
|---|---|---|---|---|---|
| Learned policy | 169.46 | [163.77, 174.71] | 251.04 | 181.3 | 31.3% |
| Static hash | 192.11 | [187.95, 196.33] | 249.80 | 0.0 | 33.9% |
| Random | 195.46 | [190.28, 200.94] | 263.79 | 134.6 | 35.8% |
| Follow traffic | 148.81 | [143.82, 153.69] | 220.17 | 867.7 | 21.5% |
| Per-window oracle (fixed shards) | 76.47 | [72.99, 80.28] | 113.43 | 0.0 | 7.6% |
| Lion-style co-location | 179.98 | [166.22, 195.61] | 258.85 | 28.8 | 4.1% |

Follow traffic improves on static hash by **22.5%** of mean latency.
Headroom between follow traffic and the fixed-shard bound: **72.34 ms** (48.6% of follow traffic). A small number here means the reactive heuristic is already close to the best that lease movement alone can do, and that what is left for a learned policy is movement cost rather than latency.

## What each policy did with its windows

Share of decision windows spent on each kind of action, and the share
of chosen actions that were inapplicable in the state they met. An
inapplicable action costs a small penalty and changes nothing.

| Policy | Move lease | Move replica | Split | Nothing | Inapplicable |
|---|---|---|---|---|---|
| Learned policy | 42.5% | 50.4% | 6.9% | 0.2% | 0.0% |
| Static hash | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |
| Random | 46.2% | 46.2% | 7.1% | 0.4% | 81.4% |
| Follow traffic | 56.0% | 43.4% | 0.0% | 0.6% | 0.0% |
| Per-window oracle (fixed shards) | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |
| Lion-style co-location | 10.1% | 1.4% | 0.0% | 88.5% | 0.0% |

## Reproducing this run

```
git checkout 9d5de71160
python scripts/run_experiment.py --config results/runs/20261117T055349Z-18af13f8-agent-20261117T043800Z/config.json \
    --seeds 8 --seed-start 2000 \
    --model /home/runner/work/COSC-6315-project/COSC-6315-project/results/models/20261117T043800Z/best_model.zip
```
