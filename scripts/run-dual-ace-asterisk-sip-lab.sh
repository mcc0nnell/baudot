#!/usr/bin/env bash
set -euo pipefail

ACE_SOURCE="${1:-${ACE_CONNECT_LITE_SOURCE:-}}"
ACE_COMMIT="da74e6450193be1456ce2cdf65dd5ffdf0e92f1e"

if [[ -z "${ACE_SOURCE}" || ! -d "${ACE_SOURCE}" ]]; then
  echo "usage: $0 /path/to/mitrefccace/aceconnectlite" >&2
  exit 64
fi
if ! command -v asterisk >/dev/null 2>&1; then
  echo "asterisk binary not found; install the distro asterisk package" >&2
  exit 66
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
SIP_A_PORT="${ASTERISK_A_SIP_PORT:-5068}"
SIP_B_PORT="${ASTERISK_B_SIP_PORT:-5069}"
PEER_A_PORT="${BAUDOT_PEER_A_PORT:-5092}"
PEER_B_PORT="${BAUDOT_PEER_B_PORT:-5093}"

WORK_DIR="${ACE_ASTERISK_WORK_DIR:-${TMPDIR:-/tmp}/baudot-dual-ace-asterisk}"
TRACE_DIR="${WORK_DIR}/traces"
LOG_DIR="${WORK_DIR}/logs"
ACE_A_DIR="${WORK_DIR}/ace-a"
ACE_B_DIR="${WORK_DIR}/ace-b"
AST_A_DIR="${WORK_DIR}/asterisk-a"
AST_B_DIR="${WORK_DIR}/asterisk-b"
rm -rf "${WORK_DIR}"
mkdir -p "${TRACE_DIR}" "${LOG_DIR}" "${ACE_A_DIR}/logs" "${ACE_B_DIR}/logs"

