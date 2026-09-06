#!/usr/bin/env bash
set -euo pipefail

ACE_SOURCE="${1:-${ACE_CONNECT_LITE_SOURCE:-}}"
ACE_COMMIT="da74e6450193be1456ce2cdf65dd5ffdf0e92f1e"

if [[ -z "${ACE_SOURCE}" || ! -d "${ACE_SOURCE}" ]]; then
  echo "usage: $0 /path/to/mitrefccace/aceconnectlite" >&2
  exit 64
fi

if command -v git >/dev/null 2>&1 && [[ -d "${ACE_SOURCE}/.git" ]]; then
  ACTUAL_COMMIT="$(git -C "${ACE_SOURCE}" rev-parse HEAD)"
  if [[ "${ACTUAL_COMMIT}" != "${ACE_COMMIT}" ]]; then
    echo "ACE source must be pinned to ${ACE_COMMIT}; found ${ACTUAL_COMMIT}" >&2
    exit 65
  fi
fi

grep -F '/vrsverify/?vrsnum=' "${ACE_SOURCE}/server.js" >/dev/null
grep -F "data2.message === 'success'" "${ACE_SOURCE}/server.js" >/dev/null
grep -F '"vrscheck"' "${ACE_SOURCE}/config.json_TEMPLATE" >/dev/null

if [[ ! -d "${ACE_SOURCE}/node_modules" ]]; then
  echo "Installing pinned ACE Connect Lite npm dependencies..." >&2
  (cd "${ACE_SOURCE}" && npm install --no-audit --no-fund --legacy-peer-deps)
fi

CTE_PORT="${ITRS_CTE_PORT:-8800}"
ADAPTER_A_PORT="${ACE_ADAPTER_A_PORT:-8801}"
ADAPTER_B_PORT="${ACE_ADAPTER_B_PORT:-8802}"
ACE_A_PORT="${ACE_A_PORT:-8831}"
ACE_B_PORT="${ACE_B_PORT:-8832}"
AGENT_PORT="${ACE_AGENT_STUB_PORT:-8840}"
AMI_A_PORT="${ACE_AMI_A_PORT:-5038}"
AMI_B_PORT="${ACE_AMI_B_PORT:-5039}"

WORK_DIR="${ACE_RUNTIME_WORK_DIR:-${TMPDIR:-/tmp}/baudot-dual-ace-runtime}"
TRACE_DIR="${WORK_DIR}/traces"
A_DIR="${WORK_DIR}/ace-a"
B_DIR="${WORK_DIR}/ace-b"
LOG_DIR="${WORK_DIR}/logs"
rm -rf "${WORK_DIR}"
mkdir -p "${TRACE_DIR}" "${A_DIR}/logs" "${B_DIR}/logs" "${LOG_DIR}"

