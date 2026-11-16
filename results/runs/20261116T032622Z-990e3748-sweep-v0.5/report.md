# Run `20261116T032622Z-990e3748-sweep-v0.5`

- **When** 2026-11-16T03:26:22.122024+00:00
- **Commit** `18b0c0fdb5` on `main` (working tree dirty: yes)
- **Config digest** `990e3748`
- **Seeds** [0, 1, 2, 3, 4, 5, 6, 7]
- **Windows per episode** 200, volatility 0.5
- **Machine** Linux-6.18.44-fc-v470-x86_64-with-glibc2.39, python 3.13.18

## Aggregate over seeds

Mean of the per-seed episode means, with a 95% percentile bootstrap
interval over seeds. `best` is the lowest latency reachable by moving
every lease for free each window at the starting shard boundaries. It
is not an achievable policy, and it is not a global optimum either: a
policy that splits a shard can sit below it.

| Policy | Mean latency (ms) | 95% CI | p95 (ms) | GB moved | Cross-region txns |
|---|---|---|---|---|---|
| Static hash | 196.80 | [190.44, 204.44] | 231.18 | 0.0 | 36.6% |
| Random | 196.37 | [190.74, 202.01] | 236.36 | 162.7 | 35.4% |
| Follow traffic | 116.97 | [108.55, 124.39] | 147.31 | 322.5 | 31.1% |
| Best per window (fixed shards) | 118.70 | [110.10, 125.88] | 146.21 | 0.0 | 30.9% |
| Lion-style co-location | 183.04 | [172.47, 193.64] | 228.16 | 15.0 | 3.6% |

Follow traffic improves on static hash by **40.6%** of mean latency.
Headroom between follow traffic and the fixed-shard bound: **-1.73 ms** (-1.5% of follow traffic). A small number here means the reactive heuristic is already close to the best that lease movement alone can do, and that what is left for a learned policy is movement cost rather than latency.

## What each policy did with its windows

Share of decision windows spent on each kind of action, and the share
of chosen actions that were inapplicable in the state they met. An
inapplicable action costs a small penalty and changes nothing.

| Policy | Move lease | Move replica | Split | Nothing | Inapplicable |
|---|---|---|---|---|---|
| Static hash | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |
| Random | 43.5% | 47.2% | 8.9% | 0.4% | 77.1% |
| Follow traffic | 23.8% | 16.1% | 0.0% | 60.1% | 0.0% |
| Best per window (fixed shards) | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |
| Lion-style co-location | 3.8% | 0.8% | 0.0% | 95.4% | 0.0% |

## Reproducing this run

```
git checkout 18b0c0fdb5
python scripts/run_experiment.py --config results/runs/20261116T032622Z-990e3748-sweep-v0.5/config.json \
    --seeds 8 --seed-start 0
```
