#!/usr/bin/env bash
set -euo pipefail

[[ ${EUID:-$(id -u)} -eq 0 ]] || exec sudo -E bash "$0" "$@"

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
WT=${WIRETAP_BIN:-wiretap}
CNS=${BAUDOT_CALLER_NS:-bdt-caller}
SNS=${BAUDOT_CALLEE_NS:-bdt-callee}
WORK=${BAUDOT_WIRETAP_DIR:-$ROOT/target/wiretap-rfc4103}
EVIDENCE=${BAUDOT_EVIDENCE_DIR:-$ROOT/target/evidence-routed}
CORR=${BAUDOT_CORRELATION:-$(python3 -c 'import uuid; print(uuid.uuid4())')}
SCENARIO_ID=003-rfc4103-primary-routed
RUN="$EVIDENCE/$SCENARIO_ID/$CORR"

UL_HOST=198.18.0.1
UL_CLIENT=198.18.0.2
SIG_HOST=10.77.10.1
SIP_SERVER=10.77.10.2
MEDIA_HOST=10.77.20.1
MEDIA_SERVER=10.77.20.2
RTT_HOST=10.77.30.1
RTT_SERVER=10.77.30.2
SIP_PORT=5070
SERVER_SIP_PORT=5080
MEDIA_PORT=40000
RTT_PORT=41030
WT_PORT=51820
SIG_NET=10.77.10.0/24
RTT_NET=10.77.30.0/24
ROUTES="$SIG_NET,$RTT_NET"

server_pid=""; caller_pid=""; callee_pid=""; rtt_receiver_pid=""
relay_up=0; e2ee_up=0

safe_server_log() {
  [[ -f "$WORK/server.log" ]] || return 0
  sed -E \
    -e 's/(private_key=).*/\1[REDACTED]/' \
    -e 's/(PrivateKey[[:space:]]*=[[:space:]]*).*/\1[REDACTED]/' \
    "$WORK/server.log"
}

cleanup() {
  set +e
  [[ -n "$caller_pid" ]] && kill "$caller_pid" 2>/dev/null
  [[ -n "$callee_pid" ]] && kill "$callee_pid" 2>/dev/null
  [[ -n "$rtt_receiver_pid" ]] && kill "$rtt_receiver_pid" 2>/dev/null
  if [[ -f "$WORK/server.log" && -d "$RUN" ]]; then
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
  ip link del bdt-rtt-h 2>/dev/null
  rm -rf "$WORK"
  [[ -n "${SUDO_UID:-}" && -d "$EVIDENCE" ]] && chown -R "${SUDO_UID}:${SUDO_GID}" "$EVIDENCE" 2>/dev/null
}
trap cleanup EXIT

for bin in "$WT" ip wg-quick java mvn python3; do command -v "$bin" >/dev/null; done
rm -rf "$WORK" "$RUN"
mkdir -p "$WORK" "$RUN/vector"

cd "$ROOT"
python3 scripts/materialize_rfc4103_runtime_vector.py \
  --vector multibyte-primary-block \
  --output "$RUN/vector"
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

ip link add bdt-rtt-h type veth peer name bdt-rtt-s
ip link set bdt-rtt-s netns "$SNS"
ip addr add "$RTT_HOST/24" dev bdt-rtt-h; ip link set bdt-rtt-h up
ip -n "$SNS" addr add "$RTT_SERVER/24" dev bdt-rtt-s; ip -n "$SNS" link set bdt-rtt-s up

# The generic media plane is intentionally not routed through Wiretap in this
# scenario. A dummy caller-side network keeps UDP send() successful while the
# callee observes MEDIA_FAILED independently from RTT.
ip -n "$CNS" link add bdt-med-drop type dummy
ip -n "$CNS" addr add 10.77.20.254/24 dev bdt-med-drop
ip -n "$CNS" link set bdt-med-drop up

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
underlay=$UL_HOST/24<->$UL_CLIENT/24
signaling.serverSide=$SIG_HOST/24<->$SIP_SERVER/24
signaling.responseRouting=rfc3581-rport-over-transparent-flow
media=$MEDIA_HOST/24<->$MEDIA_SERVER/24
media.routed=false
rtt=$RTT_HOST/24<->$RTT_SERVER/24
rtt.routed=true
rtt.transport=primary-text-t140-over-rtp
rtt.sdpNegotiated=false
scenario.expectMedia=false
scenario.expectRtt=true
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
  BAUDOT_EXPECT_MEDIA=false
  BAUDOT_TIMEOUT_MS=5000
)
RTT_COMMON=(
  BAUDOT_SCENARIO="$SCENARIO_ID"
  BAUDOT_CORRELATION="$CORR"
  BAUDOT_EVIDENCE_DIR="$EVIDENCE"
  BAUDOT_RTT_PACKET_FILE="$RUN/vector/packet.bin"
  BAUDOT_RTT_VECTOR_PROPERTIES="$RUN/vector/vector.properties"
  BAUDOT_RTT_BIND_IP="$RTT_SERVER"
  BAUDOT_RTT_BIND_PORT="$RTT_PORT"
  BAUDOT_RTT_TARGET_IP="$RTT_SERVER"
  BAUDOT_RTT_TARGET_PORT="$RTT_PORT"
  BAUDOT_EXPECT_RTT=true
  BAUDOT_RTT_TIMEOUT_MS=8000
)

