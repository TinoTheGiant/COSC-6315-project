# CCGrid 2027 abstract (draft, 15 November 2026)

Double-blind: no names, institution or repository in this text.
Numbers: docs/results-log.md, "Training round, 15 November" and
"Cluster evaluation 1". The cluster figures rest on one episode per policy on each of four workload seeds.

**Title:** Reinforcement Learning for Dynamic Data Fragmentation and Allocation

Distributed databases fix how data is split into shards at design time and
place those shards with key-based rules that never observe where requests
originate. When the geographic center of a workload moves, as it does daily in
multi-region services and abruptly during local events, placement drifts away
from the traffic and transaction latency rises. We train a Deep Q-Network
agent that adjusts placement continuously. Its actions move a shard's
leaseholder, move a replica, or split the shard, and its reward combines
transaction latency, the volume of data moved, and load imbalance. We mask
invalid actions and use multi-step returns, so that a move is credited with
the latency it saves in later windows. The agent is trained in a simulator
of a six-region cluster and evaluated on a six-node CockroachDB cluster with
injected wide-area latency. A harness executes each action on the cluster and
reads the resulting placement back before timing real transactions. We compare
the agent with static hashing, a traffic-following heuristic, and a
co-location planner modeled on Lion. In simulation the agent is 14% faster
than static hashing and moves about a fifth of the data the heuristic moves,
but remains 17 ms slower than that heuristic. On the cluster, over four workload seeds, the heuristic is cheapest and the
agent second on every seed, the agent is 12.6% faster than static
hashing, and static hashing and the heuristic both run about 14% slower than
the simulator predicts.

**Index terms:** distributed databases, data placement, fragmentation,
replica allocation, deep reinforcement learning, geo-distribution
