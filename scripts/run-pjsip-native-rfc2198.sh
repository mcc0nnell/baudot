#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PJSIP_ROOT=${PJSIP_ROOT:?set PJSIP_ROOT to the exact clean pjsip/pjproject checkout}
EXPECTED_COMMIT=${BAUDOT_PJSIP_EXPECTED_COMMIT:?set BAUDOT_PJSIP_EXPECTED_COMMIT}
PROFILE=${BAUDOT_PJSIP_PROFILE_LABEL:?set BAUDOT_PJSIP_PROFILE_LABEL}
CORRELATION=${BAUDOT_PJSIP_RFC2198_CORRELATION:?set BAUDOT_PJSIP_RFC2198_CORRELATION}
EXPECT_RECOVERY=${BAUDOT_PJSIP_EXPECT_RECOVERY:?set BAUDOT_PJSIP_EXPECT_RECOVERY to true or false}
EXPECTED_TAG=${BAUDOT_PJSIP_EXPECTED_TAG:-}
SIP_PORT=${BAUDOT_PJSIP_REMOTE_PORT:-5310}
LOCAL_PORT=${BAUDOT_PJSIP_LOCAL_PORT:-5311}
MEDIA_PORT=${BAUDOT_PJSIP_MEDIA_PORT:-5312}
SENDER_TIMEOUT=${BAUDOT_PJSIP_SENDER_TIMEOUT:-30}
RECEIVER_TIMEOUT=${BAUDOT_PJSIP_RECEIVER_TIMEOUT:-35}
EVIDENCE=${BAUDOT_EVIDENCE_DIR:-$ROOT/target/evidence-external}
SCENARIO=PJSIP-NATIVE-RFC2198
OUT="$EVIDENCE/$SCENARIO/$CORRELATION"
APP_BUILD="$ROOT/target/pjsip-native-rfc2198-app-$PROFILE"
APP="$APP_BUILD/baudot-pjsip-native-rfc2198"
JAIN_PID=""

cleanup() {
  set +e
  if [[ -n "$JAIN_PID" ]]; then
    kill "$JAIN_PID" 2>/dev/null
    wait "$JAIN_PID" 2>/dev/null
  fi
}
trap cleanup EXIT

for bin in cmake c++ git java mvn python3 sha256sum grep ldd timeout; do
  command -v "$bin" >/dev/null || { echo "missing required executable: $bin" >&2; exit 2; }
done

actual_commit=$(git -C "$PJSIP_ROOT" rev-parse HEAD)
[[ "$actual_commit" == "$EXPECTED_COMMIT" ]] || { echo "unexpected PJSIP commit: $actual_commit" >&2; exit 2; }
[[ -z "$(git -C "$PJSIP_ROOT" status --porcelain=v1 --untracked-files=normal)" ]] || { echo "PJSIP checkout must be clean" >&2; exit 2; }
actual_tag=$(git -C "$PJSIP_ROOT" describe --tags --exact-match HEAD 2>/dev/null || true)
if [[ -n "$EXPECTED_TAG" ]]; then
  [[ "$actual_tag" == "$EXPECTED_TAG" ]] || { echo "PJSIP checkout is not exact tag $EXPECTED_TAG: ${actual_tag:-none}" >&2; exit 2; }
fi

rm -rf "$OUT" "$APP_BUILD"
mkdir -p "$OUT"

sender_source="$ROOT/interop/pjsip/native_rfc2198_sender.cpp"
sender_source_sha=$(sha256sum "$sender_source" | awk '{print $1}')
python3 - "$OUT/pjsip-admission.json" "$sender_source_sha" "$SENDER_TIMEOUT" "$RECEIVER_TIMEOUT" "$EXPECTED_COMMIT" "$PROFILE" "$EXPECT_RECOVERY" "${actual_tag:-}" <<'PY'
import json
import pathlib
import sys

