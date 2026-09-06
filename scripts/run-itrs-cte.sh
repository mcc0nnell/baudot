#!/usr/bin/env bash
set -euo pipefail

PORT="${ITRS_CTE_PORT:-8800}"
BASE="http://127.0.0.1:${PORT}"
LOG="${TMPDIR:-/tmp}/baudot-itrs-cte-${PORT}.log"

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]]; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

mvn -q -DskipTests compile
mvn -q -DskipTests exec:java \
  -Dexec.mainClass=org.mcc0nnell.baudot.itrs.ItrsCteMockServer \
  -Dexec.args="${PORT}" >"${LOG}" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 40); do
  if curl --fail --silent "${BASE}/health" >/dev/null; then break; fi
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then cat "${LOG}" >&2; exit 1; fi
  sleep 0.25
done
curl --fail --silent "${BASE}/health" >/dev/null || { cat "${LOG}" >&2; exit 1; }

mvn -q -DskipTests exec:java \
  -Dexec.mainClass=org.mcc0nnell.baudot.itrs.ItrsCteProbe \
  -Dexec.args="${BASE}"

# Reuse the existing #40 signaling probe through the CTE compatibility bridge.
mvn -q -DskipTests exec:java \
  -Dexec.mainClass=org.mcc0nnell.baudot.itrs.ItrsSipHandoffProbe \
  -Dexec.args="${BASE}"
