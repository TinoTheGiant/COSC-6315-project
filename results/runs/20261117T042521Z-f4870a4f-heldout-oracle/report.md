# Run `20261117T042521Z-f4870a4f-heldout-oracle`

- **When** 2026-11-17T04:25:21.473414+00:00
- **Commit** `713f46c405` on `main` (working tree dirty: yes)
- **Config digest** `f4870a4f`
- **Seeds** [2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007]
- **Windows per episode** 200, volatility 4.0
- **Machine** Linux-6.18.44-fc-v553-x86_64-with-glibc2.39, python 3.13.18

## Aggregate over seeds

Mean of the per-seed episode means, with a 95% percentile bootstrap
interval over seeds. `best` is the exact per-window minimum latency at
the starting shard boundaries, with movement free. It is not an
achievable policy; only a policy that splits a shard can sit below it.

| Policy | Mean latency (ms) | 95% CI | p95 (ms) | GB moved | Cross-region txns |
|---|---|---|---|---|---|
| Follow traffic | 148.81 | [143.82, 153.69] | 220.17 | 867.7 | 21.5% |
| Per-window oracle (fixed shards) | 76.47 | [72.99, 80.28] | 113.43 | 0.0 | 7.6% |
Headroom between follow traffic and the fixed-shard bound: **72.34 ms** (48.6% of follow traffic). A small number here means the reactive heuristic is already close to the best that lease movement alone can do, and that what is left for a learned policy is movement cost rather than latency.

## What each policy did with its windows

Share of decision windows spent on each kind of action, and the share
of chosen actions that were inapplicable in the state they met. An
inapplicable action costs a small penalty and changes nothing.

| Policy | Move lease | Move replica | Split | Nothing | Inapplicable |
|---|---|---|---|---|---|
| Follow traffic | 56.0% | 43.4% | 0.0% | 0.6% | 0.0% |
| Per-window oracle (fixed shards) | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |

## Reproducing this run

```
git checkout 713f46c405
python scripts/run_experiment.py --config results/runs/20261117T042521Z-f4870a4f-heldout-oracle/config.json \
    --seeds 8 --seed-start 2000
```
