# Fineract Consumer provider-facing boundary

Baudot and Apache Fineract Consumer-Facing serve different actors.

The first composition keeps that difference explicit:

```text
provider user
    |
    v
Apache Fineract Consumer-Facing BFF
 authentication + provider binding + ABAC
    |
    v
provider-scoped financial reads
    |
    v
Apache Fineract

operator
    |
    v
Baudot control plane
 evidence + cross-provider reasoning + exceptions
 program/rate/claim/payment decisions remain separate
```

The provider lane is not the operator lane, and neither lane becomes TRS authority merely because it can observe financial state.

## Why Consumer-Facing fits

Apache Fineract Consumer-Facing exists to keep end-user clients away from Fineract Core credentials and to place a Backend-for-Frontend between the user interface and Fineract. The BFF owns its authentication, authorization, account binding, and audit boundary while Fineract remains the banking system of record.

Baudot already preserves the complementary rule on the accounting side:

```text
Fineract journal accepted != TRS program authorized
```

This slice extends the same discipline northbound:

```text
provider access authorized != TRS program authorized
consumer BFF ABAC allow    != claim approved
consumer BFF ABAC allow    != payment authorized
ledger state               != provider visibility entitlement
```

## First provider surface: read only

The contract is pinned to `apache/fineract-consumer-facing` commit:

```text
58eacf7338126aa0de2b2a2ef70319f45d403fbf
```

The first admitted surface intentionally contains only documented Consumer-Facing reads:

```text
GET /api/v1/summary/accounts
GET /api/v1/savings
GET /api/v1/savings/{savingsId}
GET /api/v1/savings/{savingsId}/transactions
GET /api/v1/savings/{savingsId}/transactions/{transactionId}
```

The contract explicitly excludes Consumer transfer mutation, loan mutation, direct ledger journals, claim creation/approval, rate selection, payment authorization, provider certification, and TRS eligibility decisions.

That lets a later provider portal answer questions such as:

- What provider-visible financial accounts exist?
- What is the current visible balance/state?
- What transactions are visible to this provider-scoped principal?

without allowing the same surface to answer:

- Is this provider certified?
- Is this call compensable?
- Is this claim approved?
- Which rate applies?
- Is payment authorized?

Those remain separate Baudot/TRS-domain decisions.

## Consumer classes

The contract names four independent surfaces rather than creating one giant role model.

| Consumer | Surface | Initial purpose |
| --- | --- | --- |
| Provider user | Fineract Consumer-Facing BFF | Provider-scoped financial visibility |
| Operator | Baudot | Cross-provider reasoning, evidence, exceptions, reconciliation, program decisions |
| System | Separate machine API boundary | Constrained system-to-system exchange |
| Public / oversight | Separate publication boundary | Aggregated or otherwise releasable information |

No surface is declared to confer TRS program authority by itself.

## Deterministic controls

`testkit/fund/fineract-consumer-provider-boundary-v1.json` exercises five synthetic controls.

### Provider self-read

An authenticated, active provider user with matching provider scope and BFF ABAC allow can cross the read boundary.

```text
PROVIDER_ACCESS_AUTHORIZED
TRS program authority = NOT_DERIVED
```

The fixture deliberately does not require `ledgerAccepted=true` to make the access decision. Ledger acceptance is not an access credential.

### Cross-provider read

A provider-A principal targeting provider-B state is denied and no downstream Fineract read is expected.

```text
PROVIDER_ACCESS_DENIED
Fineract read = false
```

### Revoked access with ledger state still present

The fixture preserves `ledgerAccepted=true` while provider access is inactive.

```text
ledger accepted = true
provider access = denied
```

This mechanically proves that persisted accounting state cannot resurrect visibility entitlement.

### Operator through the provider lane

Even an authenticated operator with otherwise favorable synthetic facts is denied by the provider contract and routed to:

```text
baudot-operator-control-plane
```

Provider self-service is not an operator back door.

### Write-shaped Consumer request

A synthetic `POST /api/v1/transfers/initiate` request is rejected by this first contract even though Consumer-Facing documents transfer support. The point is not to claim the upstream capability is unsafe; it is to keep Baudot's initial provider integration narrower than the complete Consumer-Facing API.

## Source-pinned CI

The validator runs in two modes.

Local contract validation:

```bash
python scripts/validate_fineract_consumer_provider_boundary.py
```

CI additionally checks out the exact Consumer-Facing commit and verifies that the pinned provider-read paths remain documented there:

```bash
python scripts/validate_fineract_consumer_provider_boundary.py \
  --upstream-root .upstream/fineract-consumer-facing
```

This is provenance and contract-shape evidence, not a live BFF qualification.

## Claim boundary

A green result establishes only that:

1. Baudot has a deterministic provider-facing access contract;
2. the admitted read paths exist in the pinned Consumer-Facing source documentation;
3. provider visibility remains distinct from operator and TRS program authority; and
4. the negative controls fail closed before a downstream Fineract read where required.

It does **not** establish a live Consumer-Facing integration, production identity binding, production ABAC correctness, real provider entitlement, real TRS Fund authority, production Fineract suitability, or regulatory compliance.

## Next threshold

Run the pinned Consumer-Facing BFF as an external implementation and exercise one authenticated synthetic provider read end to end. Preserve separately:

```text
principal/session evidence
provider-scope binding evidence
BFF ABAC decision
BFF response
Fineract read observation
Baudot independent access verdict
TRS authority = NOT_DERIVED
```

Then add one cross-provider negative control and require the BFF to deny it before any Fineract request is observed.
