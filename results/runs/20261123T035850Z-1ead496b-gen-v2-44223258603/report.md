# Run `20261123T035850Z-1ead496b-gen-v2-44223258603`

- **When** 2026-11-23T03:58:50.966207+00:00
- **Commit** `cff6e28ea2` on `main` (working tree dirty: yes)
- **Config digest** `1ead496b`
- **Seeds** [2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007]
- **Windows per episode** 200, volatility 2.0
- **Machine** Linux-6.18.44-fc-v726-x86_64-with-glibc2.39, python 3.13.18

## Aggregate over seeds

Mean of the per-seed episode means, with a 95% percentile bootstrap
interval over seeds. `best` is the exact per-window minimum latency at
the starting shard boundaries, with movement free. It is not an
achievable policy; only a policy that splits a shard can sit below it.

| Policy | Mean latency (ms) | 95% CI | p95 (ms) | GB moved | Cross-region txns |
|---|---|---|---|---|---|
| Learned policy | 168.52 | [163.16, 173.27] | 244.04 | 200.5 | 21.8% |

## What each policy did with its windows

Share of decision windows spent on each kind of action, and the share
of chosen actions that were inapplicable in the state they met. An
inapplicable action costs a small penalty and changes nothing.

| Policy | Move lease | Move replica | Split | Nothing | Inapplicable |
|---|---|---|---|---|---|
| Learned policy | 85.5% | 12.6% | 1.9% | 0.0% | 0.0% |

## Reproducing this run

```
git checkout cff6e28ea2
python scripts/run_experiment.py --config results/runs/20261123T035850Z-1ead496b-gen-v2-44223258603/config.json \
    --seeds 8 --seed-start 2000 \
    --model /home/claude/cosc-6315-project/results/archive/44223258603/model-20261118T022727Z/best_model.zip
```
