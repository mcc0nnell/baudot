# Consumer authority non-interference matrix

Baudot now has multiple consumer surfaces that can all be "successful" for different reasons. The important system property is that success in one surface does not silently promote authority in another.

This matrix composes the existing source contracts instead of replacing them:

```text
provider self-service
  -> interop/fineract-consumer/provider-access-contract-v1.json

machine / TPP access
  -> interop/fineract-consumer/machine-access-contract-v1.json

program / payment governance
  -> testkit/fund/governance-boundaries-v1.json

accounting execution
  -> interop/fineract/journal-contract-v1.json

public / oversight publication
  -> interop/publication/trs-fund-publication-contract-v1.json
```

The composition contract lives at:

```text
interop/authority/consumer-authority-matrix-v1.json
```

## Core rule

A positive fact keeps the authority owned by its domain:

```text
providerAccessAuthorized    -> provider visibility only
machineAccessAuthorized     -> machine visibility only
programEligible             -> program compensability only
paymentAuthorized           -> payment authority only
ledgerAccepted              -> accounting execution observed only
publicProjectionPublished   -> public visibility only
```

None of those facts derives Baudot operator authority. This stack does not yet claim an implemented operator authentication/authorization contract, so the matrix deliberately keeps `operatorAuthority = NOT_DERIVED` in every case.

## Negative composition controls

The first matrix includes eight deterministic cases, including:

- provider access with every other authority un-derived;
- machine consent with every other authority un-derived;
- program eligibility without payment or ledger execution;
- payment authorization without accounting execution;
- ledger acceptance without program/payment authority;
- public aggregate visibility without any authenticated authority;
- machine consent revocation while provider access remains authorized; and
- program + payment + ledger success without provider, machine, operator, or public access.

## Why this matters

The same infrastructure can expose many successful signals:

```text
200 from Consumer
OAuth consent AUTHORIZED
policy/program gate allowed
payment authorized
Fineract journal accepted
public chart visible
```

Those statements are not interchangeable. The validator mechanically preserves that distinction.

## Validation

Run:

```text
python scripts/validate_consumer_authority_matrix.py
```

CI also runs this validator whenever the matrix or any of its five source contracts changes.

## Claim boundary

A green matrix establishes internal consistency of the synthetic/public proving-ground authority model. It does not establish production identity binding, production authorization policy correctness, production Fund state, operator authentication implementation, or regulatory compliance.
