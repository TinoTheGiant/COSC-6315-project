# Configurations

Each file is a complete `FragAllocConfig`, so a run is reproducible from the
file plus its seed.

| File | What it is for |
|------|----------------|
| `default.json` | The six-region baseline configuration every other file varies from |
| `high-volatility.json` | `volatility = 4.0`: the upper end of the Objective 5 sweep |
| `migration-averse.json` | `w_migration = 1.0`: the stability end of the responsiveness frontier |
| `reduced-tabular.json` | Three regions, six-fragment cap, 64 cells: small enough for the week 3 tabular Q-learning sanity check |

```python
from fragalloc.config import FragAllocConfig
cfg = FragAllocConfig.load("configs/high-volatility.json")
```

A sweep is a loop over `evolve`, not a folder of near-identical files. These
exist as named reference points, not as the sweep mechanism.
