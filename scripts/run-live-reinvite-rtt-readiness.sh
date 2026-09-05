#!/usr/bin/env bash
set -euo pipefail

rm -rf target/evidence/BAUDOT-INTEROP-003/jain-live-rtt-readiness-v1

timeout --signal=TERM --kill-after=5s 30s \
  mvn -B -ntp -q \
  -Dexec.mainClass=org.mcc0nnell.baudot.harness.LiveReinviteRttReadinessProbe \
  exec:java

python3 -m scripts.validate_reinvite_rtt_readiness

cat target/evidence/BAUDOT-INTEROP-003/jain-live-rtt-readiness-v1/live-rtt-readiness/rtt-readiness-validation.json
