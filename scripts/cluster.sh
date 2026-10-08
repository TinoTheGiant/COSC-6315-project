#!/usr/bin/env bash
# Cluster lifecycle. The cluster is disposable (ADR-0010): built at the start of
# a working session, torn down at the end, never expected to survive a sleep.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker/docker-compose.yml"
FIRST_NODE="$(python3 -c "import sys;sys.path.insert(0,'src');
from shardmind.config import ShardMindConfig
print('crdb-'+ShardMindConfig().topology.region_names[0])")"

# Four of these five are registered in CockroachDB's source but absent from the
# public settings docs, so each is verified rather than assumed (ADR-0009 AI 4).
SETTINGS=(
  "kv.allocator.load_based_rebalancing = 'off'"
  "kv.replicate_queue.enabled = false"
  "kv.lease_queue.enabled = false"
  "kv.split_queue.enabled = false"
  "kv.range_merge.queue.enabled = false"
)

sql() { $COMPOSE exec -T node0 cockroach sql --insecure -e "$1"; }

case "${1:-}" in
up)
  [ -f docker/docker-compose.yml ] || python3 scripts/gen_cluster.py
  $COMPOSE up -d --build
  echo "waiting for nodes..."; sleep 8
  $COMPOSE exec -T node0 cockroach init --insecure 2>/dev/null || echo "(already initialized)"
  sleep 5
  "$0" verify
  cat <<'MSG'

NEXT, and do not skip it: confirm the injected latency is real.
A cluster with no shaping returns plausible numbers that mean nothing.
    scripts/cluster.sh latency
MSG
  ;;

down)
  $COMPOSE down -v
  echo "cluster removed, volumes deleted"
  ;;

status)
  $COMPOSE ps
  sql "SELECT node_id, locality, is_live FROM crdb_internal.kv_node_status ORDER BY node_id;" || true
  ;;

verify)
  echo "applying and verifying cluster settings..."
  fail=0
  for s in "${SETTINGS[@]}"; do
    name="${s%% *}"
    if sql "SET CLUSTER SETTING $s;" >/dev/null 2>&1; then
      echo "  set   $name"
    else
      echo "  FAIL  $name  (not available on this build)"; fail=1
    fi
  done
  echo
  sql "SELECT variable, value FROM [SHOW CLUSTER SETTINGS] WHERE variable IN (
        'kv.allocator.load_based_rebalancing','kv.replicate_queue.enabled',
        'kv.lease_queue.enabled','kv.split_queue.enabled','kv.range_merge.queue.enabled');"
  [ "$fail" = 0 ] || echo "WARNING: a setting did not apply. The allocator may fight the agent."
  ;;

latency)
  # Ground truth for the paper's methods section. Compare against DEFAULT_RTT_MS.
  python3 - <<'PY'
import subprocess, sys
sys.path.insert(0, "src")
from shardmind.config import ShardMindConfig
from shardmind.topology import DEFAULT_RTT_MS
names = list(ShardMindConfig().topology.region_names)
print(f"{'pair':<34}{'expected':>10}{'measured':>10}")
src = f"crdb-{names[0]}"
for j in range(1, len(names)):
    ip = f"172.28.0.{11+j}"
    try:
        out = subprocess.run(["docker","exec",src,"ping","-c","5","-q",ip],
                             capture_output=True, text=True, timeout=40).stdout
        avg = float(out.split("=")[-1].split("/")[1])
    except Exception as e:
        avg = float("nan")
    print(f"{names[0]} -> {names[j]:<18}{DEFAULT_RTT_MS[0][j]:>9.1f}{avg:>10.1f}")
print("\nMeasured should track expected within a few ms. If it reads ~0, netem "
      "did not apply and every latency number from this cluster is worthless.")
PY
  ;;

*)
  echo "usage: scripts/cluster.sh {up|down|status|verify|latency}"; exit 2 ;;
esac
