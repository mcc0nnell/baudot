# Live Fineract Consumer provider boundary

This lane turns the contract-only provider boundary into an external implementation proof against a source-pinned Apache Fineract Consumer-Facing checkout.

It remains a synthetic proving-ground lane. It does not model or assert production provider identity, production entitlement, real TRS Fund data, payment authority, program authorization, or regulatory compliance.

## Source pin

```text
apache/fineract-consumer-facing
58eacf7338126aa0de2b2a2ef70319f45d403fbf
```

The lane uses the upstream development stack and its own synthetic demo seeder. Baudot does not copy Consumer authentication or ABAC logic into its authority core.

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
4. logs in as the upstream `demo3@example.com` fixture using password plus Mailpit-delivered 2FA;
5. reads `GET /api/v1/savings` through the Consumer BFF;
6. resolves one savings-account ID belonging to the separate `demo-client-4` synthetic client directly from the Fineract test fixture;
7. snapshots the recording proxy after the provider's ownership cache has been primed;
8. requests `GET /api/v1/savings/{otherProviderSavingsId}` with the first provider's authenticated session; and
9. requires both HTTP 403 and zero new downstream proxy requests.

## Why prime the ownership cache

Consumer-Facing ownership resolution can obtain the caller's owned account IDs through Fineract before applying an owned-resource decision. A first request may therefore create a legitimate downstream lookup of the caller's own account set.

The live negative control intentionally performs an authorized provider read first. That primes the ownership cache. The cross-provider request is then measured in isolation.

The required invariant is:

```text
provider A authenticated
+ provider A ownership cache established
+ provider A requests provider B savings account
=
HTTP 403 at Consumer BFF
+ zero new downstream Fineract request
```

The probe also counts the exact protected Fineract resource path and requires that count to remain unchanged.

## Evidence

The workflow preserves an artifact containing:

- `evidence.json` — machine-readable verdict and source pin;
- `provider-own-savings.json` — the provider-visible authorized response;
- `cross-provider-denial.json` — the Consumer denial response;
- `fineract-proxy.log` — downstream request evidence;
- `provider-audit-events.json` when the upstream audit-query endpoint is available; and
- `seed-demo.log` — synthetic fixture construction evidence.

Hashes of the principal response and log artifacts are recorded in `evidence.json`.

## Authority boundary

A passing lane establishes only that this pinned Consumer-Facing implementation admitted one synthetic authenticated self-read and denied one synthetic cross-provider read under the measured conditions.

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
