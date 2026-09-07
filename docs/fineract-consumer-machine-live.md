# Live Fineract Consumer machine consent boundary

This lane qualifies the consent-scoped machine/API boundary from `fineract-consumer-machine-boundary.md` against the pinned Apache Fineract Consumer-Facing stack.

It remains a synthetic proving-ground lane. It does not model or assert production TPP onboarding, production provider identity, real TRS Fund data, claim/payment authority, operator authority, or regulatory compliance.

## Source pin

```text
apache/fineract-consumer-facing
58eacf7338126aa0de2b2a2ef70319f45d403fbf
```

The lane uses the upstream development compose stack, upstream synthetic seeder, upstream OAuth2 consent helpers, and upstream Mailpit-backed 2FA flow. Baudot does not reimplement the Consumer identity or consent model.

## What runs

```text
synthetic provider user
        |
        | ordinary Consumer session
        v
Fineract Consumer-Facing BFF
        |
        | approves / later revokes consent
        v
synthetic TPP
        |
        | OAuth2 bearer
        | purpose=openbanking
        | scope=openbanking:accounts.read
        v
Consumer Open Banking read surface
        |
        v
recording reverse proxy
        |
        v
Apache Fineract
```

The proxy is observation-only. It authorizes and transforms nothing.

## Positive machine proof

The provider logs in using the pinned upstream password + Mailpit 2FA flow. The TPP then executes the real client-credentials + authorization-code + PKCE consent ceremony.

The resulting machine token must successfully execute:

```text
GET /api/v1/openbanking/accounts
GET /api/v1/openbanking/accounts/{accountId}/balances
```

The artifact records token purpose and scope but never the bearer token or provider session value.

## Credential separation proof

Before revocation, the lane also requires:

```text
Open Banking bearer -> ordinary /savings endpoint       = 401
provider login token -> Open Banking /accounts endpoint = 401
```

This proves the machine and provider credentials are not interchangeable even though both ultimately expose provider-owned financial facts.

## Revocation proof

The provider then calls the ordinary customer consent-management surface:

```text
POST /api/v1/openbanking/consents/{consentId}/revoke
```

and requires the returned consent state to be `REVOKED`.

The test deliberately keeps the already-issued machine access token. It does not mint a new token after revocation.

It then repeats:

```text
GET /api/v1/openbanking/accounts
```

with that same token and requires:

```text
HTTP 403
```

The recording proxy is snapshotted immediately before and after the denied read. Its request count must remain unchanged. This proves the revoked-consent decision occurs before a new Fineract request is delegated.

## Provider independence proof

Only after the denied machine read is measured does the provider perform another ordinary Consumer read:

```text
GET /api/v1/savings -> 200
```

So the live invariant is:

```text
machine consent REVOKED
+ same machine token still presented
=
machine denied before Fineract
+ provider session still usable
```

That is the concrete separation between a provider consumer and a machine consumer.

## Preserved evidence

The workflow uploads:

- startup / compose / proxy diagnostics;
- upstream synthetic seed log;
- provider response before machine consent revocation;
- machine account and balance responses before revocation;
- credential-substitution denial responses;
- consent revocation response;
- machine denial response after revocation;
- provider response after revocation;
- proxy logs around the revoked read;
- audit events when queryable; and
- machine-readable `evidence.json` with hashes and source pin.

No provider session token, TPP access token, refresh token, client secret, OTP, or authorization code is written to the artifact.

## Authority boundary

A green lane does not establish:

```text
machine access authorized = provider access authorized
machine access authorized = Baudot operator authorized
machine access authorized = TRS program authorized
Open Banking consent       = claim approved
Open Banking consent       = payment authorized
Fineract state              = regulatory entitlement
```

All of those equivalences remain false by design.

## Next threshold

Once this lane is stable, add the fourth consumer: a public/oversight publication surface that consumes only aggregate or explicitly releasable state. It should be impossible for public visibility to be promoted into provider, machine, operator, claim, payment, or TRS program authority.
