#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM_ROOT="${1:?usage: run_fineract_consumer_provider_live.sh UPSTREAM_ROOT [EVIDENCE_DIR]}"
EVIDENCE_DIR="${2:-/tmp/baudot-fineract-consumer-provider-live}"
CONSUMER="$UPSTREAM_ROOT/consumer"
UPSTREAM_COMMIT="58eacf7338126aa0de2b2a2ef70319f45d403fbf"
CROSS_PROVIDER_EXTERNAL_ID="demo-client-4"

mkdir -p "$EVIDENCE_DIR"
printf '{"schema":"baudot.fineract-consumer-provider-live-startup@1","status":"STARTING","upstreamCommit":"%s"}\n' \
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

count_path_hits() {
  local file="$1" path="$2"
  awk -v path="$path" 'index($0, path) { n++ } END { print n+0 }' "$file"
}

require "pinned Consumer checkout is present" test -f "$CONSUMER/compose.yaml"
require_eq "Consumer source pin" "$UPSTREAM_COMMIT" "$(git -C "$UPSTREAM_ROOT" rev-parse HEAD)"

cp "$ROOT/interop/fineract-consumer/live/fineract-proxy.conf" "$CONSUMER/baudot-fineract-proxy.conf"
cp "$ROOT/interop/fineract-consumer/live/compose.override.yaml" "$CONSUMER/baudot-provider-proxy.override.yaml"

cd "$CONSUMER"
./scripts/generate-dev-jwt-key.sh

compose=(docker compose -f compose.yaml -f baudot-provider-proxy.override.yaml)
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
printf '{"schema":"baudot.fineract-consumer-provider-live-startup@1","status":"STACK_HEALTHY","upstreamCommit":"%s"}\n' \
  "$UPSTREAM_COMMIT" > "$EVIDENCE_DIR/startup.json"

./scripts/seed-demo.sh | tee "$EVIDENCE_DIR/seed-demo.log"

# Reuse the exact pinned upstream fixture contracts without executing their mains.
# seed-demo supplies Fineract helpers/fixture identities; seed-openbanking supplies
# the headless login + Mailpit 2FA flow.
source <(sed '$d' ./scripts/seed-demo.sh)
source <(sed '$d' ./scripts/seed-openbanking.sh)

preflight
login_customer
ACCESS_TOKEN="$RESULT"
require "upstream provider login returned a session token" test -n "$ACCESS_TOKEN"

OWN_LIST="$EVIDENCE_DIR/provider-own-savings.json"
OWN_LIST_STATUS="$(curl -sS -o "$OWN_LIST" -w '%{http_code}' \
  -H "Cookie: ${ACCESS_TOKEN_COOKIE_NAME}=$ACCESS_TOKEN" \
  "$BFF_BASE/savings")"
require_eq "authenticated provider can list own savings" "200" "$OWN_LIST_STATUS"

OWN_ID="$(jq -r '.[0].id // empty' "$OWN_LIST")"
require "provider savings response contains an account" test -n "$OWN_ID"

# An authorized owned-resource detail read populates OwnedAccountsCache. The
# isolation measurement begins only after this known-good resource check.
OWN_DETAIL="$EVIDENCE_DIR/provider-own-savings-detail.json"
OWN_DETAIL_STATUS="$(curl -sS -o "$OWN_DETAIL" -w '%{http_code}' \
  -H "Cookie: ${ACCESS_TOKEN_COOKIE_NAME}=$ACCESS_TOKEN" \
  "$BFF_BASE/savings/$OWN_ID")"
require_eq "provider can read one owned savings account" "200" "$OWN_DETAIL_STATUS"

fineract GET "/clients?externalId=$CROSS_PROVIDER_EXTERNAL_ID"
CROSS_CLIENT_ID="$(echo "$HTTP_BODY" | jq -r '.pageItems[0].id // empty')"
require "cross-provider synthetic client exists" test -n "$CROSS_CLIENT_ID"

fineract GET "/clients/$CROSS_CLIENT_ID/accounts"
CROSS_SAVINGS_ID="$(echo "$HTTP_BODY" | jq -r '.savingsAccounts[0].id // empty')"
require "cross-provider synthetic client has savings" test -n "$CROSS_SAVINGS_ID"

PROTECTED_PATH="/fineract-provider/api/v1/savingsaccounts/$CROSS_SAVINGS_ID"
BEFORE_LOG="$EVIDENCE_DIR/fineract-proxy-before.log"
AFTER_LOG="$EVIDENCE_DIR/fineract-proxy.log"
docker logs fineract-proxy >"$BEFORE_LOG" 2>&1
BEFORE_REQUESTS="$(count_requests "$BEFORE_LOG")"
BEFORE_PROTECTED="$(count_path_hits "$BEFORE_LOG" "$PROTECTED_PATH")"

