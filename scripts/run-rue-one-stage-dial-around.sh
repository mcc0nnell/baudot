#!/usr/bin/env bash
set -euo pipefail

rm -rf target/evidence/RUE-DIAL-001/jain-one-stage-dial-around-v1

timeout --signal=TERM --kill-after=5s 45s \
  mvn -B -ntp -q \
  -Dexec.mainClass=org.mcc0nnell.baudot.harness.RueOneStageDialAroundProbe \
  exec:java

cat target/evidence/RUE-DIAL-001/jain-one-stage-dial-around-v1/route-proof/result.properties
