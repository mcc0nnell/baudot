#!/usr/bin/env bash
set -euo pipefail

rm -rf target/evidence/BAUDOT-INTEROP-003

mvn -B -ntp -q \
  -Dexec.mainClass=org.mcc0nnell.baudot.harness.ReinviteCorrelationProbe \
  exec:java

cat target/evidence/BAUDOT-INTEROP-003/jain-message-correlation-v1/jain-message-proof/result.properties
