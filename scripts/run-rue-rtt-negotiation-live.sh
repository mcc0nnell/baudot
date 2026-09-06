#!/usr/bin/env bash
set -euo pipefail

root="${BAUDOT_RUE_RTT_NEGOTIATION_EVIDENCE:-target/evidence/RUE-RTT-NEGOTIATION-LIVE}"
rm -rf "$root"

timeout --signal=TERM --kill-after=5s 45s \
  mvn -B -ntp -q \
  -Dexec.mainClass=org.mcc0nnell.baudot.harness.RueRttNegotiationProbe \
  exec:java

python -m scripts.validate_rue_rtt_live_execution

cat "$root/summary.json"
