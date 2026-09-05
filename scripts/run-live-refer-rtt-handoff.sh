#!/usr/bin/env bash
set -euo pipefail

rm -rf target/evidence/BAUDOT-INTEROP-004/jain-live-refer-rtt-v1

timeout --signal=TERM --kill-after=5s 45s \
  mvn -B -ntp -q \
  -Dexec.mainClass=org.mcc0nnell.baudot.harness.LiveReferRttHandoffProbe \
  exec:java

python3 scripts/validate_refer_rtt_handoff.py
