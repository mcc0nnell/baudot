#!/usr/bin/env bash
set -euo pipefail

[[ ${EUID:-$(id -u)} -eq 0 ]] || exec sudo -E bash "$0" "$@"

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
WT=${WIRETAP_BIN:-wiretap}
CNS=${BAUDOT_CALLER_NS:-bdt-tty-jitter-caller}
SNS=${BAUDOT_CALLEE_NS:-bdt-tty-jitter-callee}
WORK=${BAUDOT_WIRETAP_DIR:-$ROOT/target/wiretap-routed/tty-v18-jitter}
EVIDENCE=${BAUDOT_EVIDENCE_DIR:-$ROOT/target/evidence-routed}
CORR=${BAUDOT_CORRELATION:-$(python3 -c 'import uuid; print(uuid.uuid4())')}
RUN="$EVIDENCE/tty-v18-jitter/$CORR"
BASELINE=${BAUDOT_TTY_BASELINE_DIR:-$ROOT/target/evidence/tty-v18-cross-oracle}
PCMU=${BAUDOT_TTY_RTP_EVIDENCE_DIR:-$ROOT/target/evidence/tty-v18-pcmu-rtp}
BIN_DIR=${BAUDOT_TTY_BIN_DIR:-$ROOT/target/tty-v18}

UL_HOST=198.18.3.1
UL_CLIENT=198.18.3.2
SIG_HOST=10.79.10.1
SIG_SERVER=10.79.10.2
MEDIA_HOST=10.79.20.1
MEDIA_SERVER=10.79.20.2
WT_PORT=51821
SIG_NET=10.79.10.0/24
MEDIA_NET=10.79.20.0/24
ROUTES="$SIG_NET,$MEDIA_NET"
RESPONSE_ROUTING=rfc3581-rport-over-transparent-flow
MEDIA_PORT=41100
DELAY_INDEX=20
DELAY_MS=35

server_pid=""
recv_pid=""
relay_up=0
e2ee_up=0

safe_server_log() {
  [[ -f "$WORK/server.log" ]] || return 0
  sed -E \
    -e 's/(private_key=).*/\1[REDACTED]/' \
    -e 's/(PrivateKey[[:space:]]*=[[:space:]]*).*/\1[REDACTED]/' \
    "$WORK/server.log"
}

cleanup() {
  set +e
  [[ -n "$recv_pid" ]] && kill "$recv_pid" 2>/dev/null
  if [[ -f "$WORK/server.log" && -d "$RUN" ]]; then
    safe_server_log >"$RUN/wiretap-server.log" 2>/dev/null
  fi
  [[ -n "$server_pid" ]] && kill "$server_pid" 2>/dev/null
  if ip netns list | grep -q "^${CNS}\b"; then
    ((e2ee_up)) && ip netns exec "$CNS" wg-quick down "$WORK/wiretap.conf" >/dev/null 2>&1
    ((relay_up)) && ip netns exec "$CNS" wg-quick down "$WORK/wiretap_relay.conf" >/dev/null 2>&1
  fi
  ip netns del "$CNS" 2>/dev/null
  ip netns del "$SNS" 2>/dev/null
  ip link del bdt-tty-jit-ul-h 2>/dev/null
  ip link del bdt-tty-jit-sig-h 2>/dev/null
  ip link del bdt-tty-jit-med-h 2>/dev/null
  rm -rf "$WORK"
  [[ -n "${SUDO_UID:-}" && -d "$EVIDENCE" ]] && chown -R "${SUDO_UID}:${SUDO_GID}" "$EVIDENCE" 2>/dev/null
}

required_inputs=(
  "$BASELINE/source.txt"
  "$PCMU/minimodem-to-spandsp.rtpseq"
  "$BIN_DIR/tty-v18-file"
)
for path in "${required_inputs[@]}"; do
  [[ -e "$path" ]] || { echo "missing jitter TTY input: $path" >&2; exit 2; }
done

rm -rf "$WORK"
mkdir -p "$WORK" "$RUN/jitter-reorder-recovery"
cp "$BASELINE/source.txt" "$RUN/source.txt"

cd "$ROOT"
python3 scripts/wiretap_topology_preflight.py \
  --wiretap-bin "$WT" \
  --underlay-address "$UL_HOST/24" \
  --underlay-address "$UL_CLIENT/24" \
  --signaling-network "$SIG_NET" \
  --media-network "$MEDIA_NET" \
  --routes "$ROUTES" \
  --response-routing "$RESPONSE_ROUTING" \
  --namespace "$CNS" \
  --namespace "$SNS" \
  --host-link bdt-tty-jit-ul-h \
  --host-link bdt-tty-jit-sig-h \
  --host-link bdt-tty-jit-med-h \
  --require-bin ip \
  --require-bin wg-quick \
  --require-bin python3 \
  --evidence-root "$EVIDENCE" \
  --output "$RUN/preflight.properties"
