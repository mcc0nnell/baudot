#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PJSIP_ROOT=${PJSIP_ROOT:?set PJSIP_ROOT to the pinned clean pjsip/pjproject 2.17 checkout}
EXPECTED_COMMIT=5a457451fa2712ba18e12b01738e8ff3af2b26fd
PJSIP_RELEASE=2.17
SIP_PORT=${BAUDOT_PJSIP_REMOTE_PORT:-5290}
LOCAL_PORT=${BAUDOT_PJSIP_LOCAL_PORT:-5291}
MEDIA_PORT=${BAUDOT_PJSIP_MEDIA_PORT:-5292}
EVIDENCE=${BAUDOT_EVIDENCE_DIR:-$ROOT/target/evidence-external}
SCENARIO=PJSIP-NATIVE-T140
CORRELATION=pjsip-2.17-native-text-v1
OUT="$EVIDENCE/$SCENARIO/$CORRELATION"
PJ_BUILD=${BAUDOT_PJSIP_BUILD_DIR:-/tmp/baudot-pjsip-build}
PJ_INSTALL=${BAUDOT_PJSIP_INSTALL_DIR:-/tmp/baudot-pjsip-install}
APP_BUILD="$ROOT/target/pjsip-native-t140-app"
APP="$APP_BUILD/baudot-pjsip-native-t140"
JAIN_PID=""

cleanup() {
  set +e
  if [[ -n "$JAIN_PID" ]]; then
    kill "$JAIN_PID" 2>/dev/null
    wait "$JAIN_PID" 2>/dev/null
  fi
}
trap cleanup EXIT

for bin in cmake c++ git java mvn python3 sha256sum grep ldd; do
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

rm -rf "$OUT" "$PJ_BUILD" "$PJ_INSTALL" "$APP_BUILD"
mkdir -p "$OUT"

sender_source="$ROOT/interop/pjsip/native_t140_sender.cpp"
sender_source_sha=$(sha256sum "$sender_source" | awk '{print $1}')
python3 - "$OUT/pjsip-admission.json" "$sender_source_sha" <<'PY'
import json
import pathlib
import subprocess
import sys

out = pathlib.Path(sys.argv[1])
source_sha = sys.argv[2]
record = {
    "repository": "pjsip/pjproject",
    "release": "2.17",
    "commit": "5a457451fa2712ba18e12b01738e8ff3af2b26fd",
    "cleanCheckout": True,
    "role": "native-media-oracle",
    "verdictAuthority": False,
    "nativeMediaApi": "PJSUA2 Call::sendText -> pjsua_call_send_text -> pjmedia_txt_stream_send_text",
    "baudotSenderSourceSha256": source_sha,
    "claimBoundary": {
        "sipConformance": False,
        "rfc4103Conformance": False,
        "t140Conformance": False,
    },
}
out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

git -C "$PJSIP_ROOT" status --short >"$OUT/pjsip-status.txt"
printf '%s\n' "$actual_commit" >"$OUT/pjsip-commit.txt"
printf '%s\n' "$actual_release" >"$OUT/pjsip-release.txt"
cmake --version >"$OUT/cmake-version.txt"
c++ --version >"$OUT/cxx-version.txt"

cmake -S "$PJSIP_ROOT" -B "$PJ_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PJ_INSTALL" \
  -DBUILD_SHARED_LIBS=ON \
  -DBUILD_TESTING=OFF \
  -DPJ_SKIP_EXPERIMENTAL_NOTICE=ON \
  >"$OUT/pjsip-configure.log" 2>&1
cmake --build "$PJ_BUILD" --parallel 2 --target install \
  >"$OUT/pjsip-build.log" 2>&1

cmake -S "$ROOT/interop/pjsip" -B "$APP_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH="$PJ_INSTALL" \
  >"$OUT/sender-configure.log" 2>&1
cmake --build "$APP_BUILD" --parallel 2 \
  >"$OUT/sender-build.log" 2>&1
