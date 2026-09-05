#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <scenario.env>" >&2
  exit 64
fi

scenario_file=$1
if [[ ! -f "$scenario_file" ]]; then
  echo "scenario not found: $scenario_file" >&2
  exit 66
fi

set -a
# shellcheck disable=SC1090
source "$scenario_file"
set +a

export BAUDOT_CORRELATION="${BAUDOT_CORRELATION:-$(python3 - <<'PY'
import uuid
print(uuid.uuid4())
PY
)}"
export BAUDOT_EVIDENCE_DIR="${BAUDOT_EVIDENCE_DIR:-target/evidence}"

mvn -q -DskipTests compile

callee_log="target/baudot-rtt-callee-${BAUDOT_CORRELATION}.log"
BAUDOT_ROLE=callee mvn -q -DskipTests exec:java \
  -Dexec.mainClass=org.mcc0nnell.baudot.harness.RttSipProbe \
  >"$callee_log" 2>&1 &
callee_pid=$!
trap 'kill "$callee_pid" 2>/dev/null || true' EXIT

callee_events="${BAUDOT_EVIDENCE_DIR}/${BAUDOT_SCENARIO}/${BAUDOT_CORRELATION}/callee/events.jsonl"
for _ in $(seq 1 100); do
  if [[ -f "$callee_events" ]] && grep -q 'sip.endpoint.ready' "$callee_events"; then
    break
  fi
  if ! kill -0 "$callee_pid" 2>/dev/null; then
    cat "$callee_log" >&2
    exit 1
  fi
  sleep 0.1
done

if [[ ! -f "$callee_events" ]] || ! grep -q 'sip.endpoint.ready' "$callee_events"; then
  echo "RTT callee did not become ready" >&2
  cat "$callee_log" >&2
  exit 1
fi

BAUDOT_ROLE=caller mvn -q -DskipTests exec:java \
  -Dexec.mainClass=org.mcc0nnell.baudot.harness.RttSipProbe

wait "$callee_pid"
trap - EXIT

run_root="${BAUDOT_EVIDENCE_DIR}/${BAUDOT_SCENARIO}/${BAUDOT_CORRELATION}"
mvn -q -DskipTests exec:java \
  -Dexec.mainClass=org.mcc0nnell.baudot.harness.EvidenceAggregator \
  -Dexec.args="${run_root}/caller ${run_root}/callee"

python3 -m scripts.validate_wiretap_rtt --run-dir "$run_root"

echo "RTT evidence: ${run_root}/rtt-validation.json"
