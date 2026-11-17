# Run `20261117T054022Z-1a106c2b-presplit12-heldout-v4`

- **When** 2026-11-17T05:40:22.571369+00:00
- **Commit** `e1b0a53fec` on `main` (working tree dirty: yes)
- **Config digest** `1a106c2b`
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
| Static hash | 212.75 | [206.36, 218.27] | 264.31 | 0.0 | 67.7% |
| Follow traffic | 177.49 | [173.24, 181.54] | 241.71 | 448.8 | 48.9% |
| Lion-style co-location | 183.63 | [176.16, 190.70] | 249.05 | 40.5 | 10.7% |
| follow2 | 185.39 | [180.97, 190.40] | 249.14 | 318.1 | 52.1% |
| follow4 | 199.59 | [194.04, 205.30] | 260.02 | 173.5 | 57.3% |
| follow8 | 206.78 | [201.15, 213.25] | 270.44 | 85.3 | 59.7% |

Follow traffic improves on static hash by **16.6%** of mean latency.

## What each policy did with its windows

Share of decision windows spent on each kind of action, and the share
of chosen actions that were inapplicable in the state they met. An
inapplicable action costs a small penalty and changes nothing.

| Policy | Move lease | Move replica | Split | Nothing | Inapplicable |
|---|---|---|---|---|---|
| Static hash | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |
| Follow traffic | 55.2% | 44.8% | 0.0% | 0.0% | 0.0% |
| Lion-style co-location | 23.5% | 4.1% | 0.0% | 72.4% | 0.0% |
| follow2 | 44.2% | 31.8% | 0.0% | 24.1% | 0.0% |
| follow4 | 24.9% | 17.3% | 0.0% | 57.8% | 0.0% |
| follow8 | 12.5% | 8.5% | 0.0% | 79.0% | 0.0% |

## Reproducing this run

```
git checkout e1b0a53fec
python scripts/run_experiment.py --config results/runs/20261117T054022Z-1a106c2b-presplit12-heldout-v4/config.json \
    --seeds 8 --seed-start 2000
```
