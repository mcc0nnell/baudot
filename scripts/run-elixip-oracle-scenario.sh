#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ELIXIP_ROOT=${ELIXIP_ROOT:?set ELIXIP_ROOT to a clean neutrino38/elixip checkout}
SCENARIO=${1:-$ROOT/interop/elixip/admission-smoke.exs}
CONFIG=${2:-}
EVIDENCE=${BAUDOT_EVIDENCE_DIR:-$ROOT/target/evidence-external}
RUN_ID=${BAUDOT_RUN_ID:-$(python3 -c 'import uuid; print(uuid.uuid4())')}
RUN="$EVIDENCE/elixip/$RUN_ID"

mkdir -p "$RUN"
SCENARIO=$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$SCENARIO")
ELIXIP_ROOT=$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$ELIXIP_ROOT")
if [[ -n "$CONFIG" ]]; then
  CONFIG=$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$CONFIG")
fi

admit=(
  python3 -m scripts.elixip_oracle_admission
  --elixip-root "$ELIXIP_ROOT"
  --scenario "$SCENARIO"
  --output "$RUN/admission.json"
)
[[ -n "$CONFIG" ]] && admit+=(--config "$CONFIG")
cd "$ROOT"
"${admit[@]}"

cp "$SCENARIO" "$RUN/scenario.exs"

command=(mix scenario)
[[ -n "$CONFIG" ]] && command+=(--config "$CONFIG")
command+=("$SCENARIO")

set +e
(
  cd "$ELIXIP_ROOT"
  "${command[@]}"
) >"$RUN/elixip.stdout.log" 2>"$RUN/elixip.stderr.log"
status=$?
set -e

python3 - "$RUN/result.json" "$status" <<'PY'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
status = int(sys.argv[2])
result = {
    "schema": "baudot.external-oracle-execution/v1",
    "implementation": "Elixip",
    "authority": "observation-only",
    "exitCode": status,
    "executionStatus": "SUCCESS" if status == 0 else "FAILURE",
    "terminalVerdictAuthority": False,
    "claimBoundary": "Process execution outcome only; Baudot reducers retain terminal accessibility verdict authority.",
}
path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

(
  cd "$RUN"
  sha256sum admission.json scenario.exs result.json elixip.stdout.log elixip.stderr.log >manifest.sha256
)

cat "$RUN/admission.json"
cat "$RUN/result.json"
printf 'evidence=%s\n' "$RUN"
exit "$status"
