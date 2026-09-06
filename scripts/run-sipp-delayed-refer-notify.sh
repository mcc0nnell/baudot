#!/usr/bin/env bash
set -euo pipefail

: "${SIPP_BIN:?set SIPP_BIN to the exact admitted SIPp executable}"

EVIDENCE_ROOT="target/evidence"
CORRELATION_ROOT="$EVIDENCE_ROOT/BAUDOT-INTEROP-004/sipp-hostile-002-jain-v1"
TARGET_ROOT="$CORRELATION_ROOT/jain-referrer-target"
RUN_ROOT="$CORRELATION_ROOT/sipp-run"
TRACE="$RUN_ROOT/sipp-messages.log"
ERROR_LOG="$RUN_ROOT/sipp-errors.log"
TARGET_RESULT="$TARGET_ROOT/result.properties"
TERMINAL="$RUN_ROOT/terminal.json"
SCENARIO_XML="interop/sipp/scenarios/delayed-refer-notify-uas.xml"

rm -rf "$CORRELATION_ROOT"
mkdir -p "$RUN_ROOT"
: > "$ERROR_LOG"

mvn -B -ntp -q compile

set +e
timeout --signal=TERM --kill-after=3s 20s \
  "$SIPP_BIN" \
  -sf "$SCENARIO_XML" \
  -i 127.0.0.1 \
  -p 5092 \
  -m 1 \
  -l 1 \
  -trace_msg \
  -message_file "$TRACE" \
  -trace_err \
  -error_file "$ERROR_LOG" \
  -timeout 10 \
  -timeout_error \
  >"$RUN_ROOT/sipp.stdout" \
  2>"$RUN_ROOT/sipp.stderr" &
SIPP_PID=$!
set -e

cleanup() {
  if kill -0 "$SIPP_PID" 2>/dev/null; then
    kill "$SIPP_PID" 2>/dev/null || true
    wait "$SIPP_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

ready=false
for _ in $(seq 1 100); do
  if ss -H -lun 2>/dev/null | grep -q ':5092 '; then
    ready=true
    break
  fi
  if ! kill -0 "$SIPP_PID" 2>/dev/null; then
    break
  fi
  sleep 0.1
done

if [[ "$ready" != "true" ]]; then
  echo "SIPp delayed-NOTIFY UAS did not bind UDP 5092" >&2
  cat "$RUN_ROOT/sipp.stdout" >&2 || true
  cat "$RUN_ROOT/sipp.stderr" >&2 || true
  cat "$ERROR_LOG" >&2 || true
  exit 1
fi

set +e
BAUDOT_EVIDENCE_DIR="$EVIDENCE_ROOT" \
  timeout --signal=TERM --kill-after=5s 25s \
  mvn -B -ntp -q \
  -Dexec.mainClass=org.mcc0nnell.baudot.harness.SippDelayedReferNotifyTarget \
  exec:java \
  >"$RUN_ROOT/jain-target.stdout" \
  2>"$RUN_ROOT/jain-target.stderr"
TARGET_STATUS=$?

wait "$SIPP_PID"
SIPP_STATUS=$?
set -e
trap - EXIT

printf '%s\n' "$SIPP_STATUS" > "$RUN_ROOT/sipp.exit"
printf '%s\n' "$TARGET_STATUS" > "$RUN_ROOT/jain-target.exit"

if [[ "$SIPP_STATUS" -ne 0 ]]; then
  echo "SIPp delayed REFER/NOTIFY scenario failed with exit $SIPP_STATUS" >&2
  cat "$RUN_ROOT/sipp.stdout" >&2 || true
  cat "$RUN_ROOT/sipp.stderr" >&2 || true
  cat "$ERROR_LOG" >&2 || true
  exit "$SIPP_STATUS"
fi

if [[ "$TARGET_STATUS" -ne 0 ]]; then
  echo "JAIN delayed REFER/NOTIFY target failed with exit $TARGET_STATUS" >&2
  cat "$RUN_ROOT/jain-target.stdout" >&2 || true
  cat "$RUN_ROOT/jain-target.stderr" >&2 || true
  exit "$TARGET_STATUS"
fi

python3 scripts/validate_sipp_delayed_refer_notify.py \
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
