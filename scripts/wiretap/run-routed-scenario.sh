#!/usr/bin/env bash
set -euo pipefail

scenario=${1:-}
if [[ "$scenario" != "001" && "$scenario" != "002" ]]; then
  echo "usage: $0 <001|002>" >&2
  exit 64
fi

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  exec sudo -E bash "$0" "$@"
fi

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
WIRETAP_BIN=${WIRETAP_BIN:-wiretap}
CALLER_NS=${BAUDOT_CALLER_NS:-baudot-caller}
CALLEE_NS=${BAUDOT_CALLEE_NS:-baudot-callee}
WORKDIR=${BAUDOT_WIRETAP_DIR:-$ROOT/target/wiretap-routed/$scenario}
EVIDENCE_ROOT=${BAUDOT_EVIDENCE_DIR:-$ROOT/target/evidence-routed}
CORRELATION=${BAUDOT_CORRELATION:-$(python3 - <<'PY'
import uuid
print(uuid.uuid4())
PY
)}

SIGNALING_CIDR=10.77.10.0/24
MEDIA_CIDR=10.77.20.0/24
CALLER_UNDERLAY=192.0.2.2
HOST_UNDERLAY=192.0.2.1
CALLER_SIP_IP=10.77.10.1
CALLEE_SIP_IP=10.77.10.2
HOST_MEDIA_IP=10.77.20.1
CALLEE_MEDIA_IP=10.77.20.2
SIP_PORT=5070
CALLEE_SIP_PORT=5080
MEDIA_PORT=40000
WIRETAP_PORT=51820

server_pid=""
callee_pid=""
relay_up=0
e2ee_up=0

cleanup() {
  set +e
  [[ -n "$callee_pid" ]] && kill "$callee_pid" 2>/dev/null
  [[ -n "$server_pid" ]] && kill "$server_pid" 2>/dev/null
  if ip netns list | grep -q "^${CALLER_NS}\b"; then
    (( e2ee_up )) && ip netns exec "$CALLER_NS" wg-quick down "$WORKDIR/wiretap.conf" >/dev/null 2>&1
    (( relay_up )) && ip netns exec "$CALLER_NS" wg-quick down "$WORKDIR/wiretap_relay.conf" >/dev/null 2>&1
  fi
  ip netns del "$CALLER_NS" 2>/dev/null
  ip netns del "$CALLEE_NS" 2>/dev/null
  ip link del baudot-underlay-host 2>/dev/null
  ip link del baudot-sig-host 2>/dev/null
  ip link del baudot-media-host 2>/dev/null
  rm -rf "$WORKDIR"
  if [[ -n "${SUDO_UID:-}" && -d "$EVIDENCE_ROOT" ]]; then
    chown -R "${SUDO_UID}:${SUDO_GID}" "$EVIDENCE_ROOT" 2>/dev/null || true
  fi
}
trap cleanup EXIT

command -v "$WIRETAP_BIN" >/dev/null
command -v ip >/dev/null
command -v wg-quick >/dev/null
command -v java >/dev/null
command -v mvn >/dev/null

rm -rf "$WORKDIR"
mkdir -p "$WORKDIR" "$EVIDENCE_ROOT"

# Build before entering namespaces: the isolated caller intentionally has no
# default Internet route, so every Maven dependency must already be local.
cd "$ROOT"
mvn -q -DskipTests compile dependency:build-classpath \
  -Dmdep.outputFile=target/baudot-runtime-classpath.txt
CLASSPATH="$ROOT/target/classes:$(cat "$ROOT/target/baudot-runtime-classpath.txt")"

# Underlay: only the host and Wiretap client can reach one another here.
ip netns add "$CALLER_NS"
ip netns add "$CALLEE_NS"
ip -n "$CALLER_NS" link set lo up
ip -n "$CALLEE_NS" link set lo up

ip link add baudot-underlay-host type veth peer name baudot-underlay-client
ip link set baudot-underlay-client netns "$CALLER_NS"
ip addr add "$HOST_UNDERLAY/24" dev baudot-underlay-host
ip link set baudot-underlay-host up
ip -n "$CALLER_NS" addr add "$CALLER_UNDERLAY/24" dev baudot-underlay-client
ip -n "$CALLER_NS" link set baudot-underlay-client up

# The caller advertises the address exposed back through Wiretap. The duplicate
# address is safe because it exists in a separate network namespace.
ip -n "$CALLER_NS" addr add "$CALLER_SIP_IP/32" dev lo