trap cleanup EXIT

ip netns add "$CNS"
ip netns add "$SNS"
ip -n "$CNS" link set lo up
ip -n "$SNS" link set lo up

ip link add bdt-tty-jit-ul-h type veth peer name bdt-tty-jit-ul-c
ip link set bdt-tty-jit-ul-c netns "$CNS"
ip addr add "$UL_HOST/24" dev bdt-tty-jit-ul-h
ip link set bdt-tty-jit-ul-h up
ip -n "$CNS" addr add "$UL_CLIENT/24" dev bdt-tty-jit-ul-c
ip -n "$CNS" link set bdt-tty-jit-ul-c up

ip link add bdt-tty-jit-sig-h type veth peer name bdt-tty-jit-sig-s
ip link set bdt-tty-jit-sig-s netns "$SNS"
ip addr add "$SIG_HOST/24" dev bdt-tty-jit-sig-h
ip link set bdt-tty-jit-sig-h up
ip -n "$SNS" addr add "$SIG_SERVER/24" dev bdt-tty-jit-sig-s
ip -n "$SNS" link set bdt-tty-jit-sig-s up

ip link add bdt-tty-jit-med-h type veth peer name bdt-tty-jit-med-s
ip link set bdt-tty-jit-med-s netns "$SNS"
ip addr add "$MEDIA_HOST/24" dev bdt-tty-jit-med-h
ip link set bdt-tty-jit-med-h up
ip -n "$SNS" addr add "$MEDIA_SERVER/24" dev bdt-tty-jit-med-s
ip -n "$SNS" link set bdt-tty-jit-med-s up

cd "$WORK"
"$WT" configure --endpoint "$UL_CLIENT:$WT_PORT" --routes "$ROUTES" --port "$WT_PORT" >configure.log
CALLER_E2EE=$(sed -n 's/^Address = \([0-9.]*\)\/.*/\1/p' "$WORK/wiretap.conf" | head -n1)
[[ -n "$CALLER_E2EE" ]] || { echo "unable to read Wiretap E2EE IPv4 address" >&2; exit 1; }

ip netns exec "$CNS" wg-quick up "$WORK/wiretap_relay.conf"
relay_up=1
ip netns exec "$CNS" wg-quick up "$WORK/wiretap.conf"
e2ee_up=1
"$WT" serve -f "$WORK/wiretap_server.conf" >server.log 2>&1 &
server_pid=$!

for _ in $(seq 1 100); do
  ip netns exec "$CNS" "$WT" ping >/dev/null 2>&1 && break
  if ! kill -0 "$server_pid" 2>/dev/null; then
    safe_server_log >&2
    exit 1
  fi
  sleep .1
done
ip netns exec "$CNS" "$WT" ping >/dev/null 2>&1 || {
  echo "Wiretap API did not become reachable" >&2
  safe_server_log >&2
  exit 1
}

cat >"$RUN/topology.properties" <<EOF
wiretap.version=$($WT --version 2>/dev/null | head -n1)
wiretap.routes=$ROUTES
wiretap.clientE2EE=$CALLER_E2EE
wiretap.controlApi=::2
topology.preflight=preflight.properties
underlay=$UL_HOST/24<->$UL_CLIENT/24
signaling.serverSide=$SIG_HOST/24<->$SIG_SERVER/24
signaling.responseRouting=$RESPONSE_ROUTING
tty.media=$MEDIA_HOST/24<->$MEDIA_SERVER/24
tty.rtp.payloadType=0
tty.rtp.clockRate=8000
tty.rtp.samplesPerPacket=160
tty.rtp.packetizationMs=20
tty.jitter.delayIndex=$DELAY_INDEX
tty.jitter.delayMs=$DELAY_MS
EOF
ip netns exec "$CNS" ip route show >"$RUN/caller-routes.txt"
ip netns exec "$SNS" ip route show >"$RUN/callee-routes.txt"
ip netns exec "$CNS" "$WT" status >"$RUN/wiretap-status.txt"

