#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM_ROOT="${1:?usage: run_fineract_consumer_machine_live.sh UPSTREAM_ROOT [EVIDENCE_DIR]}"
EVIDENCE_DIR="${2:-/tmp/baudot-fineract-consumer-machine-live}"
CONSUMER="$UPSTREAM_ROOT/consumer"
UPSTREAM_COMMIT="58eacf7338126aa0de2b2a2ef70319f45d403fbf"

mkdir -p "$EVIDENCE_DIR"
printf '{"schema":"baudot.fineract-consumer-machine-live-startup@1","status":"STARTING","upstreamCommit":"%s"}\n' \
  "$UPSTREAM_COMMIT" > "$EVIDENCE_DIR/startup.json"

require() {
  local name="$1"
  shift
  if ! "$@"; then
    echo "FAIL $name" >&2
    exit 1
  fi
  echo "PASS $name"
}

require_eq() {
  local name="$1" expected="$2" actual="$3"
  if [ "$expected" != "$actual" ]; then
    echo "FAIL $name: expected '$expected', got '$actual'" >&2
    exit 1
  fi
  echo "PASS $name"
}

sha256_file() {
  sha256sum "$1" | awk '{print $1}'
}

count_requests() {
  awk '/"(GET|POST|PUT|DELETE) / { n++ } END { print n+0 }' "$1"
}

require "pinned Consumer checkout is present" test -f "$CONSUMER/compose.yaml"
require_eq "Consumer source pin" "$UPSTREAM_COMMIT" "$(git -C "$UPSTREAM_ROOT" rev-parse HEAD)"

cp "$ROOT/interop/fineract-consumer/live/fineract-proxy.conf" "$CONSUMER/baudot-fineract-proxy.conf"
cp "$ROOT/interop/fineract-consumer/live/compose.override.yaml" "$CONSUMER/baudot-machine-proxy.override.yaml"

cd "$CONSUMER"
./scripts/generate-dev-jwt-key.sh

compose=(docker compose -f compose.yaml -f baudot-machine-proxy.override.yaml)
cleanup() {
  local rc=$?
  "${compose[@]}" ps -a >"$EVIDENCE_DIR/compose-ps.txt" 2>&1 || true
  docker inspect fineract-proxy >"$EVIDENCE_DIR/fineract-proxy-inspect.json" 2>&1 || true
  docker logs fineract-proxy >"$EVIDENCE_DIR/fineract-proxy-container.log" 2>&1 || true
  "${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  exit "$rc"
}
trap cleanup EXIT

"${compose[@]}" up -d --build --wait
printf '{"schema":"baudot.fineract-consumer-machine-live-startup@1","status":"STACK_HEALTHY","upstreamCommit":"%s"}\n' \
  "$UPSTREAM_COMMIT" > "$EVIDENCE_DIR/startup.json"

./scripts/seed-demo.sh | tee "$EVIDENCE_DIR/seed-demo.log"

# Reuse the exact pinned upstream demo identities, HTTP helpers, OAuth2 flow,
# consent ceremony, and Mailpit-backed 2FA without executing either script main.
source <(sed '$d' ./scripts/seed-demo.sh)
source <(sed '$d' ./scripts/seed-openbanking.sh)

preflight
login_customer
PROVIDER_ACCESS_TOKEN="$RESULT"
require "provider session established" test -n "$PROVIDER_ACCESS_TOKEN"

PROVIDER_BEFORE="$EVIDENCE_DIR/provider-before-revoke.json"
PROVIDER_BEFORE_STATUS="$(curl -sS -o "$PROVIDER_BEFORE" -w '%{http_code}' \
  -H "Cookie: ${ACCESS_TOKEN_COOKIE_NAME}=$PROVIDER_ACCESS_TOKEN" \
  -H "$DEVICE_FINGERPRINT_HEADER: $DEVICE_FINGERPRINT" \
  "$BFF_BASE/savings")"
require_eq "provider read succeeds before machine consent ceremony" "200" "$PROVIDER_BEFORE_STATUS"

# Build a real TPP consent and authorization-code + PKCE token using the pinned
# upstream flow. Token values remain process-local and are never written to evidence.
tpp_token
TPP_CLIENT_CREDENTIALS_TOKEN="$RESULT"
create_consent "$TPP_CLIENT_CREDENTIALS_TOKEN"
CONSENT_ID="$RESULT"
request_authorization "$PROVIDER_ACCESS_TOKEN" "$CONSENT_ID"
approve_consent "$PROVIDER_ACCESS_TOKEN"
AUTHORIZATION_CODE="$RESULT"
exchange_code "$AUTHORIZATION_CODE"
MACHINE_ACCESS_TOKEN="$OB_ACCESS_TOKEN"
require "machine access token established" test -n "$MACHINE_ACCESS_TOKEN"
require "machine token scope includes accounts.read" bash -c 'case "$1" in *openbanking:accounts.read*) exit 0;; *) exit 1;; esac' _ "$OB_TOKEN_SCOPE"

