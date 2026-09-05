#!/usr/bin/env bash
set -euo pipefail

SCENARIO=TILDEN-HANDOFF-001
SELECTION_ID=sel-local-0001
EVIDENCE_ROOT=target/evidence
ROUTE_JSON="$EVIDENCE_ROOT/$SCENARIO/$SELECTION_ID/route.json"

rm -rf "$EVIDENCE_ROOT/$SCENARIO/$SELECTION_ID"
mkdir -p "$(dirname "$ROUTE_JSON")"

mvn -B -ntp -q \
  -Dexec.mainClass=org.mcc0nnell.baudot.tilden.TildenSelectionMain \
  -Dexec.args="interop/tilden/selection.selected.json $ROUTE_JSON" \
  exec:java

python3 - "$ROUTE_JSON" <<'PY'
import json, sys
route = json.load(open(sys.argv[1], encoding="utf-8"))
assert route["selectionId"] == "sel-local-0001"
assert route["selectedEndpoint"] == "sip:callee@127.0.0.1:5088;transport=udp"
PY

if mvn -B -ntp -q \
  -Dexec.mainClass=org.mcc0nnell.baudot.tilden.TildenSelectionMain \
  -Dexec.args="interop/tilden/selection.invalid.json" \
  exec:java >/dev/null 2>&1; then
  echo "expected contradictory selection to be rejected" >&2
  exit 1
fi

BAUDOT_ROLE=callee \
BAUDOT_SCENARIO="$SCENARIO" \
BAUDOT_CORRELATION="$SELECTION_ID" \
BAUDOT_CALLEE_SIP_IP=127.0.0.1 \
BAUDOT_CALLEE_SIP_BIND_IP=127.0.0.1 \
BAUDOT_CALLEE_SIP_PORT=5088 \
BAUDOT_EXPECT_MEDIA=false \
BAUDOT_TIMEOUT_MS=2500 \
BAUDOT_EVIDENCE_DIR="$EVIDENCE_ROOT" \
  mvn -B -ntp -q \
  -Dexec.mainClass=org.mcc0nnell.baudot.harness.BaudotProbe \
  exec:java >"$EVIDENCE_ROOT/$SCENARIO/$SELECTION_ID/callee.log" 2>&1 &
CALLEE_PID=$!
trap 'kill "$CALLEE_PID" 2>/dev/null || true' EXIT
sleep 1

BAUDOT_TILDEN_CALLER_IP=127.0.0.1 \
BAUDOT_TILDEN_CALLER_PORT=5087 \
BAUDOT_TIMEOUT_MS=4000 \
BAUDOT_EVIDENCE_DIR="$EVIDENCE_ROOT" \
  timeout --signal=TERM --kill-after=5s 20s \
  mvn -B -ntp -q \
  -Dexec.mainClass=org.mcc0nnell.baudot.harness.TildenSipCallMain \
  -Dexec.args="interop/tilden/selection.selected.json" \
  exec:java

wait "$CALLEE_PID"
trap - EXIT

CALLER_RESULT="$EVIDENCE_ROOT/$SCENARIO/$SELECTION_ID/caller/result.properties"
grep -q '^tilden.selection.id=sel-local-0001$' "$CALLER_RESULT"
grep -q '^tilden.selected.endpoint=sip:callee@127.0.0.1:5088;transport=udp$' "$CALLER_RESULT"
grep -q '^signaling.dialog.established=true$' "$CALLER_RESULT"

cat "$CALLER_RESULT"
