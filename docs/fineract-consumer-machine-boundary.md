# Fineract Consumer machine access boundary

This boundary gives Baudot a distinct machine/API consumer without reusing the provider session or the Baudot operator surface.

The machine actor is Apache Fineract Consumer-Facing's existing Open Banking TPP model. The first Baudot contract is intentionally read-only and source-pinned.

```text
third-party system
      |
      | OAuth2 bearer
      | purpose=openbanking
      | scope=openbanking:accounts.read
      v
Fineract Consumer-Facing BFF
      |
      | consent rechecked on every read
      v
provider-owned Fineract account state
```

## Why this is a separate consumer

A provider user and a machine integration can be looking at some of the same financial state while having completely different credentials, lifecycle, and authority.

The provider uses the ordinary Consumer session surface. The machine uses a consent-scoped Open Banking bearer token. Consumer-Facing deliberately prevents either credential from being substituted for the other.

```text
provider session != machine token
machine token     != provider session
machine access    != Baudot operator authority
```

## Source pin

```text
apache/fineract-consumer-facing
58eacf7338126aa0de2b2a2ef70319f45d403fbf
```

At that revision, the Open Banking module is read-only. The machine data surface is limited to:

```text
GET /api/v1/openbanking/accounts
GET /api/v1/openbanking/accounts/{accountId}/balances
```

The account list requires `ReadAccountsBasic`; balances require `ReadBalances`. The token must carry `purpose=openbanking` and `openbanking:accounts.read`.

## Consent is the machine kill switch

The consent row is not merely issuance-time metadata. Consumer-Facing reloads it on every TPP read and requires that it remain:

- `AUTHORISED`;
- unexpired;
- bound to the calling TPP;
- bound to the token subject/customer; and
- permitted for the requested data category.

That means a provider can revoke machine access without revoking the provider's own session. The access token may still be inside its TTL, but the next machine read must fail.

The key invariant is:

```text
provider session ACTIVE
+ machine consent REVOKED
=
provider access remains available
+ machine access is denied
```

The reverse is also important: a provider login does not create machine consent, and an active machine consent does not confer operator or TRS program authority.

## Deterministic controls

The test fixture covers:

1. an active TPP + valid consent + correct scope/permission -> machine read authorized;
2. consent revoked while provider session remains active -> machine denied, provider unchanged;
3. consumer cookie presented to machine endpoint -> unauthenticated;
4. Open Banking bearer presented to ordinary consumer endpoint -> unauthenticated;
5. TPP/consent mismatch -> denied;
6. expired consent -> denied; and
7. requested permission absent -> denied.

Every control keeps:

```text
TRS program authority = NOT_DERIVED
```

## Forbidden capabilities

This machine surface cannot be used for money movement, transfers, loan mutation, claim creation or approval, rate selection, payment authorization, provider certification, TRS eligibility decisions, ledger-journal mutation, or Baudot operator authority.

## Relationship to the other Baudot consumers

```text
provider user
  -> Consumer BFF provider surface
  -> provider-scoped financial visibility

third-party system
  -> Consumer BFF Open Banking surface
  -> consent-scoped financial visibility

operator
  -> Baudot control plane
  -> cross-provider evidence, exceptions, reconciliation, program decisions

public / oversight
  -> separate publication surface
  -> aggregated or otherwise releasable information
```

These are intentionally different authority domains even where their underlying facts overlap.

## Claim boundary

A passing contract validates the source-pinned access shape and its separation invariants. It does not establish production TPP onboarding, production OAuth client security, real TRS provider entitlement, claim/payment authority, Baudot operator authority, production Fineract suitability, or regulatory compliance.

## Next threshold

Exercise the lifecycle against the live pinned Consumer-Facing stack:

```text
provider login
-> TPP consent ceremony
-> TPP account read succeeds
-> provider revokes consent
-> same unexpired TPP token is denied
-> provider account read still succeeds
```

Preserve the consent id, token-purpose/scope metadata without the token itself, pre/post machine response evidence, provider response evidence, audit events, and downstream Fineract observations.
