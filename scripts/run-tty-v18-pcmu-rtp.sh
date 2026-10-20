#!/usr/bin/env bash
set -euo pipefail

export LC_ALL=C

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BASELINE_DIR="${BAUDOT_TTY_BASELINE_DIR:-target/evidence/tty-v18-cross-oracle}"
EVIDENCE_DIR="${BAUDOT_TTY_RTP_EVIDENCE_DIR:-target/evidence/tty-v18-pcmu-rtp}"
BIN_DIR="${BAUDOT_TTY_BIN_DIR:-target/tty-v18}"

if [[ ! -f "$BASELINE_DIR/minimodem-generated.wav" ||
      ! -f "$BASELINE_DIR/spandsp-generated.wav" ||
      ! -x "$BIN_DIR/tty-v18-file" ]]; then
  bash scripts/run-tty-v18-cross-oracle.sh
fi

mkdir -p "$EVIDENCE_DIR"

cp "$BASELINE_DIR/source.txt" "$EVIDENCE_DIR/source.txt"
for name in pins.env spandsp.version.txt minimodem.version.txt; do
  if [[ -f "$BASELINE_DIR/$name" ]]; then
    cp "$BASELINE_DIR/$name" "$EVIDENCE_DIR/$name"
  fi
done

python3 scripts/tty_pcmu_rtp.py \
  "$BASELINE_DIR/minimodem-generated.wav" \
  "$EVIDENCE_DIR/minimodem-to-spandsp.rtpseq" \
  "$EVIDENCE_DIR/minimodem-after-pcmu.wav"

"$BIN_DIR/tty-v18-file" decode \
  "$EVIDENCE_DIR/minimodem-after-pcmu.wav" \
  > "$EVIDENCE_DIR/decoded-by-spandsp.txt" \
  2> "$EVIDENCE_DIR/spandsp-decode.stderr.txt"

python3 scripts/tty_pcmu_rtp.py \
  "$BASELINE_DIR/spandsp-generated.wav" \
  "$EVIDENCE_DIR/spandsp-to-minimodem.rtpseq" \
  "$EVIDENCE_DIR/spandsp-after-pcmu.wav"

minimodem --rx --quiet --samplerate 8000 \
  --file "$EVIDENCE_DIR/spandsp-after-pcmu.wav" \
  tdd \
  > "$EVIDENCE_DIR/decoded-by-minimodem.txt" \
  2> "$EVIDENCE_DIR/minimodem-rx.stderr.txt"

{
  printf 'python3 scripts/tty_pcmu_rtp.py minimodem-generated.wav minimodem-to-spandsp.rtpseq minimodem-after-pcmu.wav\n'
  printf 'tty-v18-file decode minimodem-after-pcmu.wav\n'
  printf 'python3 scripts/tty_pcmu_rtp.py spandsp-generated.wav spandsp-to-minimodem.rtpseq spandsp-after-pcmu.wav\n'
  printf 'minimodem --rx --quiet --samplerate 8000 --file spandsp-after-pcmu.wav tdd\n'
  printf 'python3 scripts/reduce_tty_v18_pcmu_rtp.py\n'
} > "$EVIDENCE_DIR/commands.txt"

sha256sum \
  "$EVIDENCE_DIR/minimodem-to-spandsp.rtpseq" \
  "$EVIDENCE_DIR/spandsp-to-minimodem.rtpseq" \
  "$EVIDENCE_DIR/minimodem-after-pcmu.wav" \
  "$EVIDENCE_DIR/spandsp-after-pcmu.wav" \
  > "$EVIDENCE_DIR/media.sha256"

python3 scripts/reduce_tty_v18_pcmu_rtp.py "$EVIDENCE_DIR"
