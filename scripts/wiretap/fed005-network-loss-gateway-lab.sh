#!/usr/bin/env bash
set -euo pipefail

[[ ${EUID:-$(id -u)} -eq 0 ]] || exec sudo -E bash "$0" "$@"

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
WT=${WIRETAP_BIN:-wiretap}
CNS=${BAUDOT_CALLER_NS:-bdt-fed005-caller}
WORK=${BAUDOT_WIRETAP_DIR:-$ROOT/target/wiretap-routed/fed005}
RUN=${BAUDOT_RUN_DIR:-$ROOT/target/evidence-routed/BAUDOT-FED-005/network-loss}

UL_HOST=198.18.5.1
UL_CLIENT=198.18.5.2
SIG_NET=10.77.15.0/24
MEDIA_SERVER=10.77.25.2
MEDIA_NET=10.77.25.0/24
ROUTES="$SIG_NET,$MEDIA_NET"
RESPONSE_ROUTING=rfc3581-rport-over-transparent-flow
WT_PORT=51825
GATEWAY_PORT=49000
SINK_PORT=49100
SOURCE_PORT=49201
NFT_TABLE=baudot_fed005

server_pid=""
gateway_pid=""
sink_pid=""
relay_up=0
e2ee_up=0
nft_up=0
RUNNER_USER=${SUDO_USER:-}
RUNNER_UID=${SUDO_UID:-$(id -u)}
RUNNER_GID=${SUDO_GID:-$(id -g)}

safe_server_log() {
  [[ -f "$WORK/server.log" ]] || return 0
  sed -E \
    -e 's/(private_key=).*/\1[REDACTED]/' \
    -e 's/(PrivateKey[[:space:]]*=[[:space:]]*).*/\1[REDACTED]/' \
    "$WORK/server.log"
}

cleanup() {
  set +e
  [[ -n "$gateway_pid" ]] && kill "$gateway_pid" 2>/dev/null
  [[ -n "$sink_pid" ]] && kill "$sink_pid" 2>/dev/null
  [[ -f "$WORK/server.log" ]] && safe_server_log >"$RUN/wiretap-server.log" 2>/dev/null
  [[ -n "$server_pid" ]] && kill "$server_pid" 2>/dev/null
  ((nft_up)) && nft delete table inet "$NFT_TABLE" >/dev/null 2>&1
  if ip netns list | grep -q "^${CNS}\b"; then
    ((e2ee_up)) && ip netns exec "$CNS" wg-quick down "$WORK/wiretap.conf" >/dev/null 2>&1
    ((relay_up)) && ip netns exec "$CNS" wg-quick down "$WORK/wiretap_relay.conf" >/dev/null 2>&1
  fi
  ip netns del "$CNS" 2>/dev/null
  ip link del bdt-f5-ul-h 2>/dev/null
  ip link del bdt-f5-med-h 2>/dev/null
  [[ -n "${SUDO_UID:-}" && -d "$RUN" ]] && chown -R "${SUDO_UID}:${SUDO_GID}" "$RUN" 2>/dev/null
}
trap cleanup EXIT

run_as_runner() {
  if [[ -n "$RUNNER_USER" ]]; then
    sudo -u "$RUNNER_USER" -H env PATH="$PATH" "$@"
  else
    "$@"
  fi
}

run_as_runner_in_ns() {
  local ns=$1
  shift
  if [[ -n "$RUNNER_USER" ]]; then
    ip netns exec "$ns" sudo -u "$RUNNER_USER" -H env PATH="$PATH" "$@"
  else
    ip netns exec "$ns" "$@"
  fi
}

rm -rf "$WORK" "$RUN"
mkdir -p "$WORK" "$RUN/source" "$RUN/gateway" "$RUN/sink"
chown -R "$RUNNER_UID:$RUNNER_GID" "$RUN"

cd "$ROOT"
python3 scripts/wiretap_topology_preflight.py \
  --wiretap-bin "$WT" \
  --underlay-address "$UL_HOST/24" \
  --underlay-address "$UL_CLIENT/24" \
  --signaling-network "$SIG_NET" \
  --media-network "$MEDIA_NET" \
  --routes "$ROUTES" \
  --response-routing "$RESPONSE_ROUTING" \
  --namespace "$CNS" \
  --host-link bdt-f5-ul-h \
  --host-link bdt-f5-med-h \
  --require-bin ip \
  --require-bin wg-quick \
  --require-bin nft \
  --require-bin node \
  --evidence-root "$(dirname "$RUN")" \
  --output "$RUN/preflight.properties"

