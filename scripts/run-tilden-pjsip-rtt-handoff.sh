#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PJSIP_ROOT=${PJSIP_ROOT:?set PJSIP_ROOT to the pinned clean pjsip/pjproject 2.17 checkout}
EXPECTED_COMMIT=5a457451fa2712ba18e12b01738e8ff3af2b26fd
PJSIP_RELEASE=2.17
SELECTION=${BAUDOT_TILDEN_RTT_SELECTION:-$ROOT/interop/tilden/selection.pjsip-rtt.json}
CALLER_PORT=${BAUDOT_TILDEN_RTT_CALLER_PORT:-5321}
UAS_PORT=${BAUDOT_PJSIP_UAS_PORT:-5322}
MEDIA_PORT=${BAUDOT_TILDEN_RTT_MEDIA_PORT:-5323}
EVIDENCE_ROOT=${BAUDOT_EVIDENCE_DIR:-$ROOT/target/evidence-external}
SCENARIO=TILDEN-HANDOFF-002
SELECTION_ID=$(python3 - "$SELECTION" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["selectionId"])
PY
)
OUT="$EVIDENCE_ROOT/$SCENARIO/$SELECTION_ID"
READINESS="$OUT/readiness"
READY_FILE="$READINESS/rtt-ready.json"
COMPLETION_FILE="$OUT/pjsip-post-verdict-complete.signal"
APP_BUILD="$ROOT/target/tilden-pjsip-rtt-app"
APP="$APP_BUILD/baudot-pjsip-native-t140-uas"
GATE_PID=""
UAS_PID=""

