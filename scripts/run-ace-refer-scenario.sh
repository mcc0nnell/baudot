#!/usr/bin/env bash
set -euo pipefail

rm -rf target/evidence/BAUDOT-INTEROP-004

python3 -m scripts.validate_refer_provider_matrix
bash scripts/run-live-refer-provider-transfer.sh
bash scripts/run-live-refer-rtt-handoff.sh
python3 -m scripts.validate_ace_refer_scenario

cat target/evidence/BAUDOT-INTEROP-004/terminal/result.json