ip netns add "$CNS"
ip -n "$CNS" link set lo up

ip link add bdt-f5-ul-h type veth peer name bdt-f5-ul-c
ip link set bdt-f5-ul-c netns "$CNS"
ip addr add "$UL_HOST/24" dev bdt-f5-ul-h
ip link set bdt-f5-ul-h up
ip -n "$CNS" addr add "$UL_CLIENT/24" dev bdt-f5-ul-c
ip -n "$CNS" link set bdt-f5-ul-c up

# Host-owned routed media endpoint. Wiretap server re-originates UDP into the
# host network stack; Chromium stays in the already-proven host environment.
ip link add bdt-f5-med-h type dummy
ip addr add "$MEDIA_SERVER/24" dev bdt-f5-med-h
ip link set bdt-f5-med-h up

cd "$WORK"
"$WT" configure --endpoint "$UL_CLIENT:$WT_PORT" --routes "$ROUTES" --port "$WT_PORT" >configure.log
CALLER_E2EE=$(sed -n 's/^Address = \([0-9.]*\)\/.*/\1/p' "$WORK/wiretap.conf" | head -n1)
[[ -n "$CALLER_E2EE" ]] || { echo "unable to read Wiretap E2EE IPv4 address" >&2; exit 1; }

ip netns exec "$CNS" wg-quick up "$WORK/wiretap_relay.conf"
relay_up=1
ip netns exec "$CNS" wg-quick up "$WORK/wiretap.conf"
e2ee_up=1
"$WT" serve -f "$WORK/wiretap_server.conf" >server.log 2>&1 &
server_pid=$!

for _ in $(seq 1 100); do
  ip netns exec "$CNS" "$WT" ping >/dev/null 2>&1 && break
  if ! kill -0 "$server_pid" 2>/dev/null; then
    safe_server_log >&2
    exit 1
  fi
  sleep .1
done
ip netns exec "$CNS" "$WT" ping >/dev/null 2>&1 || { safe_server_log >&2; exit 1; }

ip netns exec "$CNS" ip route show >"$RUN/caller-routes.txt"
ip route show >"$RUN/server-routes.txt"
ip netns exec "$CNS" "$WT" status >"$RUN/wiretap-status.txt"
cd "$ROOT"

