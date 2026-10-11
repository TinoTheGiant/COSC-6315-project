# Graph Report - shardmind  (2026-10-11)

## Corpus Check
- 70 files · ~60,818 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 2 file(s) not represented in the graph (top: (none) 1, .crdb 1)

## Summary
- 880 nodes · 2022 edges · 42 communities (35 shown, 7 thin omitted)
- Extraction: 83% EXTRACTED · 17% INFERRED · 0% AMBIGUOUS · INFERRED: 335 edges (avg confidence: 0.91)
- Token cost: 334,945 input · 0 output

## Community Hubs (Navigation)
- Configuration and Workload Core
- Cost Model and Latency
- Figure Design System
- Falsification Test and Parity
- MDP and Architecture Spec
- Live Dashboard
- Gymnasium Environment
- Catalog and Cost Tests
- Map Projection and Basemap
- Cluster Pilot and netem Results
- Action Space and Simulator
- Baseline Policies
- Fragment Catalog Internals
- Database Selection Screen
- Cluster Simulator Loop
- Real-Cluster Harness Design
- Analysis Dashboard
- Session Scoping and Checkpoints
- Action Encoding
- Catalog Mutators
- Workload Tests
- Episode Export and Atlas
- Sim-to-Real Transfer Parity
- Testing Strategy
- Core Design Decisions
- Paper Figures
- Topology Construction and Tests
- Region Geography and RTT
- Layering and Dependency ADRs
- CI Cluster Pilot Workflow
- Research Framing and Base Papers
- Early Database Validation Plan
- Three-Stage Pipeline
- Technical Debt Audit
- Cluster Sizing and Scope Cuts
- Determinism Tests
- Config and Sweep Mechanics
- Matplotlib Style Functions
- Cluster Lifecycle Script
- Container Entrypoint
- Catalog Test Fixture
- Package Metadata

## God Nodes (most connected - your core abstractions)
1. `FragmentCatalog` - 56 edges
2. `ShardMindConfig` - 51 edges
3. `ClusterSimulator` - 46 edges
4. `Dashboard` - 32 edges
5. `ActionSpace` - 32 edges
6. `evaluate()` - 32 edges
7. `Harness Architecture: the Real-Cluster Half of the Pipeline` - 29 edges
8. `Topology` - 22 edges
9. `WorkloadGenerator` - 22 edges
10. `ADR-0009: Reverse to CockroachDB for Sim-to-Real Parity` - 22 edges

## Surprising Connections (you probably didn't know these)
- `Latency injection assertion` --semantically_similar_to--> `Validation as placement-ranking agreement`  [INFERRED] [semantically similar]
  .github/workflows/cluster-pilot.yml → docs/adr/ADR-0001-simulate-rather-than-measure.md
- `test_the_default_configuration_stays_within_a_few_hundred_actions()` --uses--> `ActionSpace`  [INFERRED]
  tests/test_actions.py → src/shardmind/actions.py
- `test_spaces_have_the_declared_shape()` --uses--> `ActionSpace`  [INFERRED]
  tests/test_env.py → src/shardmind/actions.py
- `test_each_node_declares_its_region_as_locality()` --uses--> `ShardMindConfig`  [INFERRED]
  tests/test_cluster_parity.py → src/shardmind/config.py
- `test_one_node_per_region()` --uses--> `ShardMindConfig`  [INFERRED]
  tests/test_cluster_parity.py → src/shardmind/config.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Sim-to-real cost-model parity chain** — readme_sim_to_real_pretraining, readme_generated_cluster_geography, docker_docker_compose_generated_from_topology, _github_workflows_cluster_pilot_latency_injection_assertion, docs_adr_adr_0004_analytic_cost_model_decision [INFERRED 0.85]
