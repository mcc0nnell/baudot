#!/usr/bin/env bash
set -euo pipefail

CTE_PORT="${ITRS_CTE_PORT:-8800}"
ACE_PORT="${ACE_VRSVERIFY_PORT:-8801}"
CTE_BASE="http://127.0.0.1:${CTE_PORT}"
ACE_BASE="http://127.0.0.1:${ACE_PORT}"
CTE_LOG="${TMPDIR:-/tmp}/baudot-itrs-cte-${CTE_PORT}.log"
ACE_LOG="${TMPDIR:-/tmp}/baudot-ace-vrsverify-${ACE_PORT}.log"

cleanup() {
  for pid in "${ACE_PID:-}" "${CTE_PID:-}"; do
    if [[ -n "${pid}" ]]; then
      kill "${pid}" 2>/dev/null || true
      wait "${pid}" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT

mvn -q -DskipTests compile
mvn -q -DskipTests exec:java \
  -Dexec.mainClass=org.mcc0nnell.baudot.itrs.ItrsCteMockServer \
  -Dexec.args="${CTE_PORT}" >"${CTE_LOG}" 2>&1 &
CTE_PID=$!

for _ in $(seq 1 40); do
  if curl --fail --silent "${CTE_BASE}/health" >/dev/null; then break; fi
  if ! kill -0 "${CTE_PID}" 2>/dev/null; then cat "${CTE_LOG}" >&2; exit 1; fi
  sleep 0.25
done
curl --fail --silent "${CTE_BASE}/health" >/dev/null || { cat "${CTE_LOG}" >&2; exit 1; }

mvn -q -DskipTests exec:java \
  -Dexec.mainClass=org.mcc0nnell.baudot.itrs.AceConnectLiteVrsVerifyAdapter \
  -Dexec.args="${ACE_PORT} ${CTE_BASE}" >"${ACE_LOG}" 2>&1 &
ACE_PID=$!

for _ in $(seq 1 40); do
  if curl --fail --silent "${ACE_BASE}/health" >/dev/null; then break; fi
  if ! kill -0 "${ACE_PID}" 2>/dev/null; then cat "${ACE_LOG}" >&2; exit 1; fi
  sleep 0.25
done
curl --fail --silent "${ACE_BASE}/health" >/dev/null || { cat "${ACE_LOG}" >&2; exit 1; }

mvn -q -DskipTests exec:java \
  -Dexec.mainClass=org.mcc0nnell.baudot.itrs.AceConnectLiteVrsVerifyProbe \
  -Dexec.args="${ACE_BASE}"