python3 - "$RUN/topology.json" <<PY
import json, sys
payload = {
    "scenario": "BAUDOT-FED-005",
    "transport": "sandia-wiretap-v0.9.0",
    "wiretapClientE2EE": "$CALLER_E2EE",
    "wiretapRoutes": "$ROUTES",
    "signalingNetwork": "$SIG_NET",
    "signalingResponseRouting": "$RESPONSE_ROUTING",
    "mediaNetwork": "$MEDIA_NET",
    "gatewayEndpoint": "$MEDIA_SERVER:$GATEWAY_PORT",
    "sinkEndpoint": "127.0.0.1:$SINK_PORT",
    "gatewayExecutionNamespace": "host",
    "lossPoint": "host-output-after-wiretap-server-reoriginates-udp",
    "faultInjector": "nftables",
    "faultRule": "drop UDP destination $MEDIA_SERVER:$GATEWAY_PORT when RTP sequence field equals 1",
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY

nft add table inet "$NFT_TABLE"
nft_up=1
nft "add chain inet $NFT_TABLE output { type filter hook output priority 0; policy accept; }"
nft add rule inet "$NFT_TABLE" output \
  ip daddr "$MEDIA_SERVER" meta l4proto udp udp dport "$GATEWAY_PORT" \
  @th,80,16 1 counter drop comment "baudot-fed005-drop-seq1"
nft -a list table inet "$NFT_TABLE" >"$RUN/network-loss-ruleset-before.txt"

SINK_READY="$RUN/sink/ready.json"
run_as_runner python3 "$ROOT/scripts/fed005-rtt-sink.py" \
  --bind-host 127.0.0.1 \
  --bind-port "$SINK_PORT" \
  --expect 2 \
  --evidence-dir "$RUN/sink" \
  --ready-file "$SINK_READY" &
sink_pid=$!

GATEWAY_READY="$RUN/gateway/ready.json"
run_as_runner env \
  BAUDOT_GATEWAY_BIND_IP="$MEDIA_SERVER" \
  BAUDOT_GATEWAY_BIND_PORT="$GATEWAY_PORT" \
  BAUDOT_GATEWAY_FORWARD_IP=127.0.0.1 \
  BAUDOT_GATEWAY_FORWARD_PORT="$SINK_PORT" \
  BAUDOT_GATEWAY_EXPECT_DATAGRAMS=2 \
  BAUDOT_GATEWAY_EVIDENCE_DIR="$RUN/gateway" \
  BAUDOT_GATEWAY_READY_FILE="$GATEWAY_READY" \
  node "$ROOT/scripts/fed004-rfc2198-recovery-webrtc-gateway.mjs" &
gateway_pid=$!

for _ in $(seq 1 200); do
  [[ -f "$SINK_READY" && -f "$GATEWAY_READY" ]] && break
  kill -0 "$sink_pid" 2>/dev/null || { echo "FED005 sink exited before readiness" >&2; exit 7; }
  kill -0 "$gateway_pid" 2>/dev/null || { echo "FED005 gateway exited before readiness" >&2; exit 7; }
  sleep .1
done
[[ -f "$SINK_READY" && -f "$GATEWAY_READY" ]] || { echo "FED005 endpoint readiness timed out" >&2; exit 7; }

run_as_runner_in_ns "$CNS" python3 "$ROOT/scripts/fed005-rtt-network-source.py" \
  --target-host "$MEDIA_SERVER" \
  --target-port "$GATEWAY_PORT" \
  --source-port "$SOURCE_PORT" \
  --evidence-dir "$RUN/source"

set +e
wait "$gateway_pid"
gateway_status=$?
gateway_pid=""
wait "$sink_pid"
sink_status=$?
sink_pid=""
set -e

nft -a list table inet "$NFT_TABLE" >"$RUN/network-loss-ruleset-after.txt"
DROPPED=$(awk '/baudot-fed005-drop-seq1/ { for (i=1; i<=NF; i++) if ($i == "packets") { print $(i+1); exit } }' "$RUN/network-loss-ruleset-after.txt")
DROPPED=${DROPPED:-0}
python3 - "$RUN/network-loss-result.json" "$DROPPED" <<PY
import json, sys
payload = {
    "scenario": "BAUDOT-FED-005",
    "mechanism": "nftables-host-output-raw-rtp-sequence-match",
    "droppedSequenceNumber": 1,
    "droppedPackets": int(sys.argv[2]),
    "destination": "$MEDIA_SERVER:$GATEWAY_PORT",
    "rawMatch": "@th,80,16 == 1",
    "wiretapFaultInjectionFeature": False,
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY

if [[ "$gateway_status" -ne 0 || "$sink_status" -ne 0 ]]; then
  echo "BAUDOT-FED-005 process gate failed: gateway=$gateway_status sink=$sink_status" >&2
  exit 8
fi

python3 -m scripts.validate_fed005_network_loss \
  --run-dir "$RUN" \
  --output "$RUN/fed005-terminal-result.json"

safe_server_log >"$RUN/wiretap-server.log"
(
  cd "$RUN"
  required=(
    preflight.properties
    topology.json
    caller-routes.txt
    server-routes.txt
    wiretap-status.txt
    wiretap-server.log
    network-loss-ruleset-before.txt
    network-loss-ruleset-after.txt
    network-loss-result.json
    source/source-result.json
    source/rtt-seq-0-sent.bin
    source/rtt-seq-1-sent.bin
    source/rtt-seq-2-sent.bin
    gateway/gateway-result.json
    gateway/rtt-datagram-1-received.bin
    gateway/rtt-datagram-2-received.bin
    sink/sink-result.json
    sink/rtt-datagram-1-received.bin
    sink/rtt-datagram-2-received.bin
    fed005-terminal-result.json
  )
  for artifact in "${required[@]}"; do test -f "$artifact"; done
  sha256sum "${required[@]}" >bundle.manifest.sha256
)

echo "BAUDOT-FED-005 RUNNABLE_PASS: all three RTP packets emitted; sequence 1 dropped on Wiretap-routed host network path; RED recovery delivered ABC to real Chromium"
cat "$RUN/fed005-terminal-result.json"