- **Cheap pre-checks run before any agent work** — _github_workflows_cluster_pilot_falsification_gate, readme_falsification_gate, docs_adr_adr_0003_stable_baselines3_over_hand_rolled_dqn_tabular_q_check, docs_adr_adr_0001_simulate_rather_than_measure_ranking_validation, _github_workflows_cluster_pilot_latency_injection_assertion [INFERRED 0.75]
- **Constraints imposed by using off-the-shelf DQN** — docs_adr_adr_0002_flat_declarative_action_space_decision, docs_adr_adr_0002_flat_declarative_action_space_no_masking, docs_adr_adr_0003_stable_baselines3_over_hand_rolled_dqn_decision, docs_adr_adr_0003_stable_baselines3_over_hand_rolled_dqn_truncated_vs_terminated, docs_adr_adr_0005_simulator_independent_of_gymnasium_observation_layout [INFERRED 0.85]
- **The Database Decision Chain and Its Two Reversals** — docs_adr_adr_0008_database_selection_adr_0008, docs_adr_adr_0009_cockroachdb_for_sim_to_real_parity_adr_0009, docs_adr_adr_0010_session_scoped_cluster_and_resumable_runs_adr_0010, docs_adr_adr_0011_where_the_compute_runs_adr_0011, docs_tech_debt_adr_chain_reversals [EXTRACTED 1.00]
- **The Harness Modules That Together Realize One Step** — docs_harness_architecture_step_protocol, docs_harness_architecture_cluster_py, docs_harness_architecture_placement_py, docs_harness_architecture_executor_py, docs_harness_architecture_driver_py, docs_harness_architecture_harness_env_py, docs_harness_architecture_harness_checkpoint_py [EXTRACTED 1.00]
- **The Three Parities a Transferred Weight Depends On** — docs_adr_adr_0009_cockroachdb_for_sim_to_real_parity_sim_to_real_transfer, docs_adr_adr_0009_cockroachdb_for_sim_to_real_parity_observation_space_parity, docs_adr_adr_0009_cockroachdb_for_sim_to_real_parity_cost_model_parity, docs_adr_adr_0009_cockroachdb_for_sim_to_real_parity_destination_only_encoding, docs_adr_adr_0010_session_scoped_cluster_and_resumable_runs_migration_cost_as_dataset_fraction, docs_harness_architecture_space_parity_contract, docs_testing_strategy_space_parity_test [INFERRED 0.95]

## Communities (42 total, 7 thin omitted)

### Community 0 - "Configuration and Workload Core"
Cohesion: 0.06
Nodes (20): CatalogConfig, EpisodeConfig, ShardMindConfig, tup(), WorkloadConfig, _Block, ObservationEncoder, _txn_demand_by_fragment() (+12 more)

### Community 1 - "Cost Model and Latency"
Cohesion: 0.07
Nodes (31): CostConfig, coefficient_of_variation(), evaluate(), _ops_per_region(), read_latency(), read_serving_region(), replication_term(), transaction_latency() (+23 more)

### Community 2 - "Figure Design System"
Cohesion: 0.05
Nodes (24): Basemap Drawn Once as a PolyCollection, viz.BLUES Sequential Ramp, Figure and Dashboard Design System, Figure Geometry Tokens, Form Selection by Reader Task, use_house_style() versus use_paper_style(), viz.policy_kwargs(key), viz.policy_reference() (+16 more)

### Community 3 - "Falsification Test and Parity"
Cohesion: 0.07
Nodes (23): bootstrap_gap(), build_table(), connect(), main(), observed_lease_regions(), pct(), place(), range_ids() (+15 more)

### Community 4 - "MDP and Architecture Spec"
Cohesion: 0.10
Nodes (26): Observation Space Parity, ActionSpace, ShardMind Architecture, ClusterSimulator, cost.evaluate, FragmentCatalog, ObservationEncoder, ShardMindConfig (+18 more)

### Community 5 - "Live Dashboard"
Cohesion: 0.08
Nodes (3): build_config(), Dashboard, main()

### Community 6 - "Gymnasium Environment"
Cohesion: 0.09
Nodes (14): RewardConfig, register_env(), ShardMindEnv, actions(), env(), test_an_inapplicable_action_is_charged_a_small_fixed_cost(), test_migration_weight_penalizes_moving_data(), test_observations_stay_inside_the_declared_box() (+6 more)

