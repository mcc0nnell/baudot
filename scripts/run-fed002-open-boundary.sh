#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CORRELATION="${BAUDOT_CORRELATION:-fed002-open-boundary}"
EVIDENCE_DIR="${BAUDOT_EVIDENCE_DIR:-target/evidence/fed002}"
CALLER_PORT="${BAUDOT_CALLER_SIP_PORT:-5270}"
INTERPRETER_PORT="${BAUDOT_CALLEE_SIP_PORT:-5280}"
MEDIA_PORT="${BAUDOT_MEDIA_TARGET_PORT:-43000}"

mkdir -p "$EVIDENCE_DIR"

mvn -q -DskipTests package

common_env=(
  "BAUDOT_SCENARIO=BAUDOT-FED-002"
  "BAUDOT_CORRELATION=$CORRELATION"
  "BAUDOT_CALLER_SIP_IP=127.0.0.1"
  "BAUDOT_CALLER_SIP_PORT=$CALLER_PORT"
  "BAUDOT_CALLEE_SIP_BIND_IP=127.0.0.1"
  "BAUDOT_CALLEE_SIP_IP=127.0.0.1"
  "BAUDOT_CALLEE_SIP_PORT=$INTERPRETER_PORT"
  "BAUDOT_MEDIA_BIND_IP=127.0.0.1"
  "BAUDOT_MEDIA_BIND_PORT=$MEDIA_PORT"
  "BAUDOT_MEDIA_TARGET_IP=127.0.0.1"
  "BAUDOT_MEDIA_TARGET_PORT=$MEDIA_PORT"
  "BAUDOT_EXPECT_MEDIA=true"
  "BAUDOT_TIMEOUT_MS=7000"
  "BAUDOT_EVIDENCE_DIR=$EVIDENCE_DIR"
)

(
  env "${common_env[@]}" BAUDOT_ROLE=callee \
    mvn -q -Dexec.mainClass=org.mcc0nnell.baudot.harness.BaudotProbe exec:java
) &
interpreter_pid=$!

cleanup() {
  if kill -0 "$interpreter_pid" 2>/dev/null; then
    kill "$interpreter_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

sleep 1

set +e
env "${common_env[@]}" BAUDOT_ROLE=caller \
  mvn -q -Dexec.mainClass=org.mcc0nnell.baudot.harness.BaudotProbe exec:java
caller_status=$?
wait "$interpreter_pid"
interpreter_status=$?
set -e

trap - EXIT

if [[ "$caller_status" -ne 0 || "$interpreter_status" -ne 0 ]]; then
  echo "BAUDOT-FED-002 live SIP gate failed: caller=$caller_status interpreter=$interpreter_status" >&2
  exit 2
fi

python3 -m scripts.run_federation_boundary \
  --arm control \
  --live-evidence-root "$EVIDENCE_DIR" \
  --correlation "$CORRELATION" \
  --output "$EVIDENCE_DIR/federation-boundary-result.json"

echo "BAUDOT-FED-002 RUNNABLE_PASS: live SIP evidence + interpreter readiness + RFC8865 reference boundary"
