#!/bin/sh
# Apply per-destination egress delay, then become cockroach.
#
# NETEM_RULES is "ip=delay_ms;ip=delay_ms;...". Each entry is ONE DIRECTION:
# netem shapes egress only, so a round trip of r between two nodes needs r/2
# configured on each side. scripts/gen_cluster.py already halves it.
set -e

if [ -n "$NETEM_RULES" ]; then
  DEV="${NETEM_DEV:-eth0}"
  # htb with an unshaped default class, so traffic we did not name is untouched.
  tc qdisc add dev "$DEV" root handle 1: htb default 99
  tc class add dev "$DEV" parent 1: classid 1:99 htb rate 1000mbit
  i=1
  echo "$NETEM_RULES" | tr ';' '\n' | while IFS='=' read -r peer delay; do
    [ -z "$peer" ] && continue
    i=$((i + 1))
    tc class  add dev "$DEV" parent 1: classid "1:$i" htb rate 1000mbit
    tc qdisc  add dev "$DEV" parent "1:$i" handle "$((i * 10)):" netem delay "${delay}ms"
    tc filter add dev "$DEV" protocol ip parent 1:0 prio 1 u32 \
        match ip dst "$peer/32" flowid "1:$i"
    echo "netem: -> $peer  +${delay}ms egress"
  done
else
  echo "netem: NETEM_RULES unset, no shaping applied" >&2
fi

exec /usr/local/bin/cockroach "$@"