CASE="$RUN/jitter-reorder-recovery"
cp "$PCMU/minimodem-to-spandsp.rtpseq" "$CASE/pre-route.rtpseq"
printf '%s\n' "$DELAY_INDEX" >"$CASE/delayed-index.txt"
printf '%s\n' "$DELAY_MS" >"$CASE/delay-ms.txt"
COUNT=$(python3 "$ROOT/scripts/tty_rtp_udp.py" count "$CASE/pre-route.rtpseq")
READY="$CASE/receiver.ready"

ip netns exec "$SNS" python3 "$ROOT/scripts/tty_rtp_udp.py" receive \
  "$CASE/post-route.rtpseq" \
  --bind "$MEDIA_SERVER" \
  --port "$MEDIA_PORT" \
  --expected-count "$COUNT" \
  --timeout-seconds 20 \
  --ready-file "$READY" \
  >"$CASE/receiver.json" \
  2>"$CASE/receiver.stderr.txt" &
recv_pid=$!

for _ in $(seq 1 100); do
  [[ -f "$READY" ]] && break
  kill -0 "$recv_pid" 2>/dev/null || { cat "$CASE/receiver.stderr.txt" >&2; exit 1; }
  sleep .05
done
[[ -f "$READY" ]] || { echo "jitter UDP receiver did not become ready" >&2; exit 1; }

ip netns exec "$CNS" python3 "$ROOT/scripts/tty_rtp_udp.py" send \
  "$CASE/pre-route.rtpseq" \
  --target "$MEDIA_SERVER" \
  --port "$MEDIA_PORT" \
  --interval-ms 20 \
  --delay-index "$DELAY_INDEX=$DELAY_MS" \
  >"$CASE/sender.json" \
  2>"$CASE/sender.stderr.txt"

wait "$recv_pid"
recv_pid=""
rm -f "$READY"

set +e
python3 "$ROOT/scripts/tty_rtp_udp.py" reconstruct \
  "$CASE/post-route.rtpseq" \
  "$CASE/raw-arrival-order.wav" \
  >"$CASE/raw-reconstruct.json" \
  2>"$CASE/raw-reconstruct.stderr.txt"
RAW_EXIT=$?
set -e
printf '%s\n' "$RAW_EXIT" >"$CASE/raw-reconstruct.exit-code.txt"
if (( RAW_EXIT == 0 )); then
  echo "arrival-order reconstruction unexpectedly accepted reordered RTP" >&2
  exit 1
fi

python3 "$ROOT/scripts/tty_rtp_udp.py" resequence \
  "$CASE/post-route.rtpseq" \
  "$CASE/resequenced.rtpseq" \
  >"$CASE/resequence.json"

python3 "$ROOT/scripts/tty_rtp_udp.py" reconstruct \
  "$CASE/resequenced.rtpseq" \
  "$CASE/after-resequence.wav" \
  >"$CASE/reconstruct.json"

"$BIN_DIR/tty-v18-file" decode "$CASE/after-resequence.wav" \
  >"$CASE/decoded.txt" \
  2>"$CASE/decoder.stderr.txt"

sha256sum \
  "$CASE/pre-route.rtpseq" \
  "$CASE/post-route.rtpseq" \
  "$CASE/resequenced.rtpseq" \
  "$CASE/after-resequence.wav" \
  >"$CASE/media.sha256"

safe_server_log >"$RUN/wiretap-server.log"
cd "$ROOT"
python3 scripts/reduce_tty_v18_jitter_reorder.py "$RUN"

(
  cd "$RUN"
  required=(
    preflight.properties
    topology.properties
    caller-routes.txt
    callee-routes.txt
    wiretap-status.txt
    wiretap-server.log
    source.txt
    tty-jitter-validation.json
    jitter-reorder-recovery/pre-route.rtpseq
    jitter-reorder-recovery/post-route.rtpseq
    jitter-reorder-recovery/resequenced.rtpseq
    jitter-reorder-recovery/delayed-index.txt
    jitter-reorder-recovery/delay-ms.txt
    jitter-reorder-recovery/sender.json
    jitter-reorder-recovery/receiver.json
    jitter-reorder-recovery/raw-reconstruct.exit-code.txt
    jitter-reorder-recovery/raw-reconstruct.stderr.txt
    jitter-reorder-recovery/resequence.json
    jitter-reorder-recovery/after-resequence.wav
    jitter-reorder-recovery/decoded.txt
  )
  for artifact in "${required[@]}"; do test -f "$artifact"; done
  sha256sum "${required[@]}" >bundle.manifest.sha256
)

cat "$RUN/tty-jitter-validation.json"
