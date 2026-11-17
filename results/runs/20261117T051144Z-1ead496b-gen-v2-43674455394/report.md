# Run `20261117T051144Z-1ead496b-gen-v2-43674455394`

- **When** 2026-11-17T05:11:44.660006+00:00
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
| Learned policy | 166.47 | [162.23, 170.81] | 240.40 | 252.6 | 31.2% |

## What each policy did with its windows

Share of decision windows spent on each kind of action, and the share
of chosen actions that were inapplicable in the state they met. An
inapplicable action costs a small penalty and changes nothing.

| Policy | Move lease | Move replica | Split | Nothing | Inapplicable |
|---|---|---|---|---|---|
| Learned policy | 64.7% | 30.6% | 4.8% | 0.0% | 0.0% |

## Reproducing this run

```
git checkout 153f6b8059
python scripts/run_experiment.py --config results/runs/20261117T051144Z-1ead496b-gen-v2-43674455394/config.json \
    --seeds 8 --seed-start 2000 \
    --model C:\Users\tinok\OneDrive\Desktop\COSC 6315\Initial Project Details\Project\results\archive\43674455394\model-20261115T035554Z\best_model.zip
```
