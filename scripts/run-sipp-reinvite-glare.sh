#!/usr/bin/env bash
set -euo pipefail

: "${SIPP_BIN:?set SIPP_BIN to the exact admitted SIPp executable}"

EVIDENCE_ROOT="target/evidence"
CORRELATION_ROOT="$EVIDENCE_ROOT/BAUDOT-INTEROP-003/sipp-hostile-004-jain-v1"
TARGET_ROOT="$CORRELATION_ROOT/sipp-glare-target"
RUN_ROOT="$CORRELATION_ROOT/sipp-run"
TRACE="$RUN_ROOT/sipp-messages.log"
ERROR_LOG="$RUN_ROOT/sipp-errors.log"
TARGET_RESULT="$TARGET_ROOT/result.properties"
TERMINAL="$RUN_ROOT/terminal.json"
SCENARIO_XML="interop/sipp/scenarios/reinvite-glare-uac.xml"

rm -rf "$CORRELATION_ROOT"
mkdir -p "$RUN_ROOT"

mvn -B -ntp -q compile

set +e
BAUDOT_EVIDENCE_DIR="$EVIDENCE_ROOT" \
  timeout --signal=TERM --kill-after=5s 25s \
  mvn -B -ntp -q \
  -Dexec.mainClass=org.mcc0nnell.baudot.harness.SippReinviteGlareTarget \
  exec:java \
  >"$RUN_ROOT/jain-target.stdout" \
  2>"$RUN_ROOT/jain-target.stderr" &
TARGET_PID=$!
set -e

cleanup() {
  if kill -0 "$TARGET_PID" 2>/dev/null; then
    kill "$TARGET_PID" 2>/dev/null || true
    wait "$TARGET_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

READY_FILE="$TARGET_ROOT/events.jsonl"
ready=false
for _ in $(seq 1 100); do
  if [[ -f "$READY_FILE" ]] && grep -q '"type":"sipp.target.ready"' "$READY_FILE"; then
    ready=true
    break
  fi
  if ! kill -0 "$TARGET_PID" 2>/dev/null; then
    break
  fi
  sleep 0.1
done

if [[ "$ready" != "true" ]]; then
  echo "JAIN SIP target did not become ready" >&2
  cat "$RUN_ROOT/jain-target.stdout" >&2 || true
  cat "$RUN_ROOT/jain-target.stderr" >&2 || true
  exit 1
fi

set +e
timeout --signal=TERM --kill-after=3s 15s \
  "$SIPP_BIN" \
  -sf "$SCENARIO_XML" \
  127.0.0.1:5090 \
  -i 127.0.0.1 \
  -p 5091 \
  -m 1 \
  -l 1 \
  -trace_msg \
  -message_file "$TRACE" \
  -trace_err \
  -error_file "$ERROR_LOG" \
  -timeout 8 \
  -timeout_error \
  >"$RUN_ROOT/sipp.stdout" \
  2>"$RUN_ROOT/sipp.stderr"
SIPP_STATUS=$?

wait "$TARGET_PID"
TARGET_STATUS=$?
set -e
trap - EXIT

printf '%s\n' "$SIPP_STATUS" > "$RUN_ROOT/sipp.exit"
printf '%s\n' "$TARGET_STATUS" > "$RUN_ROOT/jain-target.exit"

if [[ "$SIPP_STATUS" -ne 0 ]]; then
  echo "SIPp hostile glare scenario failed with exit $SIPP_STATUS" >&2
  cat "$RUN_ROOT/sipp.stdout" >&2 || true
  cat "$RUN_ROOT/sipp.stderr" >&2 || true
  cat "$ERROR_LOG" >&2 || true
  exit "$SIPP_STATUS"
fi

if [[ "$TARGET_STATUS" -ne 0 ]]; then
  echo "JAIN SIP glare target failed with exit $TARGET_STATUS" >&2
  cat "$RUN_ROOT/jain-target.stdout" >&2 || true
  cat "$RUN_ROOT/jain-target.stderr" >&2 || true
  exit "$TARGET_STATUS"
fi

python3 scripts/validate_sipp_reinvite_glare.py \
  "$TRACE" \
  "$TARGET_RESULT" \
  "$TERMINAL"

sha256sum \
  "$SCENARIO_XML" \
  "$TRACE" \
  "$ERROR_LOG" \
  "$RUN_ROOT/sipp.stdout" \
  "$RUN_ROOT/sipp.stderr" \
  "$RUN_ROOT/sipp.exit" \
  "$RUN_ROOT/jain-target.stdout" \
  "$RUN_ROOT/jain-target.stderr" \
  "$RUN_ROOT/jain-target.exit" \
  "$TARGET_RESULT" \
  "$TERMINAL" \
  > "$RUN_ROOT/manifest.sha256"

cat "$TERMINAL"