out = pathlib.Path(sys.argv[1])
out.write_text(json.dumps({
    "repository": "pjsip/pjproject",
    "commit": sys.argv[5],
    "profile": sys.argv[6],
    "expectedRecovery": sys.argv[7].lower() == "true",
    "exactTag": sys.argv[8] or None,
    "cleanCheckout": True,
    "role": "native-rfc2198-media-oracle",
    "verdictAuthority": False,
    "nativeMediaApi": "PJSUA2 Call::sendText -> PJMEDIA text stream RFC2198 redundancy",
    "redundancyLevel": 2,
    "redPayloadType": 100,
    "t140PayloadType": 98,
    "baudotSenderSourceSha256": sys.argv[2],
    "senderTimeoutSeconds": int(sys.argv[3]),
    "receiverTimeoutSeconds": int(sys.argv[4]),
    "claimBoundary": {
        "sipConformance": False,
        "rfc2198Conformance": False,
        "rfc4103Conformance": False,
        "t140Conformance": False,
    },
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

printf '%s\n' "$actual_commit" >"$OUT/pjsip-commit.txt"
printf '%s\n' "${actual_tag:-none}" >"$OUT/pjsip-exact-tag.txt"
printf '%s\n' "$PROFILE" >"$OUT/pjsip-profile.txt"
git -C "$PJSIP_ROOT" status --short >"$OUT/pjsip-status.txt"
cmake --version >"$OUT/cmake-version.txt"
c++ --version >"$OUT/cxx-version.txt"

cmake -S "$ROOT/interop/pjsip" -B "$APP_BUILD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DPJSIP_SOURCE_DIR="$PJSIP_ROOT" \
  >"$OUT/sender-configure.log" 2>&1
cmake --build "$APP_BUILD" --parallel 4 --target baudot-pjsip-native-rfc2198 \
  >"$OUT/sender-build.log" 2>&1
[[ -x "$APP" ]] || { echo "native PJSIP RFC2198 sender was not built: $APP" >&2; exit 3; }
ldd "$APP" >"$OUT/sender-ldd.txt" || true
sha256sum "$APP" >"$OUT/sender.sha256"

cd "$ROOT"
mvn -q -DskipTests compile dependency:build-classpath -Dmdep.outputFile=target/baudot-runtime-classpath.txt
CP="$ROOT/target/classes:$(cat "$ROOT/target/baudot-runtime-classpath.txt")"

timeout --signal=TERM --kill-after=2s "${RECEIVER_TIMEOUT}s" env \
  BAUDOT_EVIDENCE_ROOT="$EVIDENCE" \
  BAUDOT_PJSIP_REMOTE_PORT="$SIP_PORT" \
  BAUDOT_PJSIP_MEDIA_PORT="$MEDIA_PORT" \
  BAUDOT_PJSIP_RFC2198_CORRELATION="$CORRELATION" \
  BAUDOT_PJSIP_PROFILE_LABEL="$PROFILE" \
  java -cp "$CP" org.mcc0nnell.baudot.harness.PjsipNativeRedReceiverProbe \
  >"$OUT/jain.stdout.log" 2>"$OUT/jain.stderr.log" &
JAIN_PID=$!

ready_file="$OUT/jain-red-receiver/events.jsonl"
ready=0
for _ in $(seq 1 120); do
  if ! kill -0 "$JAIN_PID" 2>/dev/null; then
    echo "JAIN RED receiver exited before readiness" >&2
    cat "$OUT/jain.stderr.log" >&2 || true
    exit 4
  fi
  if [[ -f "$ready_file" ]] && grep -q 'pjsip.native_red.receiver_ready' "$ready_file"; then
    ready=1
    break
  fi
  sleep .1
done
[[ "$ready" == 1 ]] || { echo "JAIN RED receiver did not become ready" >&2; exit 4; }

set +e
timeout --signal=TERM --kill-after=2s "${SENDER_TIMEOUT}s" env \
  BAUDOT_PJSIP_LOCAL_PORT="$LOCAL_PORT" \
  BAUDOT_PJSIP_REMOTE_PORT="$SIP_PORT" \
  BAUDOT_PJSIP_REMOTE_URI="sip:baudot-red@127.0.0.1:$SIP_PORT" \
  BAUDOT_PJSIP_TEXT_FIRST=H \
  BAUDOT_PJSIP_TEXT_SECOND=I \
  BAUDOT_PJSIP_REDUNDANCY_LEVEL=2 \
  BAUDOT_PJSIP_PROFILE_LABEL="$PROFILE" \
  "$APP" >"$OUT/pjsip.stdout.log" 2>"$OUT/pjsip.stderr.log"
sender_status=$?
wait "$JAIN_PID"
jain_status=$?
JAIN_PID=""
set -e

printf '%s\n' "$sender_status" >"$OUT/pjsip.exit-code.txt"
printf '%s\n' "$jain_status" >"$OUT/jain.exit-code.txt"
printf '%s\n' "$SENDER_TIMEOUT" >"$OUT/pjsip-timeout-seconds.txt"
printf '%s\n' "$RECEIVER_TIMEOUT" >"$OUT/jain-timeout-seconds.txt"
[[ "$sender_status" != 124 && "$sender_status" != 137 ]] || { echo "PJSIP RFC2198 sender exceeded execution window" >&2; exit 5; }
[[ "$jain_status" != 124 && "$jain_status" != 137 ]] || { echo "JAIN RED receiver exceeded execution window" >&2; exit 5; }
[[ "$sender_status" == 0 ]] || { echo "PJSIP RFC2198 sender failed: $sender_status" >&2; cat "$OUT/pjsip.stderr.log" >&2 || true; exit 5; }
[[ "$jain_status" == 0 ]] || { echo "JAIN RED receiver failed: $jain_status" >&2; cat "$OUT/jain.stderr.log" >&2 || true; exit 5; }

BAUDOT_EVIDENCE_ROOT="$EVIDENCE" \
BAUDOT_PJSIP_RFC2198_CORRELATION="$CORRELATION" \
BAUDOT_PJSIP_EXPECTED_COMMIT="$EXPECTED_COMMIT" \
BAUDOT_PJSIP_PROFILE_LABEL="$PROFILE" \
BAUDOT_PJSIP_EXPECT_RECOVERY="$EXPECT_RECOVERY" \
  python3 -m scripts.validate_pjsip_native_rfc2198

(
  cd "$OUT"
  (cd terminal && sha256sum -c manifest.sha256)
  required=(
    pjsip-admission.json
    pjsip-commit.txt
    pjsip-exact-tag.txt
    pjsip-profile.txt
    pjsip-status.txt
    cmake-version.txt
    cxx-version.txt
    sender-configure.log
    sender-build.log
    sender-ldd.txt
    sender.sha256
    pjsip.stdout.log
    pjsip.stderr.log
    pjsip.exit-code.txt
    pjsip-timeout-seconds.txt
    jain.stdout.log
    jain.stderr.log
    jain.exit-code.txt
    jain-timeout-seconds.txt
    jain-red-receiver/manifest.sha256
    jain-red-receiver/result.properties
    jain-red-receiver/pjsip-offer.sdp
    jain-red-receiver/baudot-answer.sdp
    terminal/manifest.sha256
    terminal/pjsip-native-rfc2198.json
  )
  for artifact in "${required[@]}"; do test -f "$artifact"; done
  packets=(jain-red-receiver/rtt-datagram-*.bin)
  [[ -e "${packets[0]}" ]] || { echo "no native PJSIP RFC2198 packet evidence" >&2; exit 6; }
  sha256sum "${required[@]}" "${packets[@]}" >bundle.manifest.sha256
)

cat "$OUT/jain-red-receiver/result.properties"
cat "$OUT/terminal/pjsip-native-rfc2198.json"
printf 'nativePjsipRfc2198Evidence=%s\n' "$OUT"