cleanup() {
  for pid in \
    "${ACE_B_PID:-}" "${ACE_A_PID:-}" \
    "${ADAPTER_B_PID:-}" "${ADAPTER_A_PID:-}" \
    "${CTE_PID:-}" "${SUPPORT_PID:-}"; do
    if [[ -n "${pid}" ]]; then
      kill "${pid}" 2>/dev/null || true
      wait "${pid}" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT

python3 scripts/generate_ace_runtime_config.py \
  --output "${A_DIR}/config.json" \
  --http-port "${ACE_A_PORT}" \
  --ami-port "${AMI_A_PORT}" \
  --adapter-port "${ADAPTER_A_PORT}" \
  --agent-port "${AGENT_PORT}"

python3 scripts/generate_ace_runtime_config.py \
  --output "${B_DIR}/config.json" \
  --http-port "${ACE_B_PORT}" \
  --ami-port "${AMI_B_PORT}" \
  --adapter-port "${ADAPTER_B_PORT}" \
  --agent-port "${AGENT_PORT}"

python3 scripts/ace_runtime_support.py \
  --agent-port "${AGENT_PORT}" \
  --ami-a-port "${AMI_A_PORT}" \
  --ami-b-port "${AMI_B_PORT}" \
  --trace-dir "${TRACE_DIR}" >"${LOG_DIR}/support.log" 2>&1 &
SUPPORT_PID=$!

for _ in $(seq 1 40); do
  if curl --fail --silent "http://127.0.0.1:${AGENT_PORT}/health" >/dev/null; then break; fi
  if ! kill -0 "${SUPPORT_PID}" 2>/dev/null; then cat "${LOG_DIR}/support.log" >&2; exit 1; fi
  sleep 0.25
done
curl --fail --silent "http://127.0.0.1:${AGENT_PORT}/health" >/dev/null || {
  cat "${LOG_DIR}/support.log" >&2
  exit 1
}

mvn -q -DskipTests compile

java -cp target/classes org.mcc0nnell.baudot.itrs.ItrsCteMockServer "${CTE_PORT}" \
  >"${LOG_DIR}/cte.log" 2>&1 &
CTE_PID=$!

for _ in $(seq 1 40); do
  if curl --fail --silent "http://127.0.0.1:${CTE_PORT}/health" >/dev/null; then break; fi
  if ! kill -0 "${CTE_PID}" 2>/dev/null; then cat "${LOG_DIR}/cte.log" >&2; exit 1; fi
  sleep 0.25
done
curl --fail --silent "http://127.0.0.1:${CTE_PORT}/health" >/dev/null || {
  cat "${LOG_DIR}/cte.log" >&2
  exit 1
}

java -cp target/classes org.mcc0nnell.baudot.itrs.AceConnectLiteVrsVerifyAdapter \
  "${ADAPTER_A_PORT}" "http://127.0.0.1:${CTE_PORT}" >"${LOG_DIR}/adapter-a.log" 2>&1 &
ADAPTER_A_PID=$!

java -cp target/classes org.mcc0nnell.baudot.itrs.AceConnectLiteVrsVerifyAdapter \
  "${ADAPTER_B_PORT}" "http://127.0.0.1:${CTE_PORT}" >"${LOG_DIR}/adapter-b.log" 2>&1 &
ADAPTER_B_PID=$!

for port in "${ADAPTER_A_PORT}" "${ADAPTER_B_PORT}"; do
  for _ in $(seq 1 40); do
    if curl --fail --silent "http://127.0.0.1:${port}/health" >/dev/null; then break; fi
    sleep 0.25
  done
  curl --fail --silent "http://127.0.0.1:${port}/health" >/dev/null || {
    cat "${LOG_DIR}/adapter-a.log" >&2 || true
    cat "${LOG_DIR}/adapter-b.log" >&2 || true
    exit 1
  }
done

(
  cd "${A_DIR}"
  node "${ACE_SOURCE}/server.js"
) >"${LOG_DIR}/ace-a.log" 2>&1 &
ACE_A_PID=$!

(
  cd "${B_DIR}"
  node "${ACE_SOURCE}/server.js"
) >"${LOG_DIR}/ace-b.log" 2>&1 &
ACE_B_PID=$!

for port in "${ACE_A_PORT}" "${ACE_B_PORT}"; do
  for _ in $(seq 1 80); do
    if curl --fail --silent "http://127.0.0.1:${port}/api/config" >/dev/null; then break; fi
    sleep 0.25
  done
  curl --fail --silent "http://127.0.0.1:${port}/api/config" >/dev/null || {
    cat "${LOG_DIR}/ace-a.log" >&2 || true
    cat "${LOG_DIR}/ace-b.log" >&2 || true
    exit 1
  }
done

login() {
  local port="$1"
  local username="$2"
  curl --fail --silent \
    -H 'Content-Type: application/json' \
    -X POST \
    -d "{\"username\":\"${username}\",\"password\":\"test\"}" \
    "http://127.0.0.1:${port}/login" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])'
}

TOKEN_A="$(login "${ACE_A_PORT}" "provider-a-agent")"
TOKEN_B="$(login "${ACE_B_PORT}" "provider-b-agent")"

NODE_PATH="${ACE_SOURCE}/node_modules" node scripts/ace_runtime_drive.js \
  "${ACE_A_PORT}" "${TOKEN_A}" "provider-a-agent" "2025550103"

NODE_PATH="${ACE_SOURCE}/node_modules" node scripts/ace_runtime_drive.js \
  "${ACE_B_PORT}" "${TOKEN_B}" "provider-b-agent" "2025550101"

NODE_PATH="${ACE_SOURCE}/node_modules" node scripts/ace_runtime_drive.js \
  "${ACE_A_PORT}" "${TOKEN_A}" "provider-a-agent" "2025550105"

sleep 1

python3 scripts/assert_dual_ace_runtime.py \
  --trace-dir "${TRACE_DIR}" \
  --adapter-a "http://127.0.0.1:${ADAPTER_A_PORT}" \
  --adapter-b "http://127.0.0.1:${ADAPTER_B_PORT}" \
  --ace-a "http://127.0.0.1:${ACE_A_PORT}" \
  --ace-b "http://127.0.0.1:${ACE_B_PORT}" \
  --adapter-a-port "${ADAPTER_A_PORT}" \
  --adapter-b-port "${ADAPTER_B_PORT}"

echo "Evidence:"
echo "  ACE A log: ${LOG_DIR}/ace-a.log"
echo "  ACE B log: ${LOG_DIR}/ace-b.log"
echo "  AMI traces: ${TRACE_DIR}"
