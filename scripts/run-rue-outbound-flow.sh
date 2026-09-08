#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

discovery="target/evidence/RUE-REG-001/discovery.json"
if [[ ! -f "$discovery" ]]; then
  python scripts/resolve_rue_registration_route.py
fi

readarray -t route < <(python - "$discovery" <<'PY'
import json
import sys
from pathlib import Path

value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if value.get("schema") != "baudot.rue-registration-discovery-evidence@1":
    raise SystemExit("unexpected discovery evidence schema")
print(value["resolvedAddress"])
print(value["srvPort"])
print(value["selectedTransport"])
PY
)

host="${route[0]}"
port="${route[1]}"
transport="${route[2]}"

if [[ "$host" != "127.0.0.1" || "$transport" != "tls" ]]; then
  echo "RUE outbound-flow execution escaped loopback TLS boundary" >&2
  exit 1
fi

keystore_dir="target/evidence/RUE-REG-001/ephemeral-outbound-tls"
keystore="$keystore_dir/provider-a.p12"
storepass="baudot-test-only"
rm -rf "$keystore_dir" \
  "target/evidence/RUE-REG-001/outbound-flow-recovery-v1"
mkdir -p "$keystore_dir"

cleanup() {
  rm -rf "$keystore_dir"
}
trap cleanup EXIT

keytool -genkeypair \
  -alias provider-a \
  -keyalg RSA \
  -keysize 2048 \
  -storetype PKCS12 \
  -keystore "$keystore" \
  -storepass "$storepass" \
  -keypass "$storepass" \
  -dname "CN=provider-a.example,OU=Baudot Synthetic,O=Baudot,L=Test,ST=Test,C=US" \
  -ext "SAN=dns:provider-a.example,ip:127.0.0.1" \
  -validity 2 \
  -noprompt >/dev/null 2>&1

BAUDOT_RUE_REG_KEYSTORE="$keystore" \
BAUDOT_RUE_REG_KEYSTORE_PASSWORD="$storepass" \
BAUDOT_RUE_REG_HOST="$host" \
BAUDOT_RUE_REG_PORT="$port" \
  timeout --signal=TERM --kill-after=5s 45s \
  mvn -B -ntp -q \
    -Dexec.mainClass=org.mcc0nnell.baudot.harness.RueOutboundFlowProbe \
    exec:java

python -m scripts.validate_rue_outbound_flow
cat \
  target/evidence/RUE-REG-001/outbound-flow-recovery-v1/outbound-flow-proof/result.properties
