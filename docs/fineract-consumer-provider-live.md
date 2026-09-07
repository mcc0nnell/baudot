# Live Fineract Consumer provider boundary

This lane turns the contract-only provider boundary into an external implementation proof against a source-pinned Apache Fineract Consumer-Facing checkout.

It remains a synthetic proving-ground lane. It does not model or assert production provider identity, production entitlement, real TRS Fund data, payment authority, program authorization, or regulatory compliance.

## Source pin

```text
apache/fineract-consumer-facing
58eacf7338126aa0de2b2a2ef70319f45d403fbf
```

The lane uses the upstream development stack and its own synthetic demo seeder. Baudot does not copy Consumer authentication or ABAC logic into its authority core. The live probe also reuses the pinned upstream fixture helpers for login, Mailpit 2FA, and Fineract fixture access rather than duplicating their demo credentials in Baudot.

## What runs

```text
synthetic provider user
        |
        v
Fineract Consumer-Facing BFF
        |
        v
recording reverse proxy
        |
        v
Apache Fineract
```

The recording proxy exists only as an observation point. It does not authorize, transform, or interpret the request.

The probe:

1. generates the upstream development JWT signing key;
2. starts the pinned Consumer-Facing compose stack;
3. runs upstream `seed-demo.sh` to create the synthetic clients and BFF bindings;
4. uses the pinned upstream headless-login helpers to establish the `demo3@example.com` password + Mailpit 2FA session;
5. reads `GET /api/v1/savings` through the Consumer BFF;
6. reads one account from that returned set with `GET /api/v1/savings/{ownedSavingsId}`, exercising the owned-resource ABAC path and populating `OwnedAccountsCache`;
7. resolves one savings-account ID belonging to the separate `demo-client-4` synthetic client directly from the Fineract test fixture;
8. snapshots the recording proxy;
9. requests `GET /api/v1/savings/{otherProviderSavingsId}` with the first provider's authenticated session; and
10. requires both HTTP 403 and zero new downstream proxy requests.

## Why prime the ownership cache

Consumer-Facing's list path and owned-resource path are not identical. `GET /api/v1/savings` resolves the caller's client and lists accounts, but an owned-resource request such as `GET /api/v1/savings/{id}` authorizes through `OwnedAccountsCache`. On the cache's first load, Consumer-Facing may legitimately call Fineract to learn the caller's owned account IDs.

The live negative control therefore performs one known-good **owned account detail** request before measurement. That gives the same owned-resource authorization path a legitimate chance to populate its cache. Only then is the cross-provider request measured in isolation.

The required invariant is:

```text
provider A authenticated
+ provider A owned-resource cache established
+ provider A requests provider B savings account
=
HTTP 403 at Consumer BFF
+ zero new downstream Fineract request
```

The probe also counts the exact protected Fineract resource path and requires that count to remain unchanged.

## Evidence

The workflow preserves an artifact containing:

- `evidence.json` — machine-readable verdict and source pin;
- `provider-own-savings.json` — the authorized provider account list;
- `provider-own-savings-detail.json` — the authorized owned-resource read used to establish the ABAC/cache path;
- `cross-provider-denial.json` — the Consumer denial response;
- `fineract-proxy-before.log` and `fineract-proxy.log` — downstream request evidence around the negative control;
- `provider-audit-events.json` when the upstream audit-query endpoint is available; and
- `seed-demo.log` — synthetic fixture construction evidence.

Hashes of the principal response and log artifacts are recorded in `evidence.json`.

## Authority boundary

A passing lane establishes only that this pinned Consumer-Facing implementation admitted the measured synthetic authenticated self-reads and denied one synthetic cross-provider read under the measured conditions.

It does not establish:

```text
Consumer authentication = TRS provider certification
Consumer ABAC allow      = TRS claim approval
Consumer ABAC allow      = payment authorization
Fineract account state   = regulatory entitlement
provider visibility      = operator authority
```

All of those equivalences remain false by design.

## Next threshold

Once this lane is stable, add a machine/API actor as a separate surface rather than reusing the provider session. The next composition should prove that a system integration can consume a narrowly scoped read contract without inheriting provider UI authority or Baudot operator authority.
