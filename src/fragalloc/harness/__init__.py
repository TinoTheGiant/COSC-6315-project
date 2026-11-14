"""The real-cluster half of the pipeline: CockroachDB in place of the simulator.

See docs/harness-architecture.md and ADR-0009. The organising rule is that the
cluster environment must be interchangeable with ``fragalloc.env`` from the
agent's point of view: same observation, same action space, same reward units.

Dependency rule: this package may import ``fragalloc.actions``,
``fragalloc.catalog``, ``fragalloc.config``, ``fragalloc.observation``,
``fragalloc.workload`` and ``fragalloc.topology``. It must never import
``fragalloc.cost`` or ``fragalloc.simulator``: the cluster replaces the cost
model, and importing it invites reporting a modelled number as a measured one.
``tests/test_harness_placement.py`` enforces this.
"""
