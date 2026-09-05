#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ELIXIP_ROOT=${ELIXIP_ROOT:?set ELIXIP_ROOT to the pinned clean neutrino38/elixip checkout}
ELIXIPP_BIN=${ELIXIPP_BIN:-$ELIXIP_ROOT/apps/elixipp/elixipp}
ELIXIP_PORT=${BAUDOT_ELIXIP_SIP_PORT:-5282}
JAIN_PORT=5280
SCENARIO="$ROOT/interop/elixip/interop004-elixip-to-jain-signaling-only.exs"
EVIDENCE=${BAUDOT_EVIDENCE_DIR:-$ROOT/target/evidence-external}
CORRELATION=elixip-to-jain-signaling-only-v1
OUT="$EVIDENCE/BAUDOT-INTEROP-004/$CORRELATION"
RUN="$OUT/elixip-to-jain-signaling-only"
JAIN_PID=""
ELIXIP_PID=""

cleanup() {
  set +e
  if [[ -n "$ELIXIP_PID" ]]; then
    kill "$ELIXIP_PID" 2>/dev/null
    wait "$ELIXIP_PID" 2>/dev/null
  fi
  if [[ -n "$JAIN_PID" ]]; then
    kill "$JAIN_PID" 2>/dev/null
    wait "$JAIN_PID" 2>/dev/null
  fi
}
trap cleanup EXIT

for bin in python3 java mvn git sha256sum ss timeout grep; do
  command -v "$bin" >/dev/null || { echo "missing required executable: $bin" >&2; exit 2; }
done
[[ -x "$ELIXIPP_BIN" ]] || { echo "Elixip executable not found: $ELIXIPP_BIN" >&2; exit 2; }

rm -rf "$OUT"
mkdir -p "$OUT"

cd "$ROOT"
python3 -m scripts.elixip_oracle_admission \
  --elixip-root "$ELIXIP_ROOT" \
  --scenario "$SCENARIO" \
  --output "$OUT/admission.json"

cp "$SCENARIO" "$OUT/scenario.exs"
ELIXIPP_SHA=$(sha256sum "$ELIXIPP_BIN" | awk '{print $1}')
cat >"$OUT/implementation.properties" <<EOF
sourceImplementation.name=Elixip
sourceImplementation.repository=neutrino38/elixip
sourceImplementation.commit=d5f942768213200576031346099a896fb61bef4f
sourceImplementation.executableSha256=$ELIXIPP_SHA
sourceImplementation.authority=observation-only
transferImplementation.name=JAIN-SIP
transferImplementation.authority=instrument-only
EOF

mvn -q -DskipTests compile dependency:build-classpath \
  -Dmdep.outputFile=target/baudot-runtime-classpath.txt
CP="$ROOT/target/classes:$(cat "$ROOT/target/baudot-runtime-classpath.txt")"

BAUDOT_EVIDENCE_DIR="$EVIDENCE" \
  java -cp "$CP" org.mcc0nnell.baudot.harness.ElixipToJainReferSignalingOnlyProbe \
  >"$OUT/jain.stdout.log" 2>"$OUT/jain.stderr.log" &
JAIN_PID=$!

jain_ready=0
for _ in $(seq 1 100); do
  if ! kill -0 "$JAIN_PID" 2>/dev/null; then
    echo "JAIN reverse transfer processor exited before binding UDP/$JAIN_PORT" >&2
    cat "$OUT/jain.stderr.log" >&2 || true
    exit 3
  fi
  if ss -H -lun | awk -v port=":$JAIN_PORT" '$4 ~ port "$" { found=1 } END { exit found ? 0 : 1 }'; then
    jain_ready=1
    break
  fi
  sleep .1
done
[[ "$jain_ready" == 1 ]] || { echo "JAIN reverse transfer processor did not bind UDP/$JAIN_PORT" >&2; exit 3; }
ss -H -lun | awk -v port=":$JAIN_PORT" '$4 ~ port "$"' >"$OUT/jain-listener.txt"
[[ -s "$OUT/jain-listener.txt" ]] || { echo "unable to preserve JAIN listener evidence" >&2; exit 3; }

