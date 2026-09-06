#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PJSIP_ROOT=${PJSIP_ROOT:?set PJSIP_ROOT to the pinned clean pjsip/pjproject 2.17 checkout}
INITIAL_SELECTION=${BAUDOT_TILDEN_INITIAL_SELECTION:-$ROOT/interop/tilden/selection.reselection-initial.json}
RECOVERY_SELECTION=${BAUDOT_TILDEN_RECOVERY_SELECTION:-$ROOT/interop/tilden/selection.reselection-recovery.json}
EVIDENCE_ROOT=${BAUDOT_EVIDENCE_DIR:-$ROOT/target/evidence-external}
SCENARIO=TILDEN-HANDOFF-004
CORRELATION=reselection-recovery-0001
OUT="$EVIDENCE_ROOT/$SCENARIO/$CORRELATION"
INITIAL_ROOT="$OUT/initial-attempt"
RECOVERY_ROOT="$OUT/recovery-attempt"
INITIAL_ID=sel-reselection-initial-0001
RECOVERY_ID=sel-reselection-recovery-0002
INITIAL_RUN="$INITIAL_ROOT/TILDEN-HANDOFF-001/$INITIAL_ID/caller"
RECOVERY_RUN="$RECOVERY_ROOT/TILDEN-HANDOFF-003/$RECOVERY_ID"
SENTINEL_PORT=5310
SENTINEL_JSON="$OUT/pre-reselection-provider-sentinel.json"
SENTINEL_READY="$OUT/pre-reselection-provider-sentinel.ready"
SENTINEL_PID=""

cleanup() {
  set +e
  if [[ -n "$SENTINEL_PID" ]]; then
    kill "$SENTINEL_PID" 2>/dev/null || true
    wait "$SENTINEL_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

for bin in java mvn python3 sha256sum ss; do
  command -v "$bin" >/dev/null || { echo "missing required executable: $bin" >&2; exit 2; }
done

rm -rf "$OUT"
mkdir -p "$OUT" "$INITIAL_ROOT" "$RECOVERY_ROOT"
cp "$INITIAL_SELECTION" "$OUT/initial-selection.json"
cp "$RECOVERY_SELECTION" "$OUT/recovery-selection.json"

mvn -B -ntp -q -DskipTests compile dependency:build-classpath \
  -Dmdep.outputFile=target/baudot-runtime-classpath.txt
CP="$ROOT/target/classes:$(cat "$ROOT/target/baudot-runtime-classpath.txt")"

# Consume only the first Tilden selection before attempt 1. The recovery selection exists as
# evidence input but is not adapted or authorized until the selected route has failed.
java -cp "$CP" org.mcc0nnell.baudot.tilden.TildenSelectionMain \
  "$INITIAL_SELECTION" "$OUT/initial-route.json"

python3 - "$OUT/initial-selection.json" "$OUT/initial-route.json" <<'PY'
import json, sys
selection = json.load(open(sys.argv[1], encoding="utf-8"))
route = json.load(open(sys.argv[2], encoding="utf-8"))
assert selection["selectionId"] == "sel-reselection-initial-0001"
assert route["selectionId"] == selection["selectionId"]
assert route["selectedEndpoint"] == "sip:unavailable@127.0.0.1:5390;transport=udp"
eligible = [c for c in selection["candidates"] if c.get("outcome") == "eligible"]
assert [c["uri"] for c in eligible] == ["sip:provider-a@127.0.0.1:5310"]
PY

# The selected dead route must actually be dead in this controlled profile.
if ss -H -lun | awk '$5 ~ /:5390$/ || $4 ~ /:5390$/ { found=1 } END { exit found ? 0 : 1 }'; then
  echo "controlled unavailable endpoint unexpectedly has a UDP listener on 5390" >&2
  exit 3
fi

# Observe the eligible-but-not-selected provider during attempt 1. Any datagram here would prove
# Baudot silently tried a route that Tilden had not selected.
python3 - "$SENTINEL_JSON" "$SENTINEL_READY" "$SENTINEL_PORT" <<'PY' &
import json, pathlib, socket, sys, time
out = pathlib.Path(sys.argv[1])
ready = pathlib.Path(sys.argv[2])
port = int(sys.argv[3])
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("127.0.0.1", port))
sock.settimeout(0.1)
ready.write_text("bound\n", encoding="utf-8")
packets = []
deadline = time.monotonic() + 2.5
while time.monotonic() < deadline:
    try:
        data, peer = sock.recvfrom(65535)
    except socket.timeout:
        continue
    packets.append({"bytes": len(data), "peer": f"{peer[0]}:{peer[1]}"})
