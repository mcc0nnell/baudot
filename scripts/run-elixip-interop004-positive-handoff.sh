#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ELIXIP_ROOT=${ELIXIP_ROOT:?set ELIXIP_ROOT to the pinned clean neutrino38/elixip checkout}
ELIXIPP_BIN=${ELIXIPP_BIN:-$ELIXIP_ROOT/apps/elixipp/elixipp}
ELIXIP_PORT=${BAUDOT_ELIXIP_SIP_PORT:-5272}
SCENARIO="$ROOT/interop/elixip/interop004-positive-handoff-target.exs"
EVIDENCE=${BAUDOT_EVIDENCE_DIR:-$ROOT/target/evidence-external}
CORRELATION=jain-to-elixip-positive-handoff-v1
OUT="$EVIDENCE/BAUDOT-INTEROP-004/$CORRELATION"
RUN="$OUT/jain-to-elixip-positive-handoff"
TARGET_PID=""

cleanup() {
  set +e
  if [[ -n "$TARGET_PID" ]]; then
    kill "$TARGET_PID" 2>/dev/null
    wait "$TARGET_PID" 2>/dev/null
  fi
}
trap cleanup EXIT

for bin in python3 java mvn git sha256sum ss grep; do
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
implementation.name=Elixip
implementation.repository=neutrino38/elixip
implementation.commit=d5f942768213200576031346099a896fb61bef4f
implementation.executableSha256=$ELIXIPP_SHA
implementation.authority=observation-only
media.stimulus.owner=Baudot-scenario
media.stimulus.nativeElixipRfc4103=false
EOF

mvn -q -DskipTests compile dependency:build-classpath \
  -Dmdep.outputFile=target/baudot-runtime-classpath.txt
CP="$ROOT/target/classes:$(cat "$ROOT/target/baudot-runtime-classpath.txt")"

(
  cd "$ELIXIP_ROOT"
  exec "$ELIXIPP_BIN" --listen "udp:$ELIXIP_PORT" "$SCENARIO"
) >"$OUT/elixip.stdout.log" 2>"$OUT/elixip.stderr.log" &
TARGET_PID=$!

ready=0
for _ in $(seq 1 100); do
  if ! kill -0 "$TARGET_PID" 2>/dev/null; then
    echo "Elixip target exited before binding UDP/$ELIXIP_PORT" >&2
    cat "$OUT/elixip.stderr.log" >&2 || true
    exit 3
  fi
  if ss -H -lun | awk -v port=":$ELIXIP_PORT" '$4 ~ port "$" { found=1 } END { exit found ? 0 : 1 }'; then
    ready=1
    break
  fi
  sleep .1
done
[[ "$ready" == 1 ]] || { echo "Elixip target did not bind UDP/$ELIXIP_PORT" >&2; exit 3; }
ss -H -lun | awk -v port=":$ELIXIP_PORT" '$4 ~ port "$"' >"$OUT/elixip-listener.txt"
[[ -s "$OUT/elixip-listener.txt" ]] || { echo "unable to preserve Elixip listener evidence" >&2; exit 3; }

BAUDOT_EVIDENCE_DIR="$EVIDENCE" \
BAUDOT_ELIXIP_SIP_HOST=127.0.0.1 \
BAUDOT_ELIXIP_SIP_PORT="$ELIXIP_PORT" \
  java -cp "$CP" org.mcc0nnell.baudot.harness.ElixipReferPositiveHandoffProbe

ack_observed=0
packet_sent=0
for _ in $(seq 1 30); do
  if grep -q 'BAUDOT-ELIXIP replacementAckObserved=true' "$OUT/elixip.stdout.log"; then
    ack_observed=1
  fi
  if grep -q 'BAUDOT-ELIXIP canonicalT140DatagramSent=true' "$OUT/elixip.stdout.log"; then
    packet_sent=1
  fi
  if [[ "$ack_observed" == 1 && "$packet_sent" == 1 ]]; then
    break
  fi
  sleep .1
done
[[ "$ack_observed" == 1 ]] || { echo "Elixip did not record replacement ACK receipt" >&2; exit 4; }
[[ "$packet_sent" == 1 ]] || { echo "external scenario did not record canonical T.140 stimulus emission" >&2; exit 4; }

python3 -m scripts.validate_elixip_refer_positive_handoff \
  --run-dir "$RUN" \
  --elixip-log "$OUT/elixip.stdout.log"

# Stop the server only after the live experiment and independent semantic
# reduction complete.
kill "$TARGET_PID" 2>/dev/null || true
wait "$TARGET_PID" 2>/dev/null || true
TARGET_PID=""

(
  cd "$OUT"
  required=(
    admission.json
    implementation.properties
    scenario.exs
    elixip.stdout.log
    elixip.stderr.log
    elixip-listener.txt
    jain-to-elixip-positive-handoff/manifest.sha256
    jain-to-elixip-positive-handoff/result.properties
    jain-to-elixip-positive-handoff/terminal-result.json
    jain-to-elixip-positive-handoff/replacement-invite.request.sip
    jain-to-elixip-positive-handoff/replacement-response-200.sip
    jain-to-elixip-positive-handoff/replacement-ack.request.sip
    jain-to-elixip-positive-handoff/rtt-datagram-received.bin
    jain-to-elixip-positive-handoff/notify-200.request.sip
    jain-to-elixip-positive-handoff/old-leg-bye-sent.request.sip
    jain-to-elixip-positive-handoff/old-leg-bye-observed.request.sip
  )
  for artifact in "${required[@]}"; do test -f "$artifact"; done
  sha256sum "${required[@]}" >bundle.manifest.sha256
)

cat "$RUN/result.properties"
cat "$RUN/terminal-result.json"
printf 'crossStackEvidence=%s\n' "$OUT"