CROSS_BODY="$EVIDENCE_DIR/cross-provider-denial.json"
CROSS_STATUS="$(curl -sS -o "$CROSS_BODY" -w '%{http_code}' \
  -H "Cookie: ${ACCESS_TOKEN_COOKIE_NAME}=$ACCESS_TOKEN" \
  "$BFF_BASE/savings/$CROSS_SAVINGS_ID")"
require_eq "cross-provider savings request is denied" "403" "$CROSS_STATUS"

docker logs fineract-proxy >"$AFTER_LOG" 2>&1
AFTER_REQUESTS="$(count_requests "$AFTER_LOG")"
AFTER_PROTECTED="$(count_path_hits "$AFTER_LOG" "$PROTECTED_PATH")"

require_eq "cross-provider denial does not fetch protected Fineract resource" "$BEFORE_PROTECTED" "$AFTER_PROTECTED"
require_eq "primed cross-provider denial creates no downstream Fineract request" "$BEFORE_REQUESTS" "$AFTER_REQUESTS"

AUDIT_BODY="$EVIDENCE_DIR/provider-audit-events.json"
AUDIT_STATUS="$(curl -sS -o "$AUDIT_BODY" -w '%{http_code}' \
  -H "Cookie: ${ACCESS_TOKEN_COOKIE_NAME}=$ACCESS_TOKEN" \
  "$BFF_BASE/audit/events" || true)"
if [ "$AUDIT_STATUS" != "200" ]; then
  rm -f "$AUDIT_BODY"
fi

jq -n \
  --arg schema "baudot.fineract-consumer-provider-live-evidence@1" \
  --arg repository "apache/fineract-consumer-facing" \
  --arg commit "$UPSTREAM_COMMIT" \
  --arg providerEmail "$DEMO_EMAIL" \
  --arg ownListEndpoint "GET /api/v1/savings" \
  --arg ownListStatus "$OWN_LIST_STATUS" \
  --arg ownId "$OWN_ID" \
  --arg ownDetailStatus "$OWN_DETAIL_STATUS" \
  --arg crossExternalId "$CROSS_PROVIDER_EXTERNAL_ID" \
  --arg crossId "$CROSS_SAVINGS_ID" \
  --arg crossStatus "$CROSS_STATUS" \
  --arg protectedPath "$PROTECTED_PATH" \
  --arg beforeRequests "$BEFORE_REQUESTS" \
  --arg afterRequests "$AFTER_REQUESTS" \
  --arg beforeProtected "$BEFORE_PROTECTED" \
  --arg afterProtected "$AFTER_PROTECTED" \
  --arg auditStatus "$AUDIT_STATUS" \
  --arg ownListSha256 "$(sha256_file "$OWN_LIST")" \
  --arg ownDetailSha256 "$(sha256_file "$OWN_DETAIL")" \
  --arg denialSha256 "$(sha256_file "$CROSS_BODY")" \
  --arg proxyLogSha256 "$(sha256_file "$AFTER_LOG")" \
  --arg seedLogSha256 "$(sha256_file "$EVIDENCE_DIR/seed-demo.log")" \
  '{
    schema: $schema,
    upstream: {repository: $repository, commit: $commit},
    actor: {kind: "synthetic-provider-user", email: $providerEmail},
    authentication: {passwordStepObserved: true, twoFactorObserved: true, sessionEstablished: true},
    ownRead: {
      listEndpoint: $ownListEndpoint,
      listStatus: ($ownListStatus|tonumber),
      ownedSavingsId: ($ownId|tonumber),
      detailStatus: ($ownDetailStatus|tonumber),
      ownershipCachePrimed: true,
      listResponseSha256: $ownListSha256,
      detailResponseSha256: $ownDetailSha256
    },
    crossProviderControl: {
      targetExternalId: $crossExternalId,
      targetSavingsId: ($crossId|tonumber),
      status: ($crossStatus|tonumber),
      protectedFineractPath: $protectedPath,
      proxyRequestLinesBefore: ($beforeRequests|tonumber),
      proxyRequestLinesAfter: ($afterRequests|tonumber),
      downstreamRequestDelta: (($afterRequests|tonumber)-($beforeRequests|tonumber)),
      protectedPathHitsBefore: ($beforeProtected|tonumber),
      protectedPathHitsAfter: ($afterProtected|tonumber),
      denialResponseSha256: $denialSha256
    },
    auditQueryStatus: ($auditStatus|tonumber?),
    proxyLogSha256: $proxyLogSha256,
    seedLogSha256: $seedLogSha256,
    claimBoundary: {
      trsProgramAuthority: "NOT_DERIVED",
      providerProductionEntitlementClaimed: false,
      productionFineractSuitabilityClaimed: false,
      regulatoryComplianceClaimed: false
    }
  }' > "$EVIDENCE_DIR/evidence.json"

echo "Fineract Consumer provider live boundary: PASS"