ip netns exec "$SNS" env "${RTT_COMMON[@]}" BAUDOT_RTT_ROLE=receiver \
  java -cp "$CP" org.mcc0nnell.baudot.harness.Rfc4103RuntimeProbe >"$RUN/rtt-receiver.log" 2>&1 &
rtt_receiver_pid=$!

RTT_EVENTS="$RUN/rtt-receiver/events.jsonl"
for _ in $(seq 1 100); do
  [[ -f "$RTT_EVENTS" ]] && grep -q 'rtt.receiver.ready' "$RTT_EVENTS" && break
  kill -0 "$rtt_receiver_pid" 2>/dev/null || { cat "$RUN/rtt-receiver.log" >&2; exit 1; }
  sleep .1
done
[[ -f "$RTT_EVENTS" ]] && grep -q 'rtt.receiver.ready' "$RTT_EVENTS" || { cat "$RUN/rtt-receiver.log" >&2; exit 1; }

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
  java -cp "$CP" org.mcc0nnell.baudot.harness.BaudotProbe >"$RUN/caller.log" 2>&1 &
caller_pid=$!
CALLER_EVENTS="$RUN/caller/events.jsonl"
for _ in $(seq 1 100); do
  [[ -f "$CALLER_EVENTS" ]] && grep -q 'sip.dialog.established' "$CALLER_EVENTS" && break
  kill -0 "$caller_pid" 2>/dev/null || { cat "$RUN/caller.log" >&2; exit 1; }
  sleep .05
done
[[ -f "$CALLER_EVENTS" ]] && grep -q 'sip.dialog.established' "$CALLER_EVENTS" || { cat "$RUN/caller.log" >&2; exit 1; }

# RTT replay is gated on the observed established SIP dialog. The SIP/SDP in
# this slice does not negotiate text/t140 yet; that remains an explicit later
# boundary. This step proves canonical packet transport and interpretation.
ip netns exec "$CNS" env "${RTT_COMMON[@]}" BAUDOT_RTT_ROLE=sender \
  java -cp "$CP" org.mcc0nnell.baudot.harness.Rfc4103RuntimeProbe

wait "$caller_pid"; caller_pid=""
wait "$callee_pid"; callee_pid=""
wait "$rtt_receiver_pid"; rtt_receiver_pid=""

java -cp "$CP" org.mcc0nnell.baudot.harness.EvidenceAggregator "$RUN/caller" "$RUN/callee"

python3 - "$RUN" <<'PY'
import json
import pathlib
import sys

run = pathlib.Path(sys.argv[1])
call = json.loads((run / "aggregate" / "result.json").read_text(encoding="utf-8"))

def props(path):
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        result[key] = value
    return result

rtt = props(run / "rtt-receiver" / "result.properties")
passed = call.get("scenarioResult") == "PASS" and rtt.get("rtt.state") == "RTT_RECEIVED"
summary = {
    "scenario": call.get("scenario"),
    "scenarioResult": "PASS" if passed else "FAIL",
    "callState": call.get("callState"),
    "mediaState": call.get("mediaState"),
    "rttState": rtt.get("rtt.state"),
    "rttVector": f"{rtt.get('rtt.suite')}@{rtt.get('rtt.suite.version')}/{rtt.get('rtt.vector')}",
    "rttPacketSha256": rtt.get("rtt.packet.sha256"),
    "t140blockHex": rtt.get("rtt.t140block.hex"),
    "sipAckObserved": call.get("sipAckObserved"),
    "sdpNegotiated": False,
}
(run / "scenario-result.json").write_text(json.dumps(summary, separators=(",", ":")) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2))
if not passed:
    raise SystemExit(1)
PY

safe_server_log >"$RUN/wiretap-server.log"
(
  cd "$RUN"
  sha256sum topology.properties caller-routes.txt callee-routes.txt wiretap-status.txt wiretap-server.log \
    vector/packet.bin vector/vector.properties \
    caller/manifest.sha256 callee/manifest.sha256 \
    rtt-sender/manifest.sha256 rtt-receiver/manifest.sha256 \
    aggregate/manifest.sha256 scenario-result.json >bundle.manifest.sha256
)