# Destination side has distinct signaling and media networks. This separation
# is what lets scenario 002 keep SIP healthy while withholding the media route.
ip link add baudot-sig-host type veth peer name baudot-sig-callee
ip link set baudot-sig-callee netns "$CALLEE_NS"
ip addr add "$CALLER_SIP_IP/24" dev baudot-sig-host
ip link set baudot-sig-host up
ip -n "$CALLEE_NS" addr add "$CALLEE_SIP_IP/24" dev baudot-sig-callee
ip -n "$CALLEE_NS" link set baudot-sig-callee up

ip link add baudot-media-host type veth peer name baudot-media-callee
ip link set baudot-media-callee netns "$CALLEE_NS"
ip addr add "$HOST_MEDIA_IP/24" dev baudot-media-host
ip link set baudot-media-host up
ip -n "$CALLEE_NS" addr add "$CALLEE_MEDIA_IP/24" dev baudot-media-callee
ip -n "$CALLEE_NS" link set baudot-media-callee up

routes="$SIGNALING_CIDR"
if [[ "$scenario" == "001" ]]; then
  routes="$SIGNALING_CIDR,$MEDIA_CIDR"
else
  # Prevent Linux from falling back to any future default route while still
  # allowing UDP send() to complete: the packet is emitted into an isolated
  # dummy network and never reaches the callee.
  ip -n "$CALLER_NS" link add baudot-media-drop type dummy
  ip -n "$CALLER_NS" link set baudot-media-drop up
  ip -n "$CALLER_NS" route add "$MEDIA_CIDR" dev baudot-media-drop
fi

cd "$WORKDIR"
"$WIRETAP_BIN" configure \
  --endpoint "$CALLER_UNDERLAY:$WIRETAP_PORT" \
  --routes "$routes" \
  --port "$WIRETAP_PORT" \
  >configure.log

ip netns exec "$CALLER_NS" wg-quick up "$WORKDIR/wiretap_relay.conf"
relay_up=1
ip netns exec "$CALLER_NS" wg-quick up "$WORKDIR/wiretap.conf"
e2ee_up=1

"$WIRETAP_BIN" serve -f "$WORKDIR/wiretap_server.conf" >server.log 2>&1 &
server_pid=$!

for _ in $(seq 1 100); do
  if ip netns exec "$CALLER_NS" "$WIRETAP_BIN" ping >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$server_pid" 2>/dev/null; then
    cat server.log >&2
    exit 1
  fi
  sleep 0.1
done
if ! ip netns exec "$CALLER_NS" "$WIRETAP_BIN" ping >/dev/null 2>&1; then
  echo "Wiretap API did not become reachable" >&2
  cat server.log >&2
  exit 1
fi

# SIP 200/ACK traffic is a new UDP flow in the reverse direction because SIP
# carries an explicit Via. Expose the caller listener on the Wiretap server so
# the complete dialog still crosses the controlled path.
ip netns exec "$CALLER_NS" "$WIRETAP_BIN" expose \
  --local "$SIP_PORT" \
  --remote "$SIP_PORT" \
  --protocol udp >/dev/null

export BAUDOT_SCENARIO="00${scenario#0}-wiretap-routed"
export BAUDOT_CORRELATION="$CORRELATION"
export BAUDOT_EVIDENCE_DIR="$EVIDENCE_ROOT"
export BAUDOT_CALLER_SIP_IP="$CALLER_SIP_IP"
export BAUDOT_CALLER_SIP_PORT="$SIP_PORT"
export BAUDOT_CALLEE_SIP_BIND_IP="$CALLEE_SIP_IP"
export BAUDOT_CALLEE_SIP_IP="$CALLEE_SIP_IP"
export BAUDOT_CALLEE_SIP_PORT="$CALLEE_SIP_PORT"
export BAUDOT_MEDIA_BIND_IP="$CALLEE_MEDIA_IP"
export BAUDOT_MEDIA_BIND_PORT="$MEDIA_PORT"
export BAUDOT_MEDIA_TARGET_IP="$CALLEE_MEDIA_IP"
export BAUDOT_MEDIA_TARGET_PORT="$MEDIA_PORT"
export BAUDOT_EXPECT_MEDIA=$([[ "$scenario" == "001" ]] && echo true || echo false)
export BAUDOT_TIMEOUT_MS=5000

run_root="$EVIDENCE_ROOT/$BAUDOT_SCENARIO/$CORRELATION"
mkdir -p "$run_root"
cat >"$run_root/topology.properties" <<EOF
wiretap.version=$($WIRETAP_BIN --version 2>/dev/null | head -n1)
wiretap.routes=$routes
underlay=$HOST_UNDERLAY/24<->$CALLER_UNDERLAY/24
signaling=$CALLER_SIP_IP/24<->$CALLEE_SIP_IP/24
media=$HOST_MEDIA_IP/24<->$CALLEE_MEDIA_IP/24
scenario.expectMedia=$BAUDOT_EXPECT_MEDIA
EOF
ip netns exec "$CALLER_NS" ip route show >"$run_root/caller-routes.txt"
ip netns exec "$CALLEE_NS" ip route show >"$run_root/callee-routes.txt"
ip netns exec "$CALLER_NS" "$WIRETAP_BIN" status >"$run_root/wiretap-status.txt"

