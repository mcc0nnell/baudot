#!/usr/bin/env bash
set -euo pipefail

rm -rf target/evidence/BAUDOT-INTEROP-004/jain-live-refer-v1

timeout --signal=TERM --kill-after=5s 40s \
  mvn -B -ntp -q \
  -Dexec.mainClass=org.mcc0nnell.baudot.harness.LiveReferProviderTransferProbe \
  exec:java

cat target/evidence/BAUDOT-INTEROP-004/jain-live-refer-v1/live-refer-transfer/result.properties