(
  cd "$ELIXIP_ROOT"
  exec timeout --signal=TERM --kill-after=5s 35s \
    "$ELIXIPP_BIN" --listen "udp:$ELIXIP_PORT" "$SCENARIO"
) >"$OUT/elixip.stdout.log" 2>"$OUT/elixip.stderr.log" &
ELIXIP_PID=$!

# Preserve the independently implemented UAC listener when it becomes visible.
elixip_ready=0
for _ in $(seq 1 50); do
  if ! kill -0 "$ELIXIP_PID" 2>/dev/null; then
    break
  fi
  if ss -H -lun | awk -v port=":$ELIXIP_PORT" '$4 ~ port "$" { found=1 } END { exit found ? 0 : 1 }'; then
    elixip_ready=1
    ss -H -lun | awk -v port=":$ELIXIP_PORT" '$4 ~ port "$"' >"$OUT/elixip-listener.txt"
    break
  fi
  sleep .1
done

set +e
wait "$ELIXIP_PID"
ELIXIP_STATUS=$?
ELIXIP_PID=""
wait "$JAIN_PID"
JAIN_STATUS=$?
JAIN_PID=""
set -e

if [[ "$ELIXIP_STATUS" -ne 0 || "$JAIN_STATUS" -ne 0 ]]; then
  echo "reverse interop execution failed: elixip=$ELIXIP_STATUS jain=$JAIN_STATUS" >&2
  echo "--- Elixip stdout ---" >&2
  cat "$OUT/elixip.stdout.log" >&2 || true
  echo "--- Elixip stderr ---" >&2
  cat "$OUT/elixip.stderr.log" >&2 || true
  echo "--- JAIN stdout ---" >&2
  cat "$OUT/jain.stdout.log" >&2 || true
  echo "--- JAIN stderr ---" >&2
  cat "$OUT/jain.stderr.log" >&2 || true
  exit 4
fi

# The Elixip listener may disappear immediately on scenario success. Its network
# participation is also evidenced by the original INVITE/ACK and REFER bytes, so
# listener capture is supplemental rather than a terminal requirement.
if [[ "$elixip_ready" != 1 ]]; then
  printf 'listener.capture=not-observed-before-process-exit\n' >"$OUT/elixip-listener.txt"
fi

python3 -m scripts.validate_elixip_to_jain_refer_signaling_only \
  --run-dir "$RUN" \
  --elixip-log "$OUT/elixip.stdout.log"

(
  cd "$OUT"
  required=(
    admission.json
    implementation.properties
    scenario.exs
    elixip.stdout.log
    elixip.stderr.log
    elixip-listener.txt
    jain.stdout.log
    jain.stderr.log
    jain-listener.txt
    elixip-to-jain-signaling-only/manifest.sha256
    elixip-to-jain-signaling-only/result.properties
    elixip-to-jain-signaling-only/terminal-result.json
    elixip-to-jain-signaling-only/terminal.manifest.sha256
    elixip-to-jain-signaling-only/original-invite.request.sip
    elixip-to-jain-signaling-only/original-ack.request.sip
    elixip-to-jain-signaling-only/refer.request.sip
    elixip-to-jain-signaling-only/refer-202.response.sip
    elixip-to-jain-signaling-only/replacement-invite.request.sip
    elixip-to-jain-signaling-only/replacement-response-200.sip
    elixip-to-jain-signaling-only/replacement-ack.request.sip
    elixip-to-jain-signaling-only/notify-200.request.sip
  )
  for artifact in "${required[@]}"; do test -f "$artifact"; done
  sha256sum "${required[@]}" >bundle.manifest.sha256
)

cat "$RUN/result.properties"
cat "$RUN/terminal-result.json"
printf 'crossStackEvidence=%s\n' "$OUT"
