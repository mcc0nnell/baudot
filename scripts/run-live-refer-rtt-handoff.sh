#!/usr/bin/env bash
set -euo pipefail

RUN_ROOT=target/evidence/BAUDOT-INTEROP-004/jain-live-refer-rtt-v1
DIAGNOSTICS="$RUN_ROOT/diagnostics"

rm -rf "$RUN_ROOT"
mkdir -p "$DIAGNOSTICS"

# Keep producer, scenario reducer, and causal-proof failures distinguishable.
# The Java log is diagnostic-only evidence; the canonical arm/terminal
# manifests remain owned by EvidenceRecorder and the Python reference reducer.
set +e
timeout --signal=TERM --kill-after=5s 45s \
  mvn -B -ntp -q \
  -Dexec.mainClass=org.mcc0nnell.baudot.harness.LiveReferRttHandoffProbe \
  exec:java \
  2>&1 | tee "$DIAGNOSTICS/java-producer.log"
producer_status=${PIPESTATUS[0]}

python3 -m scripts.validate_refer_rtt_handoff \
  2>&1 | tee "$DIAGNOSTICS/reference-validator.log"
validator_status=${PIPESTATUS[0]}

python3 -m scripts.validate_causal_proof_manifest \
  "$RUN_ROOT/terminal/causal-proof.json" \
  2>&1 | tee "$DIAGNOSTICS/causal-proof-validator.log"
proof_status=${PIPESTATUS[0]}
set -e

if (( producer_status != 0 || validator_status != 0 || proof_status != 0 )); then
  printf 'BAUDOT-INTEROP-004 handoff gate failed: producer=%d validator=%d proof=%d\n' \
    "$producer_status" "$validator_status" "$proof_status" >&2
  exit 1
fi
