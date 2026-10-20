#!/usr/bin/env bash
set -euo pipefail

[[ ${EUID:-$(id -u)} -eq 0 ]] || exec sudo -E bash "$0" "$@"

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
WT=${WIRETAP_BIN:-wiretap}
CNS=${BAUDOT_CALLER_NS:-bdt-tty-caller}
SNS=${BAUDOT_CALLEE_NS:-bdt-tty-callee}
WORK=${BAUDOT_WIRETAP_DIR:-$ROOT/target/wiretap-routed/tty-v18}
EVIDENCE=${BAUDOT_EVIDENCE_DIR:-$ROOT/target/evidence-routed}
CORR=${BAUDOT_CORRELATION:-$(python3 -c 'import uuid; print(uuid.uuid4())')}
RUN="$EVIDENCE/tty-v18-wiretap/$CORR"
BASELINE=${BAUDOT_TTY_BASELINE_DIR:-$ROOT/target/evidence/tty-v18-cross-oracle}
PCMU=${BAUDOT_TTY_RTP_EVIDENCE_DIR:-$ROOT/target/evidence/tty-v18-pcmu-rtp}
BIN_DIR=${BAUDOT_TTY_BIN_DIR:-$ROOT/target/tty-v18}
MINIMODEM_BIN=${BAUDOT_MINIMODEM_BIN:-minimodem}

UL_HOST=198.18.2.1
UL_CLIENT=198.18.2.2
SIG_HOST=10.78.10.1
SIG_SERVER=10.78.10.2
MEDIA_HOST=10.78.20.1
MEDIA_SERVER=10.78.20.2
WT_PORT=51820
SIG_NET=10.78.10.0/24
MEDIA_NET=10.78.20.0/24
ROUTES="$SIG_NET,$MEDIA_NET"
RESPONSE_ROUTING=rfc3581-rport-over-transparent-flow

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
  ip link del bdt-tty-ul-h 2>/dev/null
  ip link del bdt-tty-sig-h 2>/dev/null
  ip link del bdt-tty-med-h 2>/dev/null
  rm -rf "$WORK"
  [[ -n "${SUDO_UID:-}" && -d "$EVIDENCE" ]] && chown -R "${SUDO_UID}:${SUDO_GID}" "$EVIDENCE" 2>/dev/null
}

required_inputs=(
  "$BASELINE/source.txt"
  "$BASELINE/minimodem-generated.wav"
  "$BASELINE/spandsp-generated.wav"
  "$PCMU/minimodem-to-spandsp.rtpseq"
  "$PCMU/spandsp-to-minimodem.rtpseq"
  "$BIN_DIR/tty-v18-file"
)
for path in "${required_inputs[@]}"; do
  [[ -e "$path" ]] || { echo "missing routed TTY input: $path" >&2; exit 2; }
done
[[ -x "$MINIMODEM_BIN" ]] || { echo "minimodem executable unavailable: $MINIMODEM_BIN" >&2; exit 2; }

rm -rf "$WORK"
mkdir -p "$WORK" "$RUN/inputs"
cp "$BASELINE/source.txt" "$RUN/source.txt"
cp "$BASELINE/minimodem-generated.wav" "$RUN/inputs/minimodem-generated.wav"
cp "$BASELINE/spandsp-generated.wav" "$RUN/inputs/spandsp-generated.wav"
for name in pins.env spandsp.version.txt minimodem.version.txt; do
  [[ -f "$BASELINE/$name" ]] && cp "$BASELINE/$name" "$RUN/inputs/$name"
done

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
  --host-link bdt-tty-ul-h \
  --host-link bdt-tty-sig-h \
  --host-link bdt-tty-med-h \
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

ip link add bdt-tty-ul-h type veth peer name bdt-tty-ul-c
ip link set bdt-tty-ul-c netns "$CNS"
ip addr add "$UL_HOST/24" dev bdt-tty-ul-h
ip link set bdt-tty-ul-h up
ip -n "$CNS" addr add "$UL_CLIENT/24" dev bdt-tty-ul-c
ip -n "$CNS" link set bdt-tty-ul-c up

ip link add bdt-tty-sig-h type veth peer name bdt-tty-sig-s
ip link set bdt-tty-sig-s netns "$SNS"
ip addr add "$SIG_HOST/24" dev bdt-tty-sig-h
ip link set bdt-tty-sig-h up
ip -n "$SNS" addr add "$SIG_SERVER/24" dev bdt-tty-sig-s
ip -n "$SNS" link set bdt-tty-sig-s up

ip link add bdt-tty-med-h type veth peer name bdt-tty-med-s
ip link set bdt-tty-med-s netns "$SNS"
ip addr add "$MEDIA_HOST/24" dev bdt-tty-med-h
ip link set bdt-tty-med-h up
ip -n "$SNS" addr add "$MEDIA_SERVER/24" dev bdt-tty-med-s
ip -n "$SNS" link set bdt-tty-med-s up

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
EOF
ip netns exec "$CNS" ip route show >"$RUN/caller-routes.txt"
ip netns exec "$SNS" ip route show >"$RUN/callee-routes.txt"
ip netns exec "$CNS" "$WT" status >"$RUN/wiretap-status.txt"