sock.close()
out.write_text(json.dumps({
    "bind": f"127.0.0.1:{port}",
    "datagramCount": len(packets),
    "packets": packets,
    "meaning": "eligible-but-not-selected provider traffic before second Tilden selection",
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
SENTINEL_PID=$!

for _ in $(seq 1 100); do
  [[ -f "$SENTINEL_READY" ]] && break
  kill -0 "$SENTINEL_PID" 2>/dev/null || { echo "provider sentinel exited before bind" >&2; exit 4; }
  sleep .02
done
[[ -f "$SENTINEL_READY" ]] || { echo "provider sentinel did not bind UDP/$SENTINEL_PORT" >&2; exit 4; }

set +e
BAUDOT_EVIDENCE_DIR="$INITIAL_ROOT" \
BAUDOT_TIMEOUT_MS=1200 \
BAUDOT_TILDEN_CALLER_PORT=5387 \
  java -cp "$CP" org.mcc0nnell.baudot.harness.TildenSipCallMain "$INITIAL_SELECTION" \
  >"$OUT/initial.stdout.log" 2>"$OUT/initial.stderr.log"
initial_status=$?
set -e
printf '%s\n' "$initial_status" >"$OUT/initial.exit-code.txt"
[[ "$initial_status" == 3 ]] || {
  echo "initial selected route did not fail as expected: exit=$initial_status" >&2
  cat "$OUT/initial.stderr.log" >&2 || true
  exit 5
}

wait "$SENTINEL_PID"
SENTINEL_PID=""
python3 - "$SENTINEL_JSON" <<'PY'
import json, sys
sentinel = json.load(open(sys.argv[1], encoding="utf-8"))
assert sentinel["datagramCount"] == 0, sentinel
PY

# Only after the failed attempt and zero-packet sentinel observation do we consume the second
# Tilden selection. It has a new selectionId and explicitly promotes provider-a to selected.
java -cp "$CP" org.mcc0nnell.baudot.tilden.TildenSelectionMain \
  "$RECOVERY_SELECTION" "$OUT/recovery-route.json"

python3 - "$OUT/initial-selection.json" "$OUT/recovery-selection.json" \
  "$OUT/initial-route.json" "$OUT/recovery-route.json" "$OUT/reselection-authority.json" <<'PY'
import hashlib, json, pathlib, sys
initial_path, recovery_path = map(pathlib.Path, sys.argv[1:3])
initial = json.loads(initial_path.read_text(encoding="utf-8"))
recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
initial_route = json.load(open(sys.argv[3], encoding="utf-8"))
recovery_route = json.load(open(sys.argv[4], encoding="utf-8"))
assert initial["target"] == recovery["target"]
assert initial["selectionId"] != recovery["selectionId"]
assert initial_route["selectedEndpoint"] == initial["selectedEndpoint"]
assert recovery_route["selectedEndpoint"] == recovery["selectedEndpoint"]
assert recovery["selectedEndpoint"] == "sip:provider-a@127.0.0.1:5310"
initial_provider = next(c for c in initial["candidates"] if c["uri"] == recovery["selectedEndpoint"])
recovery_provider = next(c for c in recovery["candidates"] if c["uri"] == recovery["selectedEndpoint"])
failed_initial = next(c for c in recovery["candidates"] if c["uri"] == initial["selectedEndpoint"])
assert initial_provider["outcome"] == "eligible"
assert recovery_provider["outcome"] == "selected"
assert failed_initial["outcome"] == "failed"
pathlib.Path(sys.argv[5]).write_text(json.dumps({
    "scenarioId": "TILDEN-HANDOFF-004",
    "target": initial["target"],
    "initialSelectionId": initial["selectionId"],
    "initialSelectedEndpoint": initial["selectedEndpoint"],
    "recoverySelectionId": recovery["selectionId"],
    "recoverySelectedEndpoint": recovery["selectedEndpoint"],
    "initialSelectionSha256": hashlib.sha256(initial_path.read_bytes()).hexdigest(),
    "recoverySelectionSha256": hashlib.sha256(recovery_path.read_bytes()).hexdigest(),
    "authority": "second route attempt requires a distinct Tilden selection",
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

BAUDOT_TILDEN_PROVIDER_SELECTION="$RECOVERY_SELECTION" \
BAUDOT_EVIDENCE_DIR="$RECOVERY_ROOT" \
PJSIP_ROOT="$PJSIP_ROOT" \
  bash "$ROOT/scripts/run-tilden-provider-refer-rtt-handoff.sh"

python3 "$ROOT/scripts/validate_tilden_reselection_recovery.py" \
  --out "$OUT" \
  --initial-selection "$INITIAL_SELECTION" \
  --recovery-selection "$RECOVERY_SELECTION"

(
  cd "$OUT"
  required=(
    initial-selection.json
    recovery-selection.json
    initial-route.json
    recovery-route.json
    reselection-authority.json
    pre-reselection-provider-sentinel.json
    initial.exit-code.txt
    initial.stdout.log
    initial.stderr.log
    initial-attempt/TILDEN-HANDOFF-001/sel-reselection-initial-0001/caller/events.jsonl
    initial-attempt/TILDEN-HANDOFF-001/sel-reselection-initial-0001/caller/result.properties
    initial-attempt/TILDEN-HANDOFF-001/sel-reselection-initial-0001/caller/manifest.sha256
    recovery-attempt/TILDEN-HANDOFF-003/sel-reselection-recovery-0002/terminal-result.json
    recovery-attempt/TILDEN-HANDOFF-003/sel-reselection-recovery-0002/bundle.manifest.sha256
    terminal-result.json
  )
  for artifact in "${required[@]}"; do test -f "$artifact"; done
  sha256sum "${required[@]}" >bundle.manifest.sha256
  sha256sum -c bundle.manifest.sha256
)

cat "$OUT/terminal-result.json"
printf 'tildenReselectionRecoveryEvidence=%s\n' "$OUT"