cleanup() {
  for pid in \
    "${PEER_PID:-}" "${ACE_B_PID:-}" "${ACE_A_PID:-}" \
    "${AST_B_PID:-}" "${AST_A_PID:-}" \
    "${ADAPTER_B_PID:-}" "${ADAPTER_A_PID:-}" \
    "${CTE_PID:-}" "${AGENT_PID:-}"; do
    if [[ -n "${pid}" ]]; then
      kill "${pid}" 2>/dev/null || true
      wait "${pid}" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT

wait_http() {
  local url="$1" pid="$2" log="$3"
  for _ in $(seq 1 100); do
    if curl --fail --silent "${url}" >/dev/null; then return 0; fi
    if [[ -n "${pid}" ]] && ! kill -0 "${pid}" 2>/dev/null; then cat "${log}" >&2 || true; return 1; fi
    sleep 0.2
  done
  cat "${log}" >&2 || true
  return 1
}

wait_log() {
  local log="$1" pattern="$2" pid="$3"
  for _ in $(seq 1 100); do
    if [[ -f "${log}" ]] && grep -F "${pattern}" "${log}" >/dev/null; then return 0; fi
    if [[ -n "${pid}" ]] && ! kill -0 "${pid}" 2>/dev/null; then cat "${log}" >&2 || true; return 1; fi
    sleep 0.2
  done
  cat "${log}" >&2 || true
  return 1
}

wait_tcp() {
  local port="$1" pid="$2" log="$3"
  for _ in $(seq 1 100); do
    if python3 - "${port}" <<'PY' >/dev/null 2>&1
import socket, sys
s = socket.socket()
s.settimeout(0.15)
try:
    s.connect(("127.0.0.1", int(sys.argv[1])))
except OSError:
    raise SystemExit(1)
finally:
    s.close()
PY
    then return 0; fi
    if [[ -n "${pid}" ]] && ! kill -0 "${pid}" 2>/dev/null; then cat "${log}" >&2 || true; return 1; fi
    sleep 0.2
  done
  cat "${log}" >&2 || true
  return 1
}

AGI_SCRIPT="$(pwd)/scripts/itrs_route_agi.py"
ASTMODDIR="$(find /usr/lib -type d -path '*/asterisk/modules' -print -quit)"
if [[ -z "${ASTMODDIR}" ]]; then
  echo "could not locate Asterisk module directory" >&2
  exit 67
fi
asterisk -V | tee "${TRACE_DIR}/asterisk-version.txt"

python3 scripts/generate_ace_runtime_config.py \
  --output "${ACE_A_DIR}/config.json" --http-port "${ACE_A_PORT}" \
  --ami-port "${AMI_A_PORT}" --adapter-port "${ADAPTER_A_PORT}" --agent-port "${AGENT_PORT}"
python3 scripts/generate_ace_runtime_config.py \
  --output "${ACE_B_DIR}/config.json" --http-port "${ACE_B_PORT}" \
  --ami-port "${AMI_B_PORT}" --adapter-port "${ADAPTER_B_PORT}" --agent-port "${AGENT_PORT}"

python3 scripts/generate_asterisk_fixture.py \
  --root "${AST_A_DIR}" --name "Asterisk-A" --ami-port "${AMI_A_PORT}" --sip-port "${SIP_A_PORT}" \
  --peer-port "${PEER_A_PORT}" --agent-extension 7001 --provider-id provider-a --from-tn 2025550101 \
  --cte-base "http://127.0.0.1:${CTE_PORT}" --agi-script "${AGI_SCRIPT}" \
  --agi-trace "${TRACE_DIR}/agi-a.jsonl" --module-dir "${ASTMODDIR}" --rtp-start 10000 --rtp-end 10099
python3 scripts/generate_asterisk_fixture.py \
  --root "${AST_B_DIR}" --name "Asterisk-B" --ami-port "${AMI_B_PORT}" --sip-port "${SIP_B_PORT}" \
  --peer-port "${PEER_B_PORT}" --agent-extension 7002 --provider-id provider-b --from-tn 2025550103 \
  --cte-base "http://127.0.0.1:${CTE_PORT}" --agi-script "${AGI_SCRIPT}" \
  --agi-trace "${TRACE_DIR}/agi-b.jsonl" --module-dir "${ASTMODDIR}" --rtp-start 10100 --rtp-end 10199

python3 scripts/ace_asterisk_agent_stub.py --port "${AGENT_PORT}" >"${LOG_DIR}/agent.log" 2>&1 &
AGENT_PID=$!
wait_http "http://127.0.0.1:${AGENT_PORT}/health" "${AGENT_PID}" "${LOG_DIR}/agent.log"

mvn -q -DskipTests compile

java -cp target/classes org.mcc0nnell.baudot.itrs.ItrsCteMockServer "${CTE_PORT}" >"${LOG_DIR}/cte.log" 2>&1 &
CTE_PID=$!
wait_http "http://127.0.0.1:${CTE_PORT}/health" "${CTE_PID}" "${LOG_DIR}/cte.log"

java -cp target/classes org.mcc0nnell.baudot.itrs.AceConnectLiteVrsVerifyAdapter \
  "${ADAPTER_A_PORT}" "http://127.0.0.1:${CTE_PORT}" >"${LOG_DIR}/adapter-a.log" 2>&1 &
ADAPTER_A_PID=$!
java -cp target/classes org.mcc0nnell.baudot.itrs.AceConnectLiteVrsVerifyAdapter \
  "${ADAPTER_B_PORT}" "http://127.0.0.1:${CTE_PORT}" >"${LOG_DIR}/adapter-b.log" 2>&1 &
ADAPTER_B_PID=$!
wait_http "http://127.0.0.1:${ADAPTER_A_PORT}/health" "${ADAPTER_A_PID}" "${LOG_DIR}/adapter-a.log"
wait_http "http://127.0.0.1:${ADAPTER_B_PORT}/health" "${ADAPTER_B_PID}" "${LOG_DIR}/adapter-b.log"

asterisk -C "${AST_A_DIR}/etc/asterisk.conf" -f -g -vvv >"${LOG_DIR}/asterisk-a.log" 2>&1 &
AST_A_PID=$!
asterisk -C "${AST_B_DIR}/etc/asterisk.conf" -f -g -vvv >"${LOG_DIR}/asterisk-b.log" 2>&1 &
AST_B_PID=$!
wait_tcp "${AMI_A_PORT}" "${AST_A_PID}" "${LOG_DIR}/asterisk-a.log"
wait_tcp "${AMI_B_PORT}" "${AST_B_PID}" "${LOG_DIR}/asterisk-b.log"

(
  cd "${ACE_A_DIR}"
  node "${ACE_SOURCE}/server.js"
) >"${LOG_DIR}/ace-a.log" 2>&1 &
ACE_A_PID=$!
(
  cd "${ACE_B_DIR}"
  node "${ACE_SOURCE}/server.js"
) >"${LOG_DIR}/ace-b.log" 2>&1 &
ACE_B_PID=$!
wait_http "http://127.0.0.1:${ACE_A_PORT}/api/config" "${ACE_A_PID}" "${LOG_DIR}/ace-a.log"
wait_http "http://127.0.0.1:${ACE_B_PORT}/api/config" "${ACE_B_PID}" "${LOG_DIR}/ace-b.log"

login() {
  local port="$1" username="$2"
  curl --fail --silent -H 'Content-Type: application/json' -X POST \
    -d "{\"username\":\"${username}\",\"password\":\"test\"}" \
    "http://127.0.0.1:${port}/login" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])'
}
TOKEN_A="$(login "${ACE_A_PORT}" provider-a-agent)"
TOKEN_B="$(login "${ACE_B_PORT}" provider-b-agent)"