### Community 7 - "Catalog and Cost Tests"
Cohesion: 0.11
Nodes (20): test_aggregate_cells_sums_each_fragments_rows(), test_aggregate_rejects_a_mismatched_array(), test_drop_replica_is_free(), test_drop_replica_refuses_at_min_replicas(), test_ensure_replica_costs_the_fragment_size(), test_ensure_replica_refuses_beyond_max_replicas(), test_even_boundaries_are_balanced(), test_fragments_partition_the_keyspace() (+12 more)

### Community 8 - "Map Projection and Basemap"
Cohesion: 0.08
Nodes (12): arc(), draw_basemap(), grayscale_ratio(), great_circle(), latlon_for(), load_basemap(), mercator_y(), policy_kwargs() (+4 more)

### Community 9 - "Cluster Pilot and netem Results"
Cohesion: 0.13
Nodes (18): netem Latency Injection under Citus, ADR-0011: Where the Compute Runs, and Why It Is Not a GPU, cluster-pilot.yml Workflow, GitHub Actions as the Primary Environment, GitHub Codespaces, Measured Simulator Throughput, The Latency Matrix Has No Citable Provenance, Cluster Pilot #1, 8 October 2026 (+10 more)

### Community 10 - "Action Space and Simulator"
Cohesion: 0.10
Nodes (11): Action, ActionKind, CostBreakdown, test_addressing_a_fragment_that_does_not_exist_is_a_quiet_no_op(), test_all_six_kinds_are_reachable(), test_describe_is_readable(), test_encoding_rejects_impossible_targets(), test_noop_is_the_last_index() (+3 more)

### Community 11 - "Baseline Policies"
Cohesion: 0.10
Nodes (6): main(), GreedyPrimaryPolicy, NoOpPolicy, Policy, rollout(), test_a_policy_that_follows_the_traffic_beats_one_that_does_not()

### Community 12 - "Fragment Catalog Internals"
Cohesion: 0.11
Nodes (6): _even_boundaries(), FragmentCatalog, test_dropping_a_replica_becomes_possible_once_one_is_added(), test_no_action_ever_raises_in_any_reachable_state(), test_the_inapplicable_residue_is_bounded_and_understood(), test_invariants_survive_a_long_random_mutation_sequence()

### Community 13 - "Database Selection Screen"
Cohesion: 0.15
Nodes (14): ADR-0008: Build on Citus, CockroachDB as Fallback, Apache HBase, Citus, citus_move_shard_placement, citus_split_shard_by_split_points, Eight Database Screening Criteria, MongoDB, ScyllaDB 6.2.x (+6 more)

### Community 14 - "Cluster Simulator Loop"
Cohesion: 0.12
Nodes (6): BestEachTurn, instantaneous_best(), main(), ClusterSimulator, StepResult, test_reset_restores_the_initial_catalogue()

### Community 15 - "Real-Cluster Harness Design"
Cohesion: 0.18
Nodes (14): Harness Build Order, harness/cluster.py, harness/driver.py, harness/executor.py, Harness Architecture: the Real-Cluster Half of the Pipeline, harness/checkpoint.py, harness/env.py, The Measurement Protocol and Choice of N (+6 more)

### Community 16 - "Analysis Dashboard"
Cohesion: 0.24
Nodes (13): episode_frame(), main(), panel_balance(), panel_cdf(), panel_distribution(), panel_means(), panel_origins(), panel_residence() (+5 more)

### Community 17 - "Session Scoping and Checkpoints"
Cohesion: 0.18
Nodes (10): CockroachDB, ADR-0010: Session-Scoped Cluster and Episode-Checkpointed Runs, CockroachDB Enterprise Free Licence, Episode-Boundary Checkpointing, Session-Scoped Ephemeral Cluster, Suspend Detection and Sample Discard, Harness Failure Modes and Responses, Roadmap (+2 more)

