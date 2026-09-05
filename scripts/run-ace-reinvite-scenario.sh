#!/usr/bin/env bash
set -euo pipefail

bash scripts/run-reinvite-correlation-proof.sh
bash scripts/run-live-reinvite-overlap.sh
bash scripts/run-live-reinvite-rtt-readiness.sh
python3 -m scripts.validate_ace_reinvite_scenario

cat target/evidence/BAUDOT-INTEROP-003/scenario-validation.json