MACHINE_BEFORE="$EVIDENCE_DIR/machine-accounts-before-revoke.json"
MACHINE_BEFORE_STATUS="$(curl -sS -o "$MACHINE_BEFORE" -w '%{http_code}' \
  -H "Authorization: Bearer $MACHINE_ACCESS_TOKEN" \
  "$BFF_BASE/openbanking/accounts")"
require_eq "consented machine can list provider accounts" "200" "$MACHINE_BEFORE_STATUS"

MACHINE_ACCOUNT_ID="$(jq -r '.[0].accountId // empty' "$MACHINE_BEFORE")"
require "machine account list contains an account" test -n "$MACHINE_ACCOUNT_ID"

MACHINE_BALANCES="$EVIDENCE_DIR/machine-balances-before-revoke.json"
MACHINE_BALANCES_STATUS="$(curl -sS -o "$MACHINE_BALANCES" -w '%{http_code}' \
  -H "Authorization: Bearer $MACHINE_ACCESS_TOKEN" \
  "$BFF_BASE/openbanking/accounts/$MACHINE_ACCOUNT_ID/balances")"
require_eq "consented machine can read account balances" "200" "$MACHINE_BALANCES_STATUS"

# Credential substitution controls: neither token is accepted on the other's
# resource chain.
MACHINE_ON_CONSUMER="$EVIDENCE_DIR/machine-token-on-consumer.json"
MACHINE_ON_CONSUMER_STATUS="$(curl -sS -o "$MACHINE_ON_CONSUMER" -w '%{http_code}' \
  -H "Authorization: Bearer $MACHINE_ACCESS_TOKEN" \
  "$BFF_BASE/savings")"
require_eq "machine bearer is unauthenticated on consumer surface" "401" "$MACHINE_ON_CONSUMER_STATUS"

PROVIDER_ON_MACHINE="$EVIDENCE_DIR/provider-token-on-machine.json"
PROVIDER_ON_MACHINE_STATUS="$(curl -sS -o "$PROVIDER_ON_MACHINE" -w '%{http_code}' \
  -H "Authorization: Bearer $PROVIDER_ACCESS_TOKEN" \
  "$BFF_BASE/openbanking/accounts")"
require_eq "provider token is unauthenticated on machine surface" "401" "$PROVIDER_ON_MACHINE_STATUS"

REVOKE_BODY="$EVIDENCE_DIR/consent-revoke.json"
REVOKE_STATUS="$(curl -sS -o "$REVOKE_BODY" -w '%{http_code}' -X POST \
  -H "Cookie: ${ACCESS_TOKEN_COOKIE_NAME}=$PROVIDER_ACCESS_TOKEN" \
  -H "$DEVICE_FINGERPRINT_HEADER: $DEVICE_FINGERPRINT" \
  "$BFF_BASE/openbanking/consents/$CONSENT_ID/revoke")"
require_eq "provider can revoke machine consent" "200" "$REVOKE_STATUS"
REVOKED_STATE="$(jq -r '.status // empty' "$REVOKE_BODY")"
require_eq "revocation response is REVOKED" "REVOKED" "$REVOKED_STATE"

# Measure the same still-issued machine token after consent revocation. The
# consent check must reject before delegation to Fineract.
BEFORE_LOG="$EVIDENCE_DIR/fineract-proxy-before-revoked-read.log"
AFTER_LOG="$EVIDENCE_DIR/fineract-proxy-after-revoked-read.log"
docker logs fineract-proxy >"$BEFORE_LOG" 2>&1
BEFORE_REQUESTS="$(count_requests "$BEFORE_LOG")"

MACHINE_AFTER="$EVIDENCE_DIR/machine-accounts-after-revoke.json"
MACHINE_AFTER_STATUS="$(curl -sS -o "$MACHINE_AFTER" -w '%{http_code}' \
  -H "Authorization: Bearer $MACHINE_ACCESS_TOKEN" \
  "$BFF_BASE/openbanking/accounts")"
require_eq "same machine token is denied after consent revocation" "403" "$MACHINE_AFTER_STATUS"

docker logs fineract-proxy >"$AFTER_LOG" 2>&1
AFTER_REQUESTS="$(count_requests "$AFTER_LOG")"
require_eq "revoked machine read creates no downstream Fineract request" "$BEFORE_REQUESTS" "$AFTER_REQUESTS"

PROVIDER_AFTER="$EVIDENCE_DIR/provider-after-revoke.json"
PROVIDER_AFTER_STATUS="$(curl -sS -o "$PROVIDER_AFTER" -w '%{http_code}' \
  -H "Cookie: ${ACCESS_TOKEN_COOKIE_NAME}=$PROVIDER_ACCESS_TOKEN" \
  -H "$DEVICE_FINGERPRINT_HEADER: $DEVICE_FINGERPRINT" \
  "$BFF_BASE/savings")"
require_eq "provider session remains usable after machine consent revocation" "200" "$PROVIDER_AFTER_STATUS"

