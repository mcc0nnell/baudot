#!/usr/bin/env bash
set -euo pipefail

RUN_ROOT=target/evidence/BAUDOT-INTEROP-004/jain-live-refer-rtt-v1
DIAGNOSTICS="$RUN_ROOT/diagnostics"

rm -rf "$RUN_ROOT"
mkdir -p "$DIAGNOSTICS"

# Keep producer and independent reducer failures distinguishable. The log is
# diagnostic-only evidence; the canonical arm/terminal manifests remain owned
# by EvidenceRecorder and the Python reference validator.
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
set -e

if (( producer_status != 0 || validator_status != 0 )); then
  printf 'BAUDOT-INTEROP-004 handoff gate failed: producer=%d validator=%d\n' \
    "$producer_status" "$validator_status" >&2
  exit 1
fi
