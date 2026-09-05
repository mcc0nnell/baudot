#!/usr/bin/env bash
set -euo pipefail

scenario=${1:-}
if [[ "$scenario" != "001" && "$scenario" != "002" ]]; then
  echo "usage: $0 <001|002>" >&2
  exit 64
fi

: "${WIRETAP_ENDPOINT:?set WIRETAP_ENDPOINT to the remote Wiretap endpoint host:port}"
WIRETAP_BIN=${WIRETAP_BIN:-wiretap}
SIGNALING_ROUTES=${BAUDOT_SIGNALING_ROUTES:-10.77.10.0/24}
MEDIA_ROUTES=${BAUDOT_MEDIA_ROUTES:-10.77.20.0/24}
WORKDIR=${BAUDOT_WIRETAP_DIR:-target/wiretap/$scenario}

mkdir -p "$WORKDIR"
cd "$WORKDIR"

case "$scenario" in
  001)
    routes="$SIGNALING_ROUTES,$MEDIA_ROUTES"
    ;;
  002)
    routes="$SIGNALING_ROUTES"
    ;;
esac

"$WIRETAP_BIN" configure \
  --endpoint "$WIRETAP_ENDPOINT" \
  --routes "$routes"

cat <<EOF
Baudot Wiretap scenario $scenario configured.
Routes: $routes

Next install the generated client configs with wg-quick and run the matching
caller/callee probes on opposite sides of the Wiretap path. Baudot does not
install privileged WireGuard interfaces or deploy the remote server for you.
EOF
