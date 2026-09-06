#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PJSIP_ROOT=${PJSIP_ROOT:?set PJSIP_ROOT to the pinned clean pjsip/pjproject 2.17 checkout}
SELECTION=${BAUDOT_TILDEN_PROVIDER_SELECTION:-$ROOT/interop/tilden/selection.provider-refer-rtt.json}
EVIDENCE_ROOT=${BAUDOT_EVIDENCE_DIR:-$ROOT/target/evidence-external}
SCENARIO=TILDEN-HANDOFF-003
SELECTION_ID=$(python3 - "$SELECTION" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["selectionId"])
PY
)
OUT="$EVIDENCE_ROOT/$SCENARIO/$SELECTION_ID"
INNER_ROOT="$OUT/inner-evidence"
INNER_OUT="$INNER_ROOT/BAUDOT-INTEROP-004/jain-to-pjsip-native-handoff-v1"

for bin in git mvn python3 sha256sum; do
  command -v "$bin" >/dev/null || { echo "missing required executable: $bin" >&2; exit 2; }
done

rm -rf "$OUT"
mkdir -p "$OUT"
cp "$SELECTION" "$OUT/selection.json"

# Tilden selection is validated and reduced before any provider signaling begins.
mvn -B -ntp -q -DskipTests compile
mvn -B -ntp -q \
  -Dexec.mainClass=org.mcc0nnell.baudot.tilden.TildenSelectionMain \
  -Dexec.args="$SELECTION $OUT/route.json" \
  exec:java

# This profile deliberately selects the provider/referrer endpoint, not the replacement endpoint.
# BAUDOT-INTEROP-004 remains responsible for REFER, replacement signaling, RTT readiness, and release.
python3 - "$OUT/route.json" <<'PY'
import json, re, sys
route = json.load(open(sys.argv[1], encoding="utf-8"))
endpoint = route["selectedEndpoint"]
match = re.fullmatch(r"sip:provider-a@127\.0\.0\.1:(\d+)", endpoint)
assert match, f"unexpected selected provider profile: {endpoint}"
assert int(match.group(1)) == 5310, endpoint
PY

python3 - "$OUT/admission.json" "$OUT/selection.json" <<'PY'
import hashlib, json, pathlib, sys
out = pathlib.Path(sys.argv[1])
selection_path = pathlib.Path(sys.argv[2])
selection = json.loads(selection_path.read_text(encoding="utf-8"))
out.write_text(json.dumps({
    "scenarioId": "TILDEN-HANDOFF-003",
    "selectionId": selection["selectionId"],
    "selectedProviderEndpoint": selection["selectedEndpoint"],
    "selectionSha256": hashlib.sha256(selection_path.read_bytes()).hexdigest(),
    "innerScenario": {
        "scenarioId": "BAUDOT-INTEROP-004",
        "correlationId": "jain-to-pjsip-native-handoff-v1",
        "role": "selected-provider-transfer-and-native-rtt-proof",
    },
    "authority": {
        "routeSelection": "Tilden selection evidence",
        "providerAndTransferSignaling": "Baudot JAIN SIP BAUDOT-INTEROP-004",
        "replacementNativeMedia": "pjsip/pjproject-2.17",
        "rttSemanticReadiness": "Baudot Python RFC4103/T.140 reference",
    },
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

# Reuse the already-qualified native REFER handoff exactly as-is. Only the evidence root is nested
# under this Tilden handoff so the outer reducer can bind the selected provider to the inner proof.
BAUDOT_EVIDENCE_DIR="$INNER_ROOT" \
  PJSIP_ROOT="$PJSIP_ROOT" \
  BAUDOT_JAIN_TRANSFER_PORT=5310 \
  BAUDOT_JAIN_REFERRER_PORT=5311 \
  BAUDOT_PJSIP_UAS_PORT=5312 \
  BAUDOT_PJSIP_HANDOFF_MEDIA_PORT=5313 \
  bash "$ROOT/scripts/run-pjsip-interop004-native-handoff.sh"

(
  cd "$INNER_OUT"
  sha256sum -c bundle.manifest.sha256
)

python3 "$ROOT/scripts/validate_tilden_provider_refer_rtt_handoff.py" \
  --out "$OUT" \
  --selection "$SELECTION"

(
  cd "$OUT"
  required=(
    selection.json
    route.json
    admission.json
    terminal-result.json
    inner-evidence/BAUDOT-INTEROP-004/jain-to-pjsip-native-handoff-v1/bundle.manifest.sha256
    inner-evidence/BAUDOT-INTEROP-004/jain-to-pjsip-native-handoff-v1/jain-to-pjsip-native-handoff/original-invite.request.sip
    inner-evidence/BAUDOT-INTEROP-004/jain-to-pjsip-native-handoff-v1/jain-to-pjsip-native-handoff/terminal-result.json
    inner-evidence/BAUDOT-INTEROP-004/jain-to-pjsip-native-handoff-v1/readiness/result.json
    inner-evidence/BAUDOT-INTEROP-004/jain-to-pjsip-native-handoff-v1/readiness/rtt-ready.json
  )
  for artifact in "${required[@]}"; do test -f "$artifact"; done
  sha256sum "${required[@]}" >bundle.manifest.sha256
  sha256sum -c bundle.manifest.sha256
)

cat "$OUT/terminal-result.json"
printf 'tildenProviderReferRttEvidence=%s\n' "$OUT"
