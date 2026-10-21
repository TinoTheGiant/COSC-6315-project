# ADR-0012: the project has one name, and the package is named after what it does

**Status:** accepted, 21 October 2026.

## Context

The project carried two names. The formal one, used in the proposal and on the
submission, is **Reinforcement Learning for Dynamic Data Fragmentation and
Allocation**. A second, invented name appeared in the Python package, the
Gymnasium environment identifier, two class names, the paper title and
throughout the documentation.

Two names for one thing is a cost with no benefit. A reader meeting the second
one has to work out that it refers to the first, and a marker comparing the
paper against the proposal sees a title that does not match. An invented name
also reads as branding, which is the wrong register for a course paper and for
an IEEE submission.

## Decision

**The project has one name**, the formal one, and it is used in the paper
title, the README, every document and every figure caption.

**The Python package is named after what it does**, not after the project:
`fragalloc`, for fragmentation and allocation. A package name has to be short,
lowercase and importable, so it cannot be the full title, and naming it after
the project would only have reintroduced the second name through the back door.
Naming it after the subject matter means an import line reads as a description
rather than as a brand.

Renamed with it:

| Was | Is |
|---|---|
| `shardmind` (package) | `fragalloc` |
| `ShardMindConfig` | `FragAllocConfig` |
| `ShardMindEnv` | `FragAllocEnv` |
| `ShardMind-v0` (environment id) | `FragAlloc-v0` |

## Consequences

Any model checkpoint trained before this change still loads: Stable-Baselines3
stores the observation and action spaces rather than the environment class, and
neither changed. The environment identifier did change, so a script that
constructed the environment through `gym.make` by its old id must be updated,
and none in this repository did.

The results already recorded remain valid and are not reprocessed. A run
directory names its configuration by digest rather than by class name, so the
digests are unchanged.

This record exists so that the earlier name is explicable rather than merely
absent, which matters for anyone reading the commit history.