run_case() {
  local name=$1
  local input=$2
  local decoder=$3
  local port=$4
  local drop_index=${5:--1}
  local case_dir="$RUN/$name"
  local ready="$case_dir/receiver.ready"
  local count expected

  mkdir -p "$case_dir"
  cp "$input" "$case_dir/pre-route.rtpseq"
  count=$(python3 "$ROOT/scripts/tty_rtp_udp.py" count "$case_dir/pre-route.rtpseq")
  expected=$count
  if (( drop_index >= 0 )); then
    expected=$((count - 1))
    printf '%s\n' "$drop_index" >"$case_dir/dropped-index.txt"
  fi

  ip netns exec "$SNS" python3 "$ROOT/scripts/tty_rtp_udp.py" receive \
    "$case_dir/post-route.rtpseq" \
    --bind "$MEDIA_SERVER" \
    --port "$port" \
    --expected-count "$expected" \
    --timeout-seconds 20 \
    --ready-file "$ready" \
    >"$case_dir/receiver.json" \
    2>"$case_dir/receiver.stderr.txt" &
  recv_pid=$!

  for _ in $(seq 1 100); do
    [[ -f "$ready" ]] && break
    kill -0 "$recv_pid" 2>/dev/null || { cat "$case_dir/receiver.stderr.txt" >&2; exit 1; }
    sleep .05
  done
  [[ -f "$ready" ]] || { echo "UDP receiver did not become ready for $name" >&2; exit 1; }

  send_args=(
    send "$case_dir/pre-route.rtpseq"
    --target "$MEDIA_SERVER"
    --port "$port"
    --interval-ms 20
  )
  (( drop_index >= 0 )) && send_args+=(--drop-index "$drop_index")
  ip netns exec "$CNS" python3 "$ROOT/scripts/tty_rtp_udp.py" "${send_args[@]}" \
    >"$case_dir/sender.json" \
    2>"$case_dir/sender.stderr.txt"

  wait "$recv_pid"
  recv_pid=""
  rm -f "$ready"

  reconstruct_args=(
    reconstruct "$case_dir/post-route.rtpseq" "$case_dir/after-wiretap.wav"
  )
  (( drop_index >= 0 )) && reconstruct_args+=(--conceal-gaps)
  python3 "$ROOT/scripts/tty_rtp_udp.py" "${reconstruct_args[@]}" >"$case_dir/reconstruct.json"

  if [[ "$decoder" == "spandsp" ]]; then
    if (( drop_index >= 0 )); then
      set +e
      "$BIN_DIR/tty-v18-file" decode "$case_dir/after-wiretap.wav" \
        >"$case_dir/decoded.txt" 2>"$case_dir/decoder.stderr.txt"
      printf '%s\n' "$?" >"$case_dir/decoder.exit-code.txt"
      set -e
    else
      "$BIN_DIR/tty-v18-file" decode "$case_dir/after-wiretap.wav" \
        >"$case_dir/decoded.txt" 2>"$case_dir/decoder.stderr.txt"
      printf '0\n' >"$case_dir/decoder.exit-code.txt"
    fi
  else
    if (( drop_index >= 0 )); then
      set +e
      "$MINIMODEM_BIN" --rx --quiet --samplerate 8000 \
        --file "$case_dir/after-wiretap.wav" tdd \
        >"$case_dir/decoded.txt" 2>"$case_dir/decoder.stderr.txt"
      printf '%s\n' "$?" >"$case_dir/decoder.exit-code.txt"
      set -e
    else
      "$MINIMODEM_BIN" --rx --quiet --samplerate 8000 \
        --file "$case_dir/after-wiretap.wav" tdd \
        >"$case_dir/decoded.txt" 2>"$case_dir/decoder.stderr.txt"
      printf '0\n' >"$case_dir/decoder.exit-code.txt"
    fi
  fi

  sha256sum \
    "$case_dir/pre-route.rtpseq" \
    "$case_dir/post-route.rtpseq" \
    "$case_dir/after-wiretap.wav" \
    >"$case_dir/media.sha256"
}

cd "$ROOT"
run_case \
  minimodem-to-spandsp \
  "$PCMU/minimodem-to-spandsp.rtpseq" \
  spandsp \
  41000
run_case \
  spandsp-to-minimodem \
  "$PCMU/spandsp-to-minimodem.rtpseq" \
  minimodem \
  41002
run_case \
  drop-one-negative-control \
  "$PCMU/minimodem-to-spandsp.rtpseq" \
  spandsp \
  41004 \
  20

safe_server_log >"$RUN/wiretap-server.log"
python3 scripts/reduce_tty_v18_wiretap_udp.py "$RUN"

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
    tty-wiretap-validation.json
    minimodem-to-spandsp/pre-route.rtpseq
    minimodem-to-spandsp/post-route.rtpseq
    minimodem-to-spandsp/after-wiretap.wav
    minimodem-to-spandsp/decoded.txt
    spandsp-to-minimodem/pre-route.rtpseq
    spandsp-to-minimodem/post-route.rtpseq
    spandsp-to-minimodem/after-wiretap.wav
    spandsp-to-minimodem/decoded.txt
    drop-one-negative-control/pre-route.rtpseq
    drop-one-negative-control/post-route.rtpseq
    drop-one-negative-control/dropped-index.txt
    drop-one-negative-control/after-wiretap.wav
    drop-one-negative-control/decoded.txt
  )
  for artifact in "${required[@]}"; do test -f "$artifact"; done
  sha256sum "${required[@]}" >bundle.manifest.sha256
)

cat "$RUN/tty-wiretap-validation.json"