callee_log="$run_root/callee.log"
ip netns exec "$CALLEE_NS" env \
  BAUDOT_ROLE=callee \
  BAUDOT_SCENARIO="$BAUDOT_SCENARIO" \
  BAUDOT_CORRELATION="$CORRELATION" \
  BAUDOT_EVIDENCE_DIR="$EVIDENCE_ROOT" \
  BAUDOT_CALLER_SIP_IP="$CALLER_SIP_IP" \
  BAUDOT_CALLER_SIP_PORT="$SIP_PORT" \
  BAUDOT_CALLEE_SIP_BIND_IP="$CALLEE_SIP_IP" \
  BAUDOT_CALLEE_SIP_IP="$CALLEE_SIP_IP" \
  BAUDOT_CALLEE_SIP_PORT="$CALLEE_SIP_PORT" \
  BAUDOT_MEDIA_BIND_IP="$CALLEE_MEDIA_IP" \
  BAUDOT_MEDIA_BIND_PORT="$MEDIA_PORT" \
  BAUDOT_MEDIA_TARGET_IP="$CALLEE_MEDIA_IP" \
  BAUDOT_MEDIA_TARGET_PORT="$MEDIA_PORT" \
  BAUDOT_EXPECT_MEDIA="$BAUDOT_EXPECT_MEDIA" \
  BAUDOT_TIMEOUT_MS=5000 \
  java -cp "$CLASSPATH" org.mcc0nnell.baudot.harness.BaudotProbe \
  >"$callee_log" 2>&1 &
callee_pid=$!

callee_events="$run_root/callee/events.jsonl"
for _ in $(seq 1 100); do
  if [[ -f "$callee_events" ]] && grep -q 'sip.endpoint.ready' "$callee_events"; then
    break
  fi
  if ! kill -0 "$callee_pid" 2>/dev/null; then
    cat "$callee_log" >&2
    exit 1
  fi
  sleep 0.1
done
if [[ ! -f "$callee_events" ]] || ! grep -q 'sip.endpoint.ready' "$callee_events"; then
  echo "callee did not become ready" >&2
  cat "$callee_log" >&2
  exit 1
fi

ip netns exec "$CALLER_NS" env \
  BAUDOT_ROLE=caller \
  BAUDOT_SCENARIO="$BAUDOT_SCENARIO" \
  BAUDOT_CORRELATION="$CORRELATION" \
  BAUDOT_EVIDENCE_DIR="$EVIDENCE_ROOT" \
  BAUDOT_CALLER_SIP_IP="$CALLER_SIP_IP" \
  BAUDOT_CALLER_SIP_PORT="$SIP_PORT" \
  BAUDOT_CALLEE_SIP_BIND_IP="$CALLEE_SIP_IP" \
  BAUDOT_CALLEE_SIP_IP="$CALLEE_SIP_IP" \
  BAUDOT_CALLEE_SIP_PORT="$CALLEE_SIP_PORT" \
  BAUDOT_MEDIA_BIND_IP="$CALLEE_MEDIA_IP" \
  BAUDOT_MEDIA_BIND_PORT="$MEDIA_PORT" \
  BAUDOT_MEDIA_TARGET_IP="$CALLEE_MEDIA_IP" \
  BAUDOT_MEDIA_TARGET_PORT="$MEDIA_PORT" \
  BAUDOT_EXPECT_MEDIA="$BAUDOT_EXPECT_MEDIA" \
  BAUDOT_TIMEOUT_MS=5000 \
  java -cp "$CLASSPATH" org.mcc0nnell.baudot.harness.BaudotProbe

wait "$callee_pid"
callee_pid=""

java -cp "$CLASSPATH" org.mcc0nnell.baudot.harness.EvidenceAggregator \
  "$run_root/caller" "$run_root/callee"

(
  cd "$run_root"
  sha256sum \
    topology.properties \
    caller-routes.txt \
    callee-routes.txt \
    wiretap-status.txt \
    caller/manifest.sha256 \
    callee/manifest.sha256 \
    aggregate/manifest.sha256 \
    >bundle.manifest.sha256
)

echo "routed evidence: $run_root/aggregate/result.json"
cat "$run_root/aggregate/result.json"