# Audit delivery is asynchronous in Consumer-Facing. Preserve the query result
# when available, but do not make its timing part of the synchronous authority proof.
AUDIT_BODY="$EVIDENCE_DIR/provider-audit-events.json"
AUDIT_STATUS="$(curl -sS -o "$AUDIT_BODY" -w '%{http_code}' \
  -H "Cookie: ${ACCESS_TOKEN_COOKIE_NAME}=$PROVIDER_ACCESS_TOKEN" \
  -H "$DEVICE_FINGERPRINT_HEADER: $DEVICE_FINGERPRINT" \
  "$BFF_BASE/audit/events" || true)"
if [ "$AUDIT_STATUS" != "200" ]; then
  rm -f "$AUDIT_BODY"
fi

jq -n \
  --arg schema "baudot.fineract-consumer-machine-live-evidence@1" \
  --arg repository "apache/fineract-consumer-facing" \
  --arg commit "$UPSTREAM_COMMIT" \
  --arg consentId "$CONSENT_ID" \
  --arg tppClientId "$TPP_CLIENT_ID" \
  --arg tokenPurpose "openbanking" \
  --arg tokenScope "$OB_TOKEN_SCOPE" \
  --arg machineAccountId "$MACHINE_ACCOUNT_ID" \
  --arg providerBeforeStatus "$PROVIDER_BEFORE_STATUS" \
  --arg machineBeforeStatus "$MACHINE_BEFORE_STATUS" \
  --arg machineBalancesStatus "$MACHINE_BALANCES_STATUS" \
  --arg machineOnConsumerStatus "$MACHINE_ON_CONSUMER_STATUS" \
  --arg providerOnMachineStatus "$PROVIDER_ON_MACHINE_STATUS" \
  --arg revokeStatus "$REVOKE_STATUS" \
  --arg revokedState "$REVOKED_STATE" \
  --arg machineAfterStatus "$MACHINE_AFTER_STATUS" \
  --arg providerAfterStatus "$PROVIDER_AFTER_STATUS" \
  --arg beforeRequests "$BEFORE_REQUESTS" \
  --arg afterRequests "$AFTER_REQUESTS" \
  --arg auditStatus "$AUDIT_STATUS" \
  --arg providerBeforeSha256 "$(sha256_file "$PROVIDER_BEFORE")" \
  --arg machineBeforeSha256 "$(sha256_file "$MACHINE_BEFORE")" \
  --arg balancesSha256 "$(sha256_file "$MACHINE_BALANCES")" \
  --arg revokeSha256 "$(sha256_file "$REVOKE_BODY")" \
  --arg machineAfterSha256 "$(sha256_file "$MACHINE_AFTER")" \
  --arg providerAfterSha256 "$(sha256_file "$PROVIDER_AFTER")" \
  --arg proxyAfterSha256 "$(sha256_file "$AFTER_LOG")" \
  --arg seedLogSha256 "$(sha256_file "$EVIDENCE_DIR/seed-demo.log")" \
  '{
    schema: $schema,
    upstream: {repository: $repository, commit: $commit},
    providerActor: {
      kind: "synthetic-provider-user",
      sessionTokenPersisted: false,
      beforeMachineRevocationStatus: ($providerBeforeStatus|tonumber),
      afterMachineRevocationStatus: ($providerAfterStatus|tonumber)
    },
    machineActor: {
      kind: "synthetic-third-party-system",
      tppClientId: $tppClientId,
      tokenPurpose: $tokenPurpose,
      tokenScope: $tokenScope,
      tokenPersisted: false,
      consentId: $consentId,
      accountId: $machineAccountId,
      accountsBeforeRevocationStatus: ($machineBeforeStatus|tonumber),
      balancesBeforeRevocationStatus: ($machineBalancesStatus|tonumber),
      sameTokenAfterRevocationStatus: ($machineAfterStatus|tonumber)
    },
    credentialSeparation: {
      machineBearerOnConsumerSurface: ($machineOnConsumerStatus|tonumber),
      providerTokenOnMachineSurface: ($providerOnMachineStatus|tonumber)
    },
    consentRevocation: {
      status: ($revokeStatus|tonumber),
      resultingState: $revokedState,
      proxyRequestsBeforeDeniedRead: ($beforeRequests|tonumber),
      proxyRequestsAfterDeniedRead: ($afterRequests|tonumber),
      downstreamRequestDelta: (($afterRequests|tonumber)-($beforeRequests|tonumber))
    },
    auditQueryStatus: ($auditStatus|tonumber?),
    evidenceHashes: {
      providerBefore: $providerBeforeSha256,
      machineBefore: $machineBeforeSha256,
      balancesBefore: $balancesSha256,
      revoke: $revokeSha256,
      machineAfter: $machineAfterSha256,
      providerAfter: $providerAfterSha256,
      proxyAfter: $proxyAfterSha256,
      seedLog: $seedLogSha256
    },
    claimBoundary: {
      trsProgramAuthority: "NOT_DERIVED",
      claimAuthority: "NOT_DERIVED",
      paymentAuthority: "NOT_DERIVED",
      baudotOperatorAuthority: "NOT_DERIVED",
      productionTppSuitabilityClaimed: false,
      regulatoryComplianceClaimed: false
    }
  }' > "$EVIDENCE_DIR/evidence.json"

echo "Fineract Consumer machine live boundary: PASS"
