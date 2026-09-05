#!/usr/bin/env bash
set -euo pipefail

[[ ${EUID:-$(id -u)} -eq 0 ]] || exec sudo -E bash "$0" "$@"

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
WT=${WIRETAP_BIN:-wiretap}
CNS=${BAUDOT_CALLER_NS:-bdt-rtt-caller}
SNS=${BAUDOT_CALLEE_NS:-bdt-rtt-callee}
WORK=${BAUDOT_WIRETAP_DIR:-$ROOT/target/wiretap-routed/003}
EVIDENCE=${BAUDOT_EVIDENCE_DIR:-$ROOT/target/evidence-routed}
CORR=${BAUDOT_CORRELATION:-$(python3 -c 'import uuid; print(uuid.uuid4())')}

UL_HOST=198.18.0.1
UL_CLIENT=198.18.0.2
SIG_HOST=10.77.10.1
SIP_SERVER=10.77.10.2
MEDIA_HOST=10.77.20.1
MEDIA_SERVER=10.77.20.2
SIP_PORT=5070
SERVER_SIP_PORT=5080
MEDIA_SOURCE_PORT=40001
MEDIA_PORT=40000
WT_PORT=51820
SIG_NET=10.77.10.0/24
MEDIA_NET=10.77.20.0/24
ROUTES="$SIG_NET,$MEDIA_NET"
RESPONSE_ROUTING=rfc3581-rport-over-transparent-flow
SCENARIO_ID=003-rtt-rfc4103-wiretap
RUN="$EVIDENCE/$SCENARIO_ID/$CORR"

server_pid=""; callee_pid=""; relay_up=0; e2ee_up=0

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
  if [[ -f "$WORK/server.log" ]]; then
    safe_server_log >"$RUN/wiretap-server.log" 2>/dev/null
  fi
  [[ -n "$server_pid" ]] && kill "$server_pid" 2>/dev/null
  if ip netns list | grep -q "^${CNS}\b"; then
    ((e2ee_up)) && ip netns exec "$CNS" wg-quick down "$WORK/wiretap.conf" >/dev/null 2>&1
    ((relay_up)) && ip netns exec "$CNS" wg-quick down "$WORK/wiretap_relay.conf" >/dev/null 2>&1
  fi
  ip netns del "$CNS" 2>/dev/null
  ip netns del "$SNS" 2>/dev/null
  ip link del bdt-rtt-ul-h 2>/dev/null
  ip link del bdt-rtt-sig-h 2>/dev/null
  ip link del bdt-rtt-med-h 2>/dev/null
  rm -rf "$WORK"
  [[ -n "${SUDO_UID:-}" && -d "$EVIDENCE" ]] && chown -R "${SUDO_UID}:${SUDO_GID}" "$EVIDENCE" 2>/dev/null
}

rm -rf "$WORK"
mkdir -p "$WORK" "$RUN"
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
  --namespace "$SNS" \
  --host-link bdt-rtt-ul-h \
  --host-link bdt-rtt-sig-h \
  --host-link bdt-rtt-med-h \
  --require-bin ip \
  --require-bin wg-quick \
  --require-bin java \
  --require-bin mvn \
  --evidence-root "$EVIDENCE" \
  --output "$RUN/preflight.properties"
trap cleanup EXIT

mvn -q -DskipTests compile dependency:build-classpath -Dmdep.outputFile=target/baudot-runtime-classpath.txt
CP="$ROOT/target/classes:$(cat "$ROOT/target/baudot-runtime-classpath.txt")"

ip netns add "$CNS"; ip netns add "$SNS"
ip -n "$CNS" link set lo up; ip -n "$SNS" link set lo up

ip link add bdt-rtt-ul-h type veth peer name bdt-rtt-ul-c
ip link set bdt-rtt-ul-c netns "$CNS"
ip addr add "$UL_HOST/24" dev bdt-rtt-ul-h; ip link set bdt-rtt-ul-h up
ip -n "$CNS" addr add "$UL_CLIENT/24" dev bdt-rtt-ul-c; ip -n "$CNS" link set bdt-rtt-ul-c up

