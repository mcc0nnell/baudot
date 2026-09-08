#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python -m scripts.validate_vrs_public_matrix
python scripts/validate_part64_registration_numbering.py
python scripts/resolve_rue_registration_route.py

discovery="target/evidence/RUE-REG-001/discovery.json"
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
  echo "RUE-REG-001 execution escaped loopback TLS boundary" >&2
  exit 1
fi

keystore_dir="target/evidence/RUE-REG-001/ephemeral-tls"
keystore="$keystore_dir/provider-a.p12"
storepass="baudot-test-only"
rm -rf "$keystore_dir" "target/evidence/RUE-REG-001/tls-register-v1"
mkdir -p "$keystore_dir"

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
BAUDOT_RUE_REG_TRANSPORT="$transport" \
  timeout --signal=TERM --kill-after=5s 45s \
  mvn -B -ntp -q \
    -Dexec.mainClass=org.mcc0nnell.baudot.harness.RueRegistrationTlsProbe \
    exec:java

# The private key and synthetic credential container are harness plumbing, not evidence.
rm -rf "$keystore_dir"

# Prove bounded outbound-flow behavior independently; markers alone remain
# insufficient until Require: outbound, keepalive, flow loss, replacement
# registration, and inbound delivery on the replacement flow are observed.
bash scripts/run-rue-outbound-flow.sh

bash scripts/run-rue-provider-selection.sh
bash scripts/run-rue-one-stage-dial-around.sh
python -m scripts.validate_rue_dial_execution
python -m scripts.validate_vrs_registration_route_chain
python -m scripts.validate_vrs_outbound_route_chain

cat target/evidence/VRS-OUTBOUND-ROUTE-CHAIN/summary.json