### Community 18 - "Action Encoding"
Cohesion: 0.12
Nodes (3): ActionSpace, RandomPolicy, space()

### Community 19 - "Catalog Mutators"
Cohesion: 0.18
Nodes (3): MutationResult, test_split_refuses_a_single_cell_fragment(), test_split_refuses_at_the_fragment_cap()

### Community 20 - "Workload Tests"
Cohesion: 0.21
Nodes (13): _make(), test_a_full_period_returns_the_field_to_its_starting_rotation(), test_adjacent_cells_have_more_similar_angles_than_distant_ones(), test_different_seeds_give_different_workloads(), test_read_write_split_follows_read_fraction(), test_request_counts_match_the_configured_volume(), test_requesting_a_window_beyond_the_horizon_is_an_error(), test_same_seed_reproduces_the_window_exactly() (+5 more)

### Community 21 - "Episode Export and Atlas"
Cohesion: 0.20
Nodes (5): instantaneous_best(), main(), run(), main(), main()

### Community 22 - "Sim-to-Real Transfer Parity"
Cohesion: 0.20
Nodes (12): ADR-0009: Reverse to CockroachDB for Sim-to-Real Parity, ALTER RANGE ... RELOCATE, Destination-Only MOVE_REPLICA Encoding, MOVE_LEASE(f, r), MOVE_REPLICA(f, from, to), Sim-to-Real Transfer, SPLIT(f), Defect: RELOCATE LEASE Needs an Existing Replica (+4 more)

### Community 23 - "Testing Strategy"
Cohesion: 0.16
Nodes (8): Tabular Q-Learning Sanity Check, Golden-String Action-to-SQL Tests, Checkpoint Round-Trip Test, Six Cluster Integration Tests, Suite Layers: Exact, Property, Fuzz, Determinism, Conformance, End-to-End, test_a_policy_that_follows_the_traffic_beats_one_that_does_not, Testing Strategy, Three-Tier Harness Testing

### Community 24 - "Core Design Decisions"
Cohesion: 0.18
Nodes (9): migration-averse.json (w_migration = 1.0), inapplicable_action_cost, w_imbalance reward term, Split is free in bytes, merge is not, MERGE cannot be forced on CockroachDB, Documentation index, DQN as autonomous database administrator, Latency reduction net of migration cost (+1 more)

### Community 25 - "Paper Figures"
Cohesion: 0.20
Nodes (4): chunk_homes(), cumulative_migration(), latency_over_time(), traffic_heatmap()

### Community 26 - "Topology Construction and Tests"
Cohesion: 0.18
Nodes (9): TopologyConfig, build_topology(), test_asymmetric_input_is_symmetrized(), test_cross_region_is_always_slower_than_intra_region(), test_explicit_table_of_matching_size_is_accepted(), test_matrix_is_symmetric_with_intra_region_diagonal(), test_missing_table_for_unusual_region_count_is_an_error(), test_nearest_picks_the_lowest_rtt_candidate() (+1 more)

### Community 27 - "Region Geography and RTT"
Cohesion: 0.18
Nodes (6): great_circle_km(), is_modelled(), modelled_rtt_ms(), region_meta(), rtt_matrix(), topology_for()

### Community 28 - "Layering and Dependency ADRs"
Cohesion: 0.21
Nodes (8): Pure-NumPy N-region simulator, truncated versus terminated bootstrapping contract, ClusterSimulator layer, CostBreakdown named record, Published ObservationEncoder.layout, ShardMindEnv Gymnasium adapter, shardmind/harness/ module, Reference policies (no-op, random, greedy primary)

### Community 29 - "CI Cluster Pilot Workflow"
Cohesion: 0.22
Nodes (5): Cluster pilot job, default.json six-region baseline, Six-node CockroachDB Compose cluster, Per-node region locality flags, NETEM_RULES per-peer latency injection