[[ -x "$APP" ]] || { echo "native PJSIP sender was not built: $APP" >&2; exit 3; }
ldd "$APP" >"$OUT/sender-ldd.txt" || true
sha256sum "$APP" >"$OUT/sender.sha256"

cd "$ROOT"
mvn -q -DskipTests compile dependency:build-classpath \
  -Dmdep.outputFile=target/baudot-runtime-classpath.txt
CP="$ROOT/target/classes:$(cat "$ROOT/target/baudot-runtime-classpath.txt")"

BAUDOT_EVIDENCE_ROOT="$EVIDENCE" \
BAUDOT_PJSIP_REMOTE_PORT="$SIP_PORT" \
BAUDOT_PJSIP_MEDIA_PORT="$MEDIA_PORT" \
  java -cp "$CP" org.mcc0nnell.baudot.harness.PjsipNativeTextReceiverProbe \
  >"$OUT/jain.stdout.log" 2>"$OUT/jain.stderr.log" &
JAIN_PID=$!

ready_file="$OUT/jain-receiver/events.jsonl"
ready=0
for _ in $(seq 1 120); do
  if ! kill -0 "$JAIN_PID" 2>/dev/null; then
    echo "JAIN receiver exited before readiness" >&2
    cat "$OUT/jain.stderr.log" >&2 || true
    exit 4
  fi
  if [[ -f "$ready_file" ]] && grep -q 'pjsip.native_text.receiver_ready' "$ready_file"; then
    ready=1
    break
  fi
  sleep .1
done
[[ "$ready" == 1 ]] || { echo "JAIN receiver did not become ready" >&2; exit 4; }

set +e
LD_LIBRARY_PATH="$PJ_INSTALL/lib:$PJ_INSTALL/lib64:${LD_LIBRARY_PATH:-}" \
BAUDOT_PJSIP_LOCAL_PORT="$LOCAL_PORT" \
BAUDOT_PJSIP_REMOTE_PORT="$SIP_PORT" \
BAUDOT_PJSIP_REMOTE_URI="sip:baudot@127.0.0.1:$SIP_PORT" \
BAUDOT_PJSIP_TEXT=H \
  "$APP" >"$OUT/pjsip.stdout.log" 2>"$OUT/pjsip.stderr.log"
sender_status=$?
wait "$JAIN_PID"
jain_status=$?
JAIN_PID=""
set -e

printf '%s\n' "$sender_status" >"$OUT/pjsip.exit-code.txt"
printf '%s\n' "$jain_status" >"$OUT/jain.exit-code.txt"
[[ "$sender_status" == 0 ]] || {
  echo "PJSIP native sender failed with exit $sender_status" >&2
  cat "$OUT/pjsip.stderr.log" >&2 || true
  exit 5
}
[[ "$jain_status" == 0 ]] || {
  echo "JAIN native text receiver failed with exit $jain_status" >&2
  cat "$OUT/jain.stderr.log" >&2 || true
  exit 5
}

python3 -m scripts.validate_pjsip_native_t140

(
  cd "$OUT"
  required=(
    pjsip-admission.json
    pjsip-commit.txt
    pjsip-release.txt
    pjsip-status.txt
    pjsip.stdout.log
    pjsip.stderr.log
    pjsip.exit-code.txt
    jain.stdout.log
    jain.stderr.log
    jain.exit-code.txt
    sender.sha256
    jain-receiver/manifest.sha256
    jain-receiver/result.properties
    jain-receiver/pjsip-offer.sdp
    jain-receiver/baudot-answer.sdp
    terminal/manifest.sha256
    terminal/pjsip-native-t140.json
  )
  for artifact in "${required[@]}"; do test -f "$artifact"; done
  packets=(jain-receiver/rtt-datagram-*.bin)
  [[ -e "${packets[0]}" ]] || { echo "no native PJSIP RTT packet evidence" >&2; exit 6; }
  sha256sum "${required[@]}" "${packets[@]}" >bundle.manifest.sha256
)

cat "$OUT/jain-receiver/result.properties"
cat "$OUT/terminal/pjsip-native-t140.json"
printf 'nativePjsipEvidence=%s\n' "$OUT"