ip link add bdt-rtt-sig-h type veth peer name bdt-rtt-sig-s
ip link set bdt-rtt-sig-s netns "$SNS"
ip addr add "$SIG_HOST/24" dev bdt-rtt-sig-h; ip link set bdt-rtt-sig-h up
ip -n "$SNS" addr add "$SIP_SERVER/24" dev bdt-rtt-sig-s; ip -n "$SNS" link set bdt-rtt-sig-s up

ip link add bdt-rtt-med-h type veth peer name bdt-rtt-med-s
ip link set bdt-rtt-med-s netns "$SNS"
ip addr add "$MEDIA_HOST/24" dev bdt-rtt-med-h; ip link set bdt-rtt-med-h up
ip -n "$SNS" addr add "$MEDIA_SERVER/24" dev bdt-rtt-med-s; ip -n "$SNS" link set bdt-rtt-med-s up

cd "$WORK"
"$WT" configure --endpoint "$UL_CLIENT:$WT_PORT" --routes "$ROUTES" --port "$WT_PORT" >configure.log
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

cat >"$RUN/topology.properties" <<EOF
wiretap.version=$($WT --version 2>/dev/null | head -n1)
wiretap.routes=$ROUTES
wiretap.clientE2EE=$CALLER_SIP
wiretap.controlApi=::2
topology.preflight=preflight.properties
underlay=$UL_HOST/24<->$UL_CLIENT/24
signaling.serverSide=$SIG_HOST/24<->$SIP_SERVER/24
signaling.responseRouting=$RESPONSE_ROUTING
rtt.media=$MEDIA_HOST/24<->$MEDIA_SERVER/24
rtt.sdp.redPayloadType=99
rtt.sdp.t140PayloadType=98
rtt.clockRate=1000
rtt.redundancy=98/98/98
scenario.expectMedia=true
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
  BAUDOT_MEDIA_SOURCE_PORT="$MEDIA_SOURCE_PORT"
  BAUDOT_MEDIA_BIND_IP="$MEDIA_SERVER"
  BAUDOT_MEDIA_BIND_PORT="$MEDIA_PORT"
  BAUDOT_MEDIA_TARGET_IP="$MEDIA_SERVER"
  BAUDOT_MEDIA_TARGET_PORT="$MEDIA_PORT"
  BAUDOT_TIMEOUT_MS=5000
)

ip netns exec "$SNS" env "${COMMON[@]}" BAUDOT_ROLE=callee \
  java -cp "$CP" org.mcc0nnell.baudot.harness.RttSipProbe >"$RUN/callee.log" 2>&1 &
callee_pid=$!

CALLEE_EVENTS="$RUN/callee/events.jsonl"
for _ in $(seq 1 100); do
  [[ -f "$CALLEE_EVENTS" ]] && grep -q 'sip.endpoint.ready' "$CALLEE_EVENTS" && break
  kill -0 "$callee_pid" 2>/dev/null || { cat "$RUN/callee.log" >&2; exit 1; }
  sleep .1
done
[[ -f "$CALLEE_EVENTS" ]] && grep -q 'sip.endpoint.ready' "$CALLEE_EVENTS" || { cat "$RUN/callee.log" >&2; exit 1; }

ip netns exec "$CNS" env "${COMMON[@]}" BAUDOT_ROLE=caller \
  java -cp "$CP" org.mcc0nnell.baudot.harness.RttSipProbe
wait "$callee_pid"; callee_pid=""

java -cp "$CP" org.mcc0nnell.baudot.harness.EvidenceAggregator "$RUN/caller" "$RUN/callee"
cd "$ROOT"
python3 -m scripts.validate_wiretap_rtt --run-dir "$RUN"

safe_server_log >"$RUN/wiretap-server.log"
(
  cd "$RUN"
  required=(
    preflight.properties
    topology.properties
    caller-routes.txt
    callee-routes.txt
    wiretap-status.txt
    wiretap-server.log
    caller/manifest.sha256
    callee/manifest.sha256
    aggregate/manifest.sha256
    caller/answer.sdp
    callee/offer.sdp
    caller/rtt-datagram-1-sent.bin
    caller/rtt-datagram-2-sent.bin
    callee/rtt-datagram-1-received.bin
    callee/rtt-datagram-2-received.bin
    rtt-validation.json
  )
  for artifact in "${required[@]}"; do test -f "$artifact"; done
  sha256sum "${required[@]}" >bundle.manifest.sha256
)

cat "$RUN/aggregate/result.json"
cat "$RUN/rtt-validation.json"
