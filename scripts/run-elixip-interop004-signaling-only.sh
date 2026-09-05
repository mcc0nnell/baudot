#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ELIXIP_ROOT=${ELIXIP_ROOT:?set ELIXIP_ROOT to the pinned clean neutrino38/elixip checkout}
ELIXIPP_BIN=${ELIXIPP_BIN:-$ELIXIP_ROOT/apps/elixipp/elixipp}
ELIXIP_PORT=${BAUDOT_ELIXIP_SIP_PORT:-5262}
SCENARIO="$ROOT/interop/elixip/interop004-signaling-only-target.exs"
EVIDENCE=${BAUDOT_EVIDENCE_DIR:-$ROOT/target/evidence-external}
CORRELATION=jain-to-elixip-signaling-only-v1
OUT="$EVIDENCE/BAUDOT-INTEROP-004/$CORRELATION"
RUN="$OUT/jain-to-elixip-signaling-only"
TARGET_PID=""

cleanup() {
  set +e
  if [[ -n "$TARGET_PID" ]]; then
    kill "$TARGET_PID" 2>/dev/null
    wait "$TARGET_PID" 2>/dev/null
  fi
}
trap cleanup EXIT

for bin in python3 java mvn git sha256sum ss; do
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
  # ss -lun columns are: State Recv-Q Send-Q Local-Address:Port Peer-Address:Port.
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
  java -cp "$CP" org.mcc0nnell.baudot.harness.ElixipReferSignalingOnlyProbe

python3 -m scripts.validate_elixip_refer_signaling_only --run-dir "$RUN"

# Stop the server only after Baudot's bounded observation and reduction complete.
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
    jain-to-elixip-signaling-only/manifest.sha256
    jain-to-elixip-signaling-only/result.properties
    jain-to-elixip-signaling-only/replacement-invite.request.sip
    jain-to-elixip-signaling-only/replacement-response-200.sip
    jain-to-elixip-signaling-only/notify-200.request.sip
  )
  for artifact in "${required[@]}"; do test -f "$artifact"; done
  sha256sum "${required[@]}" >bundle.manifest.sha256
)

cat "$RUN/result.properties"
printf 'crossStackEvidence=%s\n' "$OUT"
