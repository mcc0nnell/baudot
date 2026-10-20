#!/usr/bin/env bash
set -euo pipefail

selection="${BAUDOT_PROVIDER_SELECTION:-target/evidence/RUE-PROV-001/provider-b-selection.json}"
if [[ ! -f "$selection" ]]; then
  echo "missing RUE provider-selection evidence: $selection" >&2
  exit 1
fi

selected_domain="$(python - "$selection" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
value = json.loads(path.read_text(encoding="utf-8"))
if value.get("schema") != "baudot.rue-provider-selection@1":
    raise SystemExit("unexpected provider-selection schema")
if value.get("claim") != "synthetic-provider-selection-only":
    raise SystemExit("provider-selection claim boundary drift")
entry = value.get("providerEntryPoint")
if not isinstance(entry, str) or not entry:
    raise SystemExit("missing providerEntryPoint")
print(entry)
PY
)"

# The current Java route probe is intentionally a single pinned Provider-B arm.
# Selection evidence is therefore a fail-closed execution gate: a different
# selected provider must not silently run the Provider-B route. A later matrix
# expansion can parameterize the live peer while preserving this invariant.
if [[ "$selected_domain" != "provider-b.example" ]]; then
  echo "RUE-DIAL-001 route arm does not match selected provider: $selected_domain" >&2
  exit 1
fi

rm -rf target/evidence/RUE-DIAL-001/jain-one-stage-dial-around-v1

timeout --signal=TERM --kill-after=5s 45s \
  mvn -B -ntp -q \
  -Dexec.mainClass=org.mcc0nnell.baudot.harness.RueOneStageDialAroundProbe \
  exec:java

cat target/evidence/RUE-DIAL-001/jain-one-stage-dial-around-v1/route-proof/result.properties
