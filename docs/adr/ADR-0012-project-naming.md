# ADR-0012: the project has one name, and the package is named after what it does

**Status:** accepted, 21 October 2026.

## Context

The project carried two names. The formal one, used in the proposal and on the
submission, is **Reinforcement Learning for Dynamic Data Fragmentation and
Allocation**. An invented second name sat in the Python package, the Gymnasium
environment identifier, two class names, the paper title and throughout the
documentation. It is recorded in the commit history and is deliberately not
repeated here.

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
the project would only have reintroduced a second name through the back door.
Naming it after the subject matter means an import line reads as a description
rather than as a brand.

Renamed with the package: the configuration class is now `FragAllocConfig`, the
Gymnasium environment class is `FragAllocEnv`, and the registered environment
identifier is `FragAlloc-v0`.

## Consequences

Any model checkpoint trained before this change still loads. Stable-Baselines3
stores the observation and action spaces rather than the environment class, and
neither changed. The environment identifier did change, so a script that
constructed the environment through `gym.make` by the old identifier would need
updating, and none in this repository did.

Results already recorded remain valid and are not reprocessed. A run directory
names its configuration by digest rather than by class name, so the digests are
unchanged, which a full run after the rename confirmed.

This record exists so that the change is explicable to anyone reading the
commit history, rather than appearing as an unexplained mass edit.
