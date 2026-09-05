#!/usr/bin/env bash
set -euo pipefail

rm -rf target/evidence/BAUDOT-INTEROP-004

python3 scripts/validate_refer_provider_matrix.py
bash scripts/run-live-refer-provider-transfer.sh
bash scripts/run-live-refer-rtt-handoff.sh
python3 scripts/validate_ace_refer_scenario.py

cat target/evidence/BAUDOT-INTEROP-004/terminal/result.json
