# Run `20261118T034339Z-f4870a4f-agent-20261118T022638Z`

- **When** 2026-11-18T03:43:39.267553+00:00
- **Commit** `4e0b64313a` on `main` (working tree dirty: no)
- **Config digest** `f4870a4f`
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
| Learned policy | 164.36 | [159.41, 168.99] | 254.64 | 186.9 | 27.5% |
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
| Learned policy | 58.4% | 34.9% | 6.7% | 0.0% | 0.0% |
| Static hash | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |
| Random | 46.2% | 46.2% | 7.1% | 0.4% | 81.4% |
| Follow traffic | 56.0% | 43.4% | 0.0% | 0.6% | 0.0% |
| Per-window oracle (fixed shards) | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |
| Lion-style co-location | 10.1% | 1.4% | 0.0% | 88.5% | 0.0% |

## Reproducing this run

```
git checkout 4e0b64313a
python scripts/run_experiment.py --config results/runs/20261118T034339Z-f4870a4f-agent-20261118T022638Z/config.json \
    --seeds 8 --seed-start 2000 \
    --model /home/runner/work/COSC-6315-project/COSC-6315-project/results/models/20261118T022638Z/best_model.zip
```
