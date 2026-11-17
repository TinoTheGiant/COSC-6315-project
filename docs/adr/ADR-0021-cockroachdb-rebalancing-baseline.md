# ADR-0021: CockroachDB's own rebalancing as a cluster baseline

**Status:** Accepted, 17 November 2026
**Date:** 2026-11-17
**Deciders:** Tino Kaseke

## Context

Every cluster result so far freezes CockroachDB's allocator (ADR-0015), so the
placement under test is the one the policy chose. That is right for comparing
policies, but it leaves the question a reviewer is most likely to ask
unanswered: what does the database do on its own? CockroachDB rebalances
leases and replicas by load, and its follow-the-workload behavior moves
leaseholders towards the regions issuing requests, which is the idea behind
the paper's `follow` heuristic.

## Decision

Add a `crdb` policy to `scripts/cluster_episode.py`. It never acts. After the
episode's table is placed and first measured with the allocator frozen,
exactly as for every other policy, it switches the allocator back on with
`release_rebalancer` (`fragalloc.harness.cluster`), each setting read back:

| setting | value |
|---|---|
| `kv.allocator.load_based_rebalancing` | `leases and replicas` |
| `kv.replicate_queue.enabled` | `true` |
| `kv.lease_queue.enabled` | `true` |
| `kv.split_queue.enabled` | `false` |
| `kv.range_merge.queue.enabled` | `false` |

Splits and merges stay off so the ranges keep the catalogue's boundaries and
every policy is compared on the same shards. The allocator is frozen again in
`finally`, so a following episode in the same job is unaffected.

Accounting:

- **Placement:** the executor already adopts the read-back placement whenever
  it differs from the intent ("on any divergence the cluster wins"), so the
  catalogue, the load accounting and the observation track the database's
  moves. Under `crdb` a divergence is the database working, so it is reported
  and does not fail the episode.
- **Data moved:** `bytes_added(before, after)` (`fragalloc.harness.env`) counts
  replicas present after a step and not before, times the shard's size. For
  `crdb` that is the episode's data moved. It is also recorded for every other
  policy as `gb_observed`, a cross-check on the executor's account.
- **Tail:** every episode summary now carries `mean_p95_ms`.

## Options Considered

| Option | For | Against |
|---|---|---|
| A. `crdb` policy, allocator on, splits off (chosen) | Answers "what does the database do"; same shards and harness as every policy | The database's own load-based splitting is excluded |
| B. Allocator fully on, splits included | Closer to a default deployment | Ranges stop matching the catalogue; the executor and the observation lose their mapping |
| C. No such baseline | No work | The most predictable reviewer question goes unanswered |

## Consequences

- One more cluster episode per seed (about 50 minutes). Run as
  `policies: agent crdb` with a second learner seed's model, so the same four
  runs also give the cluster result a second trained agent.
- The database's allocator works on a time scale of minutes; a 200-window
  episode lasts about 45 minutes. If it barely moves anything in that time,
  that is the finding, and the paper says so rather than tuning it to look
  active.
- `tests/test_harness_cluster.py` checks the settings round trip and that
  `bytes_added` counts a replica move and not a lease move.
