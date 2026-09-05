#!/usr/bin/env bash
set -euo pipefail

scenario=${1:-}
[[ "$scenario" == 001 || "$scenario" == 002 ]] || { echo "usage: $0 <001|002>" >&2; exit 64; }
[[ ${EUID:-$(id -u)} -eq 0 ]] || exec sudo -E bash "$0" "$@"

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
WT=${WIRETAP_BIN:-wiretap}
CNS=${BAUDOT_CALLER_NS:-bdt-caller}
SNS=${BAUDOT_CALLEE_NS:-bdt-callee}
WORK=${BAUDOT_WIRETAP_DIR:-$ROOT/target/wiretap-routed/$scenario}
EVIDENCE=${BAUDOT_EVIDENCE_DIR:-$ROOT/target/evidence-routed}
CORR=${BAUDOT_CORRELATION:-$(python3 -c 'import uuid; print(uuid.uuid4())')}

# Do not use 192.0.2.0/24 here: Wiretap reserves that prefix for its IPv4 API.
UL_HOST=198.18.0.1
UL_CLIENT=198.18.0.2
SIG_HOST=10.77.10.1
SIP_SERVER=10.77.10.2
MEDIA_HOST=10.77.20.1
MEDIA_SERVER=10.77.20.2
SIP_PORT=5070
SERVER_SIP_PORT=5080
MEDIA_PORT=40000
WT_PORT=51820
SIG_NET=10.77.10.0/24
MEDIA_NET=10.77.20.0/24

server_pid=""; callee_pid=""; socat_pid=""; relay_up=0; e2ee_up=0; RUN=""

safe_server_log() {
  [[ -f "$WORK/server.log" ]] || return 0
  sed -E \
    -e 's/(private_key=).*/\1[REDACTED]/' \
    -e 's/(PrivateKey[[:space:]]*=[[:space:]]*).*/\1[REDACTED]/' \
    "$WORK/server.log"
}

cleanup() {
  set +e
  [[ -n "$callee_pid" ]] && kill "$callee_pid" 2>/dev/null
  [[ -n "$socat_pid" ]] && kill "$socat_pid" 2>/dev/null
  if [[ -n "$RUN" && -f "$WORK/server.log" ]]; then
    safe_server_log >"$RUN/wiretap-server.log" 2>/dev/null
  fi
  [[ -n "$server_pid" ]] && kill "$server_pid" 2>/dev/null
  if ip netns list | grep -q "^${CNS}\b"; then
    ((e2ee_up)) && ip netns exec "$CNS" wg-quick down "$WORK/wiretap.conf" >/dev/null 2>&1
    ((relay_up)) && ip netns exec "$CNS" wg-quick down "$WORK/wiretap_relay.conf" >/dev/null 2>&1
  fi
  ip netns del "$CNS" 2>/dev/null
  ip netns del "$SNS" 2>/dev/null
  ip link del bdt-ul-h 2>/dev/null
  ip link del bdt-sig-h 2>/dev/null
  ip link del bdt-med-h 2>/dev/null
  rm -rf "$WORK"
  [[ -n "${SUDO_UID:-}" && -d "$EVIDENCE" ]] && chown -R "${SUDO_UID}:${SUDO_GID}" "$EVIDENCE" 2>/dev/null
}
trap cleanup EXIT

for bin in "$WT" ip wg-quick java mvn socat; do command -v "$bin" >/dev/null; done
rm -rf "$WORK"; mkdir -p "$WORK" "$EVIDENCE"

cd "$ROOT"
mvn -q -DskipTests compile dependency:build-classpath -Dmdep.outputFile=target/baudot-runtime-classpath.txt
CP="$ROOT/target/classes:$(cat "$ROOT/target/baudot-runtime-classpath.txt")"

ip netns add "$CNS"; ip netns add "$SNS"
ip -n "$CNS" link set lo up; ip -n "$SNS" link set lo up

ip link add bdt-ul-h type veth peer name bdt-ul-c
ip link set bdt-ul-c netns "$CNS"
ip addr add "$UL_HOST/24" dev bdt-ul-h; ip link set bdt-ul-h up
ip -n "$CNS" addr add "$UL_CLIENT/24" dev bdt-ul-c; ip -n "$CNS" link set bdt-ul-c up

ip link add bdt-sig-h type veth peer name bdt-sig-s
ip link set bdt-sig-s netns "$SNS"
ip addr add "$SIG_HOST/24" dev bdt-sig-h; ip link set bdt-sig-h up
ip -n "$SNS" addr add "$SIP_SERVER/24" dev bdt-sig-s; ip -n "$SNS" link set bdt-sig-s up

ip link add bdt-med-h type veth peer name bdt-med-s
ip link set bdt-med-s netns "$SNS"
ip addr add "$MEDIA_HOST/24" dev bdt-med-h; ip link set bdt-med-h up
ip -n "$SNS" addr add "$MEDIA_SERVER/24" dev bdt-med-s; ip -n "$SNS" link set bdt-med-s up

routes="$SIG_NET"
if [[ "$scenario" == 001 ]]; then
  routes="$SIG_NET,$MEDIA_NET"
else
  # Keep send() successful while proving the media CIDR is absent from Wiretap.
  # The isolated dummy interface absorbs the packet instead of allowing any
  # fallback path to the callee namespace.
  ip -n "$CNS" link add bdt-med-drop type dummy
  ip -n "$CNS" addr add 10.77.20.254/24 dev bdt-med-drop
  ip -n "$CNS" link set bdt-med-drop up
fi

