#!/usr/bin/env bash
set -euo pipefail

rm -rf target/evidence/BAUDOT-INTEROP-003/jain-live-overlap-v1

timeout --signal=TERM --kill-after=5s 30s \
  mvn -B -ntp -q \
  -Dexec.mainClass=org.mcc0nnell.baudot.harness.LiveReinviteOverlapProbe \
  exec:java

cat target/evidence/BAUDOT-INTEROP-003/jain-live-overlap-v1/live-overlap/result.properties