run_peer_and_call() {
  local peer_port="$1" expected_uri="$2" evidence="$3" ace_port="$4" token="$5" username="$6" number="$7" log="$8"
  mvn -q -DskipTests exec:java \
    -Dexec.mainClass=org.mcc0nnell.baudot.itrs.AsteriskSipEvidencePeer \
    -Dexec.args="${peer_port} ${expected_uri} ${evidence}" >"${log}" 2>&1 &
  PEER_PID=$!
  wait_log "${log}" "Asterisk JAIN-SIP evidence peer listening" "${PEER_PID}"
  NODE_PATH="${ACE_SOURCE}/node_modules" node scripts/ace_runtime_drive.js \
    "${ace_port}" "${token}" "${username}" "${number}"
  if ! wait "${PEER_PID}"; then
    cat "${log}" >&2 || true
    exit 1
  fi
  PEER_PID=""
}

run_peer_and_call "${PEER_A_PORT}" "sip:2025550103@provider-b.invalid" \
  "${TRACE_DIR}/sip-a-to-b.json" "${ACE_A_PORT}" "${TOKEN_A}" provider-a-agent 2025550103 "${LOG_DIR}/sip-a-to-b.log"
run_peer_and_call "${PEER_B_PORT}" "sip:2025550101@vrs-a.example.invalid" \
  "${TRACE_DIR}/sip-b-to-a.json" "${ACE_B_PORT}" "${TOKEN_B}" provider-b-agent 2025550101 "${LOG_DIR}/sip-b-to-a.log"

NODE_PATH="${ACE_SOURCE}/node_modules" node scripts/ace_runtime_drive.js \
  "${ACE_A_PORT}" "${TOKEN_A}" provider-a-agent 2025550105
sleep 1

python3 scripts/assert_dual_ace_asterisk_sip.py \
  --work-dir "${WORK_DIR}" \
  --adapter-a "http://127.0.0.1:${ADAPTER_A_PORT}" \
  --adapter-b "http://127.0.0.1:${ADAPTER_B_PORT}" \
  --ace-a "http://127.0.0.1:${ACE_A_PORT}" \
  --ace-b "http://127.0.0.1:${ACE_B_PORT}"

echo "Evidence directory: ${TRACE_DIR}"
