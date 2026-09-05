#!/usr/bin/env bash
set -euo pipefail

export LC_ALL=C

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MESSAGE="${BAUDOT_TTY_MESSAGE:-HELLO GA}"
EVIDENCE_DIR="${BAUDOT_TTY_EVIDENCE_DIR:-target/evidence/tty-v18-cross-oracle}"
BIN_DIR="${BAUDOT_TTY_BIN_DIR:-target/tty-v18}"
SPANDSP_SOURCE_COMMIT="${BAUDOT_SPANDSP_SOURCE_COMMIT:-unverified-local-install}"
MINIMODEM_SOURCE_COMMIT="${BAUDOT_MINIMODEM_SOURCE_COMMIT:-unverified-local-install}"

mkdir -p "$EVIDENCE_DIR" "$BIN_DIR"

for tool in cc minimodem pkg-config python3 sha256sum; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "missing required tool: $tool" >&2
    exit 2
  }
done

pkg-config --exists spandsp sndfile || {
  echo "pkg-config could not resolve spandsp and sndfile" >&2
  exit 2
}

CFLAGS="$(pkg-config --cflags spandsp sndfile)"
LIBS="$(pkg-config --libs spandsp sndfile)"

# shellcheck disable=SC2086
cc -std=c11 -Wall -Wextra -Werror $CFLAGS \
  interop/tty/tty_v18_roundtrip.c \
  -o "$BIN_DIR/tty-v18-roundtrip" \
  $LIBS

# shellcheck disable=SC2086
cc -std=c11 -Wall -Wextra -Werror $CFLAGS \
  interop/tty/tty_v18_file.c \
  -o "$BIN_DIR/tty-v18-file" \
  $LIBS

printf '%s' "$MESSAGE" > "$EVIDENCE_DIR/source.txt"
pkg-config --modversion spandsp > "$EVIDENCE_DIR/spandsp.version.txt"
minimodem --version | head -n 1 > "$EVIDENCE_DIR/minimodem.version.txt"
cat > "$EVIDENCE_DIR/pins.env" <<EOF
spandsp_source_commit=$SPANDSP_SOURCE_COMMIT
minimodem_source_commit=$MINIMODEM_SOURCE_COMMIT
EOF

{
  printf 'tty-v18-roundtrip %q\n' "$MESSAGE"
  printf 'minimodem --tx --quiet --samplerate 8000 --file minimodem-generated.wav tdd < source.txt\n'
  printf 'tty-v18-file decode minimodem-generated.wav\n'
  printf 'tty-v18-file encode spandsp-generated.wav %q\n' "$MESSAGE"
  printf 'minimodem --rx --quiet --samplerate 8000 --file spandsp-generated.wav tdd\n'
  printf 'python3 scripts/reduce_tty_v18_cross_oracle.py\n'
} > "$EVIDENCE_DIR/commands.txt"

"$BIN_DIR/tty-v18-roundtrip" "$MESSAGE" \
  > "$EVIDENCE_DIR/spandsp-loopback.txt" \
  2> "$EVIDENCE_DIR/spandsp-loopback.stderr.txt"

minimodem --tx --quiet --samplerate 8000 \
  --file "$EVIDENCE_DIR/minimodem-generated.wav" \
  tdd \
  < "$EVIDENCE_DIR/source.txt" \
  > "$EVIDENCE_DIR/minimodem-tx.stdout.txt" \
  2> "$EVIDENCE_DIR/minimodem-tx.stderr.txt"

"$BIN_DIR/tty-v18-file" decode \
  "$EVIDENCE_DIR/minimodem-generated.wav" \
  > "$EVIDENCE_DIR/decoded-by-spandsp.txt" \
  2> "$EVIDENCE_DIR/spandsp-decode.stderr.txt"

"$BIN_DIR/tty-v18-file" encode \
  "$EVIDENCE_DIR/spandsp-generated.wav" \
  "$MESSAGE" \
  > "$EVIDENCE_DIR/spandsp-encode.stdout.txt" \
  2> "$EVIDENCE_DIR/spandsp-encode.stderr.txt"

minimodem --rx --quiet --samplerate 8000 \
  --file "$EVIDENCE_DIR/spandsp-generated.wav" \
  tdd \
  > "$EVIDENCE_DIR/decoded-by-minimodem.txt" \
  2> "$EVIDENCE_DIR/minimodem-rx.stderr.txt"

sha256sum \
  "$EVIDENCE_DIR/minimodem-generated.wav" \
  "$EVIDENCE_DIR/spandsp-generated.wav" \
  > "$EVIDENCE_DIR/audio.sha256"

python3 scripts/reduce_tty_v18_cross_oracle.py "$EVIDENCE_DIR"
