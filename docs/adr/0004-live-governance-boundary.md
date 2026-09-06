# ADR-0004: Cross the synthetic Fund governance boundary into the live Fineract lane

- Status: Proposed
- Date: 2026-09-06
- Decision owners: Baudot maintainers

## Context

ADR-0003 makes program authority and accounting execution distinct facts. The static governance contract proves that a balanced journal cannot create missing program authority and that ledger rejection cannot erase prior business authority.

The next threshold is to prove those asymmetries against the live, source-pinned Apache Fineract lane rather than only against the static reducer.

## Decision

The live Fund lane will carry two explicit governance negative controls.

### FUND-GOV-LIVE-001: unauthorized balanced payment is blocked before Fineract

Baudot will construct a synthetically balanced provider-disbursement intent whose event, service, provider, and program facts are valid but whose payment authorization fact is false.

The probe must preserve the intended debit/credit mapping while proving that no Fineract HTTP request is attempted for the journal operation.

Expected result:

```text
balanced journal intent
+ missing payment authorization
= BLOCKED_BEFORE_LEDGER
```

Fineract receives no payment journal request.

### FUND-GOV-LIVE-002: authorized payment can fail at the ledger boundary

Baudot will construct a fully authorized synthetic provider-disbursement intent and submit it after the live lane has established an accounting closure for the posting date.

Expected result:

```text
all pre-ledger program gates satisfied
+ Fineract accounting closure rejection
= AUTHORIZED_BUT_LEDGER_REJECTED
```

The evidence bundle must preserve both facts: the program authorization existed before the call, and Fineract rejected accounting execution without creating the transaction.

## Consequences

A live evidence manifest can now distinguish at least three materially different outcomes:

```text
NOT_AUTHORIZED_FOR_LEDGER
AUTHORIZED_BUT_LEDGER_REJECTED
AUTHORIZED_AND_LEDGER_ACCEPTED
```

None may be collapsed into another.

This remains a synthetic public proving-ground control. It does not reproduce or assert production TRS Fund authorization workflows.
