#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CORRELATION="${BAUDOT_CORRELATION:-fed004-red-loss-recovery}"
EVIDENCE_DIR="${BAUDOT_EVIDENCE_DIR:-target/evidence/fed004}"
CALLER_PORT="${BAUDOT_CALLER_SIP_PORT:-5490}"
INTERPRETER_PORT="${BAUDOT_CALLEE_SIP_PORT:-5500}"
INTERPRETER_MEDIA_PORT="${BAUDOT_MEDIA_BIND_PORT:-47100}"
GATEWAY_MEDIA_PORT="${BAUDOT_GATEWAY_BIND_PORT:-48100}"
MEDIA_SOURCE_PORT="${BAUDOT_MEDIA_SOURCE_PORT:-47101}"
READY_FILE="$EVIDENCE_DIR/gateway/ready.json"

rm -rf "$EVIDENCE_DIR"
mkdir -p "$EVIDENCE_DIR/gateway"

mvn -q -DskipTests package

BAUDOT_GATEWAY_BIND_IP=127.0.0.1 \
BAUDOT_GATEWAY_BIND_PORT="$GATEWAY_MEDIA_PORT" \
BAUDOT_GATEWAY_FORWARD_IP=127.0.0.1 \
BAUDOT_GATEWAY_FORWARD_PORT="$INTERPRETER_MEDIA_PORT" \
BAUDOT_GATEWAY_EXPECT_DATAGRAMS=2 \
BAUDOT_GATEWAY_EVIDENCE_DIR="$EVIDENCE_DIR/gateway" \
BAUDOT_GATEWAY_READY_FILE="$READY_FILE" \
node scripts/fed004-rfc2198-recovery-webrtc-gateway.mjs &
gateway_pid=$!

interpreter_pid=""
cleanup() {
  if [[ -n "$interpreter_pid" ]] && kill -0 "$interpreter_pid" 2>/dev/null; then
    kill "$interpreter_pid" 2>/dev/null || true
  fi
  if kill -0 "$gateway_pid" 2>/dev/null; then
    kill "$gateway_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

for _ in $(seq 1 150); do
  if [[ -f "$READY_FILE" ]]; then
    break
  fi
  if ! kill -0 "$gateway_pid" 2>/dev/null; then
    wait "$gateway_pid" || true
    echo "BAUDOT-FED-004 gateway exited before readiness" >&2
    exit 7
  fi
  sleep 0.1
done

if [[ ! -f "$READY_FILE" ]]; then
  echo "BAUDOT-FED-004 gateway readiness timed out" >&2
  exit 7
fi

common_env=(
  "BAUDOT_SCENARIO=BAUDOT-FED-004"
  "BAUDOT_CORRELATION=$CORRELATION"
  "BAUDOT_RTT_PROFILE=recovery"
  "BAUDOT_CALLER_SIP_IP=127.0.0.1"
  "BAUDOT_CALLER_SIP_PORT=$CALLER_PORT"
  "BAUDOT_CALLEE_SIP_BIND_IP=127.0.0.1"
  "BAUDOT_CALLEE_SIP_IP=127.0.0.1"
  "BAUDOT_CALLEE_SIP_PORT=$INTERPRETER_PORT"
  "BAUDOT_MEDIA_SOURCE_PORT=$MEDIA_SOURCE_PORT"
  "BAUDOT_MEDIA_BIND_IP=127.0.0.1"
  "BAUDOT_MEDIA_BIND_PORT=$INTERPRETER_MEDIA_PORT"
  "BAUDOT_MEDIA_TARGET_IP=127.0.0.1"
  "BAUDOT_MEDIA_TARGET_PORT=$GATEWAY_MEDIA_PORT"
  "BAUDOT_TIMEOUT_MS=9000"
  "BAUDOT_EVIDENCE_DIR=$EVIDENCE_DIR"
)

(
  env "${common_env[@]}" BAUDOT_ROLE=callee \
    mvn -q -Dexec.mainClass=org.mcc0nnell.baudot.harness.RttSipProbe exec:java
) &
interpreter_pid=$!

sleep 1

set +e
env "${common_env[@]}" BAUDOT_ROLE=caller \
  mvn -q -Dexec.mainClass=org.mcc0nnell.baudot.harness.RttSipProbe exec:java
caller_status=$?
wait "$interpreter_pid"
interpreter_status=$?
interpreter_pid=""
wait "$gateway_pid"
gateway_status=$?
set -e

trap - EXIT

if [[ "$caller_status" -ne 0 || "$interpreter_status" -ne 0 || "$gateway_status" -ne 0 ]]; then
  echo "BAUDOT-FED-004 process gate failed: caller=$caller_status interpreter=$interpreter_status gateway=$gateway_status" >&2
  exit 8
fi

python3 -m scripts.validate_fed004_recovery \
  --evidence-root "$EVIDENCE_DIR" \
  --correlation "$CORRELATION" \
  --output "$EVIDENCE_DIR/fed004-terminal-result.json"

echo "BAUDOT-FED-004 RUNNABLE_PASS: controlled RFC2198 recovery -> real WebRTC t140 preserves ABC across omitted RTP sequence 1"
