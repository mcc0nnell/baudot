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

UL_HOST=192.0.2.1
UL_CLIENT=192.0.2.2
SIP_HOST=10.77.10.1
SIP_SERVER=10.77.10.2
MEDIA_HOST=10.77.20.1
MEDIA_SERVER=10.77.20.2
SIP_PORT=5070
SERVER_SIP_PORT=5080
MEDIA_PORT=40000
WT_PORT=51820
SIG_NET=10.77.10.0/24
MEDIA_NET=10.77.20.0/24

server_pid=""; callee_pid=""; relay_up=0; e2ee_up=0
cleanup() {
  set +e
  [[ -n "$callee_pid" ]] && kill "$callee_pid" 2>/dev/null
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

for bin in "$WT" ip wg-quick java mvn; do command -v "$bin" >/dev/null; done
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
ip -n "$CNS" addr add "$SIP_HOST/32" dev lo

ip link add bdt-sig-h type veth peer name bdt-sig-s
ip link set bdt-sig-s netns "$SNS"
ip addr add "$SIP_HOST/24" dev bdt-sig-h; ip link set bdt-sig-h up
ip -n "$SNS" addr add "$SIP_SERVER/24" dev bdt-sig-s; ip -n "$SNS" link set bdt-sig-s up

ip link add bdt-med-h type veth peer name bdt-med-s
ip link set bdt-med-s netns "$SNS"
ip addr add "$MEDIA_HOST/24" dev bdt-med-h; ip link set bdt-med-h up
ip -n "$SNS" addr add "$MEDIA_SERVER/24" dev bdt-med-s; ip -n "$SNS" link set bdt-med-s up

routes="$SIG_NET"
if [[ "$scenario" == 001 ]]; then
  routes="$SIG_NET,$MEDIA_NET"
else
  ip -n "$CNS" link add bdt-med-drop type dummy
  ip -n "$CNS" link set bdt-med-drop up
  ip -n "$CNS" route add "$MEDIA_NET" dev bdt-med-drop
fi

cd "$WORK"
"$WT" configure --endpoint "$UL_CLIENT:$WT_PORT" --routes "$routes" --port "$WT_PORT" >configure.log
ip netns exec "$CNS" wg-quick up "$WORK/wiretap_relay.conf"; relay_up=1
ip netns exec "$CNS" wg-quick up "$WORK/wiretap.conf"; e2ee_up=1
"$WT" serve -f "$WORK/wiretap_server.conf" >server.log 2>&1 & server_pid=$!

for _ in $(seq 1 100); do
  ip netns exec "$CNS" "$WT" ping >/dev/null 2>&1 && break
  kill -0 "$server_pid" 2>/dev/null || { cat server.log >&2; exit 1; }
  sleep .1
done
ip netns exec "$CNS" "$WT" ping >/dev/null 2>&1 || { echo "Wiretap API did not become reachable" >&2; cat server.log >&2; exit 1; }

# SIP replies follow Via as a separate reverse UDP flow. Wiretap's UDP expose
# makes the caller's listener reachable from the server-side network.
ip netns exec "$CNS" "$WT" expose --local "$SIP_PORT" --remote "$SIP_PORT" --protocol udp >/dev/null

SCENARIO_ID="$scenario-wiretap-routed"
EXPECT_MEDIA=$([[ "$scenario" == 001 ]] && echo true || echo false)
RUN="$EVIDENCE/$SCENARIO_ID/$CORR"
mkdir -p "$RUN"
cat >"$RUN/topology.properties" <<EOF
wiretap.version=$($WT --version 2>/dev/null | head -n1)
wiretap.routes=$routes
underlay=$UL_HOST/24<->$UL_CLIENT/24
signaling=$SIP_HOST/24<->$SIP_SERVER/24
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
  BAUDOT_CALLER_SIP_IP="$SIP_HOST"
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
(
  cd "$RUN"
  sha256sum topology.properties caller-routes.txt callee-routes.txt wiretap-status.txt \
    caller/manifest.sha256 callee/manifest.sha256 aggregate/manifest.sha256 >bundle.manifest.sha256
)
cat "$RUN/aggregate/result.json"
