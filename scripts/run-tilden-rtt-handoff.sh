#!/usr/bin/env bash
set -euo pipefail

SCENARIO=TILDEN-HANDOFF-002
EVIDENCE_ROOT=target/evidence
SELECTION=interop/tilden/selection.rtt.json
WORK=target/tilden-rtt-handoff
ROUTE_JSON="$WORK/route.json"
RUNTIME_ROUTE_JSON="$WORK/runtime-route.json"

rm -rf "$WORK"
mkdir -p "$WORK"

mvn -B -ntp -q \
  -Dexec.mainClass=org.mcc0nnell.baudot.tilden.TildenSelectionMain \
  -Dexec.args="$SELECTION $ROUTE_JSON" \
  exec:java

python3 -m scripts.prepare_tilden_rtt_route \
  --route "$ROUTE_JSON" \
  --output "$RUNTIME_ROUTE_JSON"

mapfile -t ROUTE_VALUES < <(python3 - "$RUNTIME_ROUTE_JSON" <<'PY'
import json, sys
route = json.load(open(sys.argv[1], encoding="utf-8"))
print(route["selectionId"])
print(route["selectedEndpoint"])
print(route["sip"]["host"])
print(route["sip"]["port"])
PY
)

SELECTION_ID=${ROUTE_VALUES[0]}
SELECTED_ENDPOINT=${ROUTE_VALUES[1]}
CALLEE_HOST=${ROUTE_VALUES[2]}
CALLEE_PORT=${ROUTE_VALUES[3]}
RUN_ROOT="$EVIDENCE_ROOT/$SCENARIO/$SELECTION_ID"

rm -rf "$RUN_ROOT"
mkdir -p "$RUN_ROOT"
cp "$ROUTE_JSON" "$RUN_ROOT/route.json"
cp "$RUNTIME_ROUTE_JSON" "$RUN_ROOT/runtime-route.json"

export BAUDOT_SCENARIO="$SCENARIO"
export BAUDOT_CORRELATION="$SELECTION_ID"
export BAUDOT_EVIDENCE_DIR="$EVIDENCE_ROOT"
export BAUDOT_RTT_PROFILE=normal
export BAUDOT_CALLER_SIP_IP=127.0.0.1
export BAUDOT_CALLER_SIP_PORT=5090
export BAUDOT_CALLEE_SIP_BIND_IP="$CALLEE_HOST"
export BAUDOT_CALLEE_SIP_IP="$CALLEE_HOST"
export BAUDOT_CALLEE_SIP_PORT="$CALLEE_PORT"
export BAUDOT_MEDIA_SOURCE_PORT=40101
export BAUDOT_MEDIA_BIND_IP="$CALLEE_HOST"
export BAUDOT_MEDIA_BIND_PORT=40100
export BAUDOT_MEDIA_TARGET_IP="$CALLEE_HOST"
export BAUDOT_MEDIA_TARGET_PORT=40100
export BAUDOT_TIMEOUT_MS=5000

CALLEE_LOG="$WORK/callee.log"
BAUDOT_ROLE=callee mvn -B -ntp -q -DskipTests \
  -Dexec.mainClass=org.mcc0nnell.baudot.harness.RttSipProbe \
  exec:java >"$CALLEE_LOG" 2>&1 &
CALLEE_PID=$!
trap 'kill "$CALLEE_PID" 2>/dev/null || true' EXIT

CALLEE_EVENTS="$RUN_ROOT/callee/events.jsonl"
for _ in $(seq 1 100); do
  if [[ -f "$CALLEE_EVENTS" ]] && grep -q 'sip.endpoint.ready' "$CALLEE_EVENTS"; then
    break
  fi
  if ! kill -0 "$CALLEE_PID" 2>/dev/null; then
    cat "$CALLEE_LOG" >&2
    exit 1
  fi
  sleep 0.1
done

if [[ ! -f "$CALLEE_EVENTS" ]] || ! grep -q 'sip.endpoint.ready' "$CALLEE_EVENTS"; then
  echo "Tilden-selected RTT callee did not become ready" >&2
  cat "$CALLEE_LOG" >&2
  exit 1
fi

BAUDOT_ROLE=caller timeout --signal=TERM --kill-after=5s 20s \
  mvn -B -ntp -q -DskipTests \
  -Dexec.mainClass=org.mcc0nnell.baudot.harness.RttSipProbe \
  exec:java

wait "$CALLEE_PID"
trap - EXIT

mvn -B -ntp -q -DskipTests \
  -Dexec.mainClass=org.mcc0nnell.baudot.harness.EvidenceAggregator \
  -Dexec.args="$RUN_ROOT/caller $RUN_ROOT/callee" \
  exec:java

python3 -m scripts.validate_wiretap_rtt --run-dir "$RUN_ROOT"
python3 -m scripts.validate_tilden_rtt_handoff \
  --route "$RUN_ROOT/route.json" \
  --runtime-route "$RUN_ROOT/runtime-route.json" \
  --run-dir "$RUN_ROOT"

python3 - "$RUN_ROOT/tilden-rtt-handoff-validation.json" "$SELECTED_ENDPOINT" <<'PY'
import json, sys
result = json.load(open(sys.argv[1], encoding="utf-8"))
assert result["runtimeClaim"] == "selected-route-rtt-ready"
assert result["selectedEndpoint"] == sys.argv[2]
assert result["rtt"]["verdict"] == "pass"
assert result["rtt"]["presentation"]["displayText"] == "Hi"
print(json.dumps(result, indent=2, sort_keys=True))
PY
