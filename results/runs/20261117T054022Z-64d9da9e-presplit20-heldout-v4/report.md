# Run `20261117T054022Z-64d9da9e-presplit20-heldout-v4`

- **When** 2026-11-17T05:40:22.556692+00:00
- **Commit** `e1b0a53fec` on `main` (working tree dirty: yes)
- **Config digest** `64d9da9e`
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
| Static hash | 229.13 | [223.45, 234.89] | 272.78 | 0.0 | 88.6% |
| Follow traffic | 197.39 | [192.22, 201.91] | 259.74 | 257.6 | 73.7% |
| Lion-style co-location | 184.67 | [176.13, 194.13] | 243.32 | 38.2 | 16.0% |
| follow2 | 202.77 | [198.47, 207.00] | 263.03 | 198.3 | 75.6% |
| follow4 | 214.64 | [209.57, 218.86] | 274.07 | 116.2 | 79.5% |
| follow8 | 225.08 | [221.12, 229.80] | 275.22 | 49.6 | 81.9% |

Follow traffic improves on static hash by **13.8%** of mean latency.

## What each policy did with its windows

Share of decision windows spent on each kind of action, and the share
of chosen actions that were inapplicable in the state they met. An
inapplicable action costs a small penalty and changes nothing.

| Policy | Move lease | Move replica | Split | Nothing | Inapplicable |
|---|---|---|---|---|---|
| Static hash | 0.0% | 0.0% | 0.0% | 100.0% | 0.0% |
| Follow traffic | 57.1% | 42.9% | 0.0% | 0.0% | 0.0% |
| Lion-style co-location | 31.6% | 6.4% | 0.0% | 62.1% | 0.0% |
| follow2 | 43.4% | 33.1% | 0.0% | 23.6% | 0.0% |
| follow4 | 25.0% | 19.4% | 0.0% | 55.6% | 0.0% |
| follow8 | 12.5% | 8.2% | 0.0% | 79.2% | 0.0% |

## Reproducing this run

```
git checkout e1b0a53fec
python scripts/run_experiment.py --config results/runs/20261117T054022Z-64d9da9e-presplit20-heldout-v4/config.json \
    --seeds 8 --seed-start 2000
```