cd "$WORK"
"$WT" configure --disable-ipv6 --endpoint "$UL_CLIENT:$WT_PORT" --routes "$routes" --port "$WT_PORT" >configure.log
CALLER_SIP=$(sed -n 's/^Address = \([0-9.]*\)\/.*/\1/p' "$WORK/wiretap.conf" | head -n1)
[[ -n "$CALLER_SIP" ]] || { echo "unable to read Wiretap E2EE IPv4 address" >&2; exit 1; }

ip netns exec "$CNS" wg-quick up "$WORK/wiretap_relay.conf"; relay_up=1
ip netns exec "$CNS" wg-quick up "$WORK/wiretap.conf"; e2ee_up=1
"$WT" serve -f "$WORK/wiretap_server.conf" >server.log 2>&1 & server_pid=$!

for _ in $(seq 1 100); do
  ip netns exec "$CNS" "$WT" ping >/dev/null 2>&1 && break
  if ! kill -0 "$server_pid" 2>/dev/null; then
    safe_server_log >&2
    exit 1
  fi
  sleep .1
done
if ! ip netns exec "$CNS" "$WT" ping >/dev/null 2>&1; then
  echo "Wiretap API did not become reachable" >&2
  safe_server_log >&2
  exit 1
fi

# The caller sources routed packets from Wiretap's E2EE identity so WireGuard
# accepts them. SIP 200 responses follow Via/received to the server-side exposed
# port. Wiretap forwards that IPv4 UDP port to client loopback; this shim hands
# the datagram to the JAIN listener bound to the E2EE address.
ip netns exec "$CNS" socat -u \
  UDP4-RECVFROM:"$SIP_PORT",bind=127.0.0.1,reuseaddr,fork \
  UDP4-SENDTO:"$CALLER_SIP:$SIP_PORT" >/dev/null 2>&1 &
socat_pid=$!
ip netns exec "$CNS" "$WT" expose --local "$SIP_PORT" --remote "$SIP_PORT" --protocol udp >/dev/null

SCENARIO_ID="$scenario-wiretap-routed"
EXPECT_MEDIA=$([[ "$scenario" == 001 ]] && echo true || echo false)
RUN="$EVIDENCE/$SCENARIO_ID/$CORR"
mkdir -p "$RUN"
cat >"$RUN/topology.properties" <<EOF
wiretap.version=$($WT --version 2>/dev/null | head -n1)
wiretap.routes=$routes
wiretap.clientE2EE=$CALLER_SIP
wiretap.ipv4Api=192.0.2.2
underlay=$UL_HOST/24<->$UL_CLIENT/24
signaling.serverSide=$SIG_HOST/24<->$SIP_SERVER/24
signaling.reverseExpose=$SIG_HOST:$SIP_PORT->127.0.0.1:$SIP_PORT->$CALLER_SIP:$SIP_PORT
media=$MEDIA_HOST/24<->$MEDIA_SERVER/24
scenario.expectMedia=$EXPECT_MEDIA
EOF
ip netns exec "$CNS" ip route show >"$RUN/caller-routes.txt"
ip netns exec "$SNS" ip route show >"$RUN/callee-routes.txt"
ip netns exec "$CNS" "$WT" status >"$RUN/wiretap-status.txt"

COMMON=(
  BAUDOT_SCENARIO="$SCENARIO_ID"
  BAUDOT_CORRELATION="$CORR"
  BAUDOT_EVIDENCE_DIR="$EVIDENCE"
  BAUDOT_CALLER_SIP_IP="$CALLER_SIP"
  BAUDOT_CALLER_SIP_PORT="$SIP_PORT"
  BAUDOT_CALLEE_SIP_BIND_IP="$SIP_SERVER"
  BAUDOT_CALLEE_SIP_IP="$SIP_SERVER"
  BAUDOT_CALLEE_SIP_PORT="$SERVER_SIP_PORT"
  BAUDOT_MEDIA_BIND_IP="$MEDIA_SERVER"
  BAUDOT_MEDIA_BIND_PORT="$MEDIA_PORT"
  BAUDOT_MEDIA_TARGET_IP="$MEDIA_SERVER"
  BAUDOT_MEDIA_TARGET_PORT="$MEDIA_PORT"
  BAUDOT_EXPECT_MEDIA="$EXPECT_MEDIA"
  BAUDOT_TIMEOUT_MS=5000
)

ip netns exec "$SNS" env "${COMMON[@]}" BAUDOT_ROLE=callee \
  java -cp "$CP" org.mcc0nnell.baudot.harness.BaudotProbe >"$RUN/callee.log" 2>&1 &
callee_pid=$!

CALLEE_EVENTS="$RUN/callee/events.jsonl"
for _ in $(seq 1 100); do
  [[ -f "$CALLEE_EVENTS" ]] && grep -q 'sip.endpoint.ready' "$CALLEE_EVENTS" && break
  kill -0 "$callee_pid" 2>/dev/null || { cat "$RUN/callee.log" >&2; exit 1; }
  sleep .1
done
[[ -f "$CALLEE_EVENTS" ]] && grep -q 'sip.endpoint.ready' "$CALLEE_EVENTS" || { cat "$RUN/callee.log" >&2; exit 1; }

ip netns exec "$CNS" env "${COMMON[@]}" BAUDOT_ROLE=caller \
  java -cp "$CP" org.mcc0nnell.baudot.harness.BaudotProbe
wait "$callee_pid"; callee_pid=""

java -cp "$CP" org.mcc0nnell.baudot.harness.EvidenceAggregator "$RUN/caller" "$RUN/callee"
safe_server_log >"$RUN/wiretap-server.log"
(
  cd "$RUN"
  sha256sum topology.properties caller-routes.txt callee-routes.txt wiretap-status.txt wiretap-server.log \
    caller/manifest.sha256 callee/manifest.sha256 aggregate/manifest.sha256 >bundle.manifest.sha256
)
cat "$RUN/aggregate/result.json"