cleanup() {
  set +e
  for pid in "$UAS_PID" "$GATE_PID"; do
    if [[ -n "$pid" ]]; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT

for bin in cmake c++ git mvn python3 sha256sum grep ss timeout; do
  command -v "$bin" >/dev/null || { echo "missing required executable: $bin" >&2; exit 2; }
done

actual_commit=$(git -C "$PJSIP_ROOT" rev-parse HEAD)
[[ "$actual_commit" == "$EXPECTED_COMMIT" ]] || {
  echo "unexpected PJSIP commit: $actual_commit" >&2
  exit 2
}
[[ -z "$(git -C "$PJSIP_ROOT" status --porcelain=v1 --untracked-files=normal)" ]] || {
  echo "PJSIP checkout must be clean" >&2
  exit 2
}
actual_release=$(git -C "$PJSIP_ROOT" describe --tags --exact-match HEAD 2>/dev/null || true)
[[ "$actual_release" == "$PJSIP_RELEASE" ]] || {
  echo "PJSIP checkout is not exact release $PJSIP_RELEASE: ${actual_release:-none}" >&2
  exit 2
}

python3 - "$SELECTION" "$UAS_PORT" <<'PY'
import json, re, sys
selection = json.load(open(sys.argv[1], encoding="utf-8"))
endpoint = selection["selectedEndpoint"]
expected_port = int(sys.argv[2])
match = re.match(r"^sip:[^@]+@127\.0\.0\.1:(\d+);transport=udp$", endpoint)
assert match, f"unexpected selected endpoint profile: {endpoint}"
assert int(match.group(1)) == expected_port, (endpoint, expected_port)
assert selection["terminal"] == "selected"
PY

rm -rf "$OUT" "$APP_BUILD"
mkdir -p "$OUT" "$READINESS"

mvn -B -ntp -q \
  -Dexec.mainClass=org.mcc0nnell.baudot.tilden.TildenSelectionMain \
  -Dexec.args="$SELECTION $OUT/route.json" \
  exec:java

uas_source="$ROOT/interop/pjsip/native_t140_uas.cpp"
python3 - "$OUT/admission.json" "$SELECTION" "$(sha256sum "$uas_source" | awk '{print $1}')" <<'PY'
import hashlib, json, pathlib, sys
path = pathlib.Path(sys.argv[1])
selection_path = pathlib.Path(sys.argv[2])
selection = json.loads(selection_path.read_text(encoding="utf-8"))
path.write_text(json.dumps({
    "scenarioId": "TILDEN-HANDOFF-002",
    "selectionId": selection["selectionId"],
    "selectedEndpoint": selection["selectedEndpoint"],
    "selectionSha256": hashlib.sha256(selection_path.read_bytes()).hexdigest(),
    "pjsip": {
        "repository": "pjsip/pjproject",
        "release": "2.17",
        "commit": "5a457451fa2712ba18e12b01738e8ff3af2b26fd",
        "cleanCheckout": True,
        "role": "tilden-selected-native-rtt-endpoint",
        "nativeMediaApi": "incoming PJSUA2 Call -> active text media -> Call::sendText -> PJMEDIA",
        "baudotUasSourceSha256": sys.argv[3],
        "verdictAuthority": False,
    },
    "authority": {
        "routeSelection": "Tilden selection evidence",
        "signaling": "Baudot JAIN SIP harness",
        "rttSemanticReadiness": "Baudot Python RFC4103/T.140 reference",
    },
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

printf '%s\n' "$actual_commit" >"$OUT/pjsip-commit.txt"
printf '%s\n' "$actual_release" >"$OUT/pjsip-release.txt"
git -C "$PJSIP_ROOT" status --short >"$OUT/pjsip-status.txt"
cmake --version >"$OUT/cmake-version.txt"
c++ --version >"$OUT/cxx-version.txt"

cmake -S "$ROOT/interop/pjsip" -B "$APP_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DPJSIP_SOURCE_DIR="$PJSIP_ROOT" \
  >"$OUT/uas-configure.log" 2>&1
cmake --build "$APP_BUILD" --parallel 4 --target baudot-pjsip-native-t140-uas \
  >"$OUT/uas-build.log" 2>&1
[[ -x "$APP" ]] || { echo "native PJSIP UAS was not built: $APP" >&2; exit 3; }
sha256sum "$APP" >"$OUT/uas.sha256"

python3 -m scripts.live_t140_readiness_gate \
  --bind-host 127.0.0.1 \
  --port "$MEDIA_PORT" \
  --evidence-dir "$READINESS" \
  --ready-file "$READY_FILE" \
  --expected-text H \
  --payload-type 98 \
  --timeout-ms 12000 \
  >"$OUT/gate.stdout.log" 2>"$OUT/gate.stderr.log" &
GATE_PID=$!

gate_ready=0
for _ in $(seq 1 100); do
  if ! kill -0 "$GATE_PID" 2>/dev/null; then
    echo "live readiness gate exited before binding UDP/$MEDIA_PORT" >&2
    cat "$OUT/gate.stderr.log" >&2 || true
    exit 4
  fi
  if ss -H -lun | awk -v port=":$MEDIA_PORT" '$5 ~ port "$" || $4 ~ port "$" { found=1 } END { exit found ? 0 : 1 }'; then
    gate_ready=1
    break
  fi
  sleep .05
done
[[ "$gate_ready" == 1 ]] || { echo "live readiness gate did not bind UDP/$MEDIA_PORT" >&2; exit 4; }
ss -H -lun | awk -v port=":$MEDIA_PORT" '$5 ~ port "$" || $4 ~ port "$"' >"$OUT/readiness-listener.txt"

timeout --signal=TERM --kill-after=2s 35s env \
  BAUDOT_PJSIP_UAS_PORT="$UAS_PORT" \
  BAUDOT_PJSIP_TEXT=H \
  BAUDOT_PJSIP_UAS_COMPLETION_FILE="$COMPLETION_FILE" \
  "$APP" >"$OUT/pjsip.stdout.log" 2>"$OUT/pjsip.stderr.log" &
UAS_PID=$!

uas_ready=0
for _ in $(seq 1 200); do
  if ! kill -0 "$UAS_PID" 2>/dev/null; then
    echo "PJSIP UAS exited before readiness" >&2
    cat "$OUT/pjsip.stderr.log" >&2 || true
    exit 4
  fi
  if grep -q 'PJSIP_NATIVE_T140_UAS_READY release=2.17' "$OUT/pjsip.stdout.log" 2>/dev/null; then
    uas_ready=1
    break
  fi
  sleep .05
done
[[ "$uas_ready" == 1 ]] || { echo "PJSIP UAS did not report readiness" >&2; exit 4; }

set +e
BAUDOT_TILDEN_RTT_CALLER_PORT="$CALLER_PORT" \
BAUDOT_TILDEN_RTT_MEDIA_PORT="$MEDIA_PORT" \
BAUDOT_RTT_READY_FILE="$READY_FILE" \
BAUDOT_EVIDENCE_DIR="$EVIDENCE_ROOT" \
  timeout --signal=TERM --kill-after=5s 25s \
  mvn -B -ntp -q \
  -Dexec.mainClass=org.mcc0nnell.baudot.harness.TildenPjsipRttCallMain \
  -Dexec.args="$SELECTION" \
  exec:java \
  >"$OUT/jain.stdout.log" 2>"$OUT/jain.stderr.log"
jain_status=$?
wait "$GATE_PID"
gate_status=$?
GATE_PID=""

uas_alive_after_verdict=0
if kill -0 "$UAS_PID" 2>/dev/null; then
  uas_alive_after_verdict=1
fi
printf '%s\n' "$uas_alive_after_verdict" >"$OUT/pjsip-alive-after-verdict.txt"
touch "$COMPLETION_FILE"
wait "$UAS_PID"
uas_status=$?
UAS_PID=""
set -e

printf '%s\n' "$jain_status" >"$OUT/jain.exit-code.txt"
printf '%s\n' "$gate_status" >"$OUT/gate.exit-code.txt"
printf '%s\n' "$uas_status" >"$OUT/pjsip.exit-code.txt"
[[ "$jain_status" == 0 ]] || { echo "Tilden-selected JAIN caller failed: $jain_status" >&2; cat "$OUT/jain.stderr.log" >&2 || true; exit 5; }
[[ "$gate_status" == 0 ]] || { echo "live readiness gate failed: $gate_status" >&2; cat "$OUT/gate.stderr.log" >&2 || true; exit 5; }
[[ "$uas_alive_after_verdict" == 1 ]] || { echo "PJSIP selected endpoint exited before verdict completed" >&2; exit 5; }
[[ "$uas_status" == 0 ]] || { echo "PJSIP UAS failed with exit $uas_status" >&2; cat "$OUT/pjsip.stderr.log" >&2 || true; exit 5; }

(
  cd "$READINESS"
  sha256sum -c manifest.sha256
)
python3 "$ROOT/scripts/validate_tilden_pjsip_rtt_handoff.py" --out "$OUT" --selection "$SELECTION"

(
  cd "$OUT"
  required=(
    route.json
    admission.json
    pjsip-commit.txt
    pjsip-release.txt
    pjsip-status.txt
    cmake-version.txt
    cxx-version.txt
    uas-configure.log
    uas-build.log
    uas.sha256
    pjsip.stdout.log
    pjsip.stderr.log
    pjsip.exit-code.txt
    pjsip-alive-after-verdict.txt
    pjsip-post-verdict-complete.signal
    readiness-listener.txt
    gate.stdout.log
    gate.stderr.log
    gate.exit-code.txt
    jain.stdout.log
    jain.stderr.log
    jain.exit-code.txt
    readiness/events.jsonl
    readiness/result.json
    readiness/rtt-ready.json
    readiness/manifest.sha256
    jain-caller/events.jsonl
    jain-caller/result.properties
    jain-caller/invite.request.sip
    jain-caller/offer.sdp
    jain-caller/invite-200.response.sip
    jain-caller/answer.sdp
    jain-caller/ack.request.sip
    jain-caller/rtt-ready.token.json
    jain-caller/bye.request.sip
    jain-caller/bye-200.response.sip
    terminal-result.json
  )
  for artifact in "${required[@]}"; do test -f "$artifact"; done
  packets=(readiness/rtt-datagram-*.bin)
  [[ -e "${packets[0]}" ]] || { echo "no native PJSIP RTT packet evidence" >&2; exit 6; }
  sha256sum "${required[@]}" "${packets[@]}" >bundle.manifest.sha256
  sha256sum -c bundle.manifest.sha256
)

cat "$OUT/jain-caller/result.properties"
cat "$OUT/terminal-result.json"
printf 'tildenPjsipRttEvidence=%s\n' "$OUT"