### Community 30 - "Research Framing and Base Papers"
Cohesion: 0.24
Nodes (6): The fidelity objection, GeoTP: Latency-Aware Geo-Distributed Transaction Processing in Database Middlewares (ICDE 2025), Lion: Minimizing Distributed Transactions Through Adaptive Replica Provision (ICDE 2024), The gap this project occupies, ShardMind: RL for dynamic data fragmentation and allocation, world-50m.json Natural Earth outlines

### Community 31 - "Early Database Validation Plan"
Cohesion: 0.25
Nodes (4): Falsification test gate (CI), reduced-tabular.json (three regions, 64 cells), Week 3 tabular Q-learning reward check, Three readings of "should have a real database"

### Community 32 - "Three-Stage Pipeline"
Cohesion: 0.25
Nodes (6): Measured applicable-action fraction (~54%), Desired-end-state action semantics, ALTER RANGE RELOCATE synchronous primitive, Stage 1: Python simulator, Stage 2: real CockroachDB cluster, Three-stage architecture

### Community 33 - "Technical Debt Audit"
Cohesion: 0.22
Nodes (8): Debt 7: Four-Deep ADR Chain with Two Reversals, Debt Scoring Formula, Debt 1: No Version Control and No Off-Machine Copy, Technical Debt Audit, Debt 4: Dependencies Unpinned, Debt 6: Baselines Have No Tests, Debt 8: 1,773 Lines of Untested Scripts, Baseline Characterization Tests

### Community 35 - "Determinism Tests"
Cohesion: 0.38
Nodes (5): test_a_different_seed_gives_a_different_episode(), test_the_configured_seed_is_used_when_reset_is_given_none(), test_the_same_seed_reproduces_the_episode_exactly(), test_two_simulators_stay_in_step_under_the_same_actions(), _trajectory()

## Ambiguous Edges - Review These
- `netem over Toxiproxy` → `Toxiproxy Half-RTT per Direction`  [AMBIGUOUS]
  docs/harness-architecture.md · relation: conceptually_related_to

## Knowledge Gaps
- **10 isolated node(s):** `shardmind`, `Reference policies (no-op, random, greedy primary)`, `The fidelity objection`, `inapplicable_action_cost`, `Measured applicable-action fraction (~54%)` (+5 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 250 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Roadmap` connect `Session Scoping and Checkpoints` to `Technical Debt Audit`, `Cluster Sizing and Scope Cuts`, `Falsification Test and Parity`, `Cluster Pilot and netem Results`, `Real-Cluster Harness Design`, `Sim-to-Real Transfer Parity`, `Testing Strategy`?**
  _High betweenness centrality (0.159) - this node is a cross-community bridge._
- **Are the 29 inferred relationships involving `FragmentCatalog` (e.g. with `ActionSpace` and `CatalogConfig`) actually correct?**
  _`FragmentCatalog` has 29 INFERRED edges - model-reasoned connections that need verification._
- **What connects `shardmind`, `Reference policies (no-op, random, greedy primary)`, `The fidelity objection` to the rest of the system?**
  _10 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Configuration and Workload Core` be split into smaller, more focused modules?**
  _Cohesion score 0.056314699792960665 - nodes in this community are weakly interconnected._
- **Why does `ShardMindConfig` connect `Configuration and Workload Core` to `Cost Model and Latency`, `Falsification Test and Parity`, `Determinism Tests`, `Live Dashboard`, `Gymnasium Environment`, `Cluster Pilot and netem Results`, `Action Space and Simulator`, `Baseline Policies`, `Cluster Simulator Loop`, `Analysis Dashboard`, `Episode Export and Atlas`, `Topology Construction and Tests`?**
  _High betweenness centrality (0.081) - this node is a cross-community bridge._
- **Are the 32 inferred relationships involving `ShardMindConfig` (e.g. with `episode_frame()` and `main()`) actually correct?**
  _`ShardMindConfig` has 32 INFERRED edges - model-reasoned connections that need verification._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `netem over Toxiproxy` and `Toxiproxy Half-RTT per Direction`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._