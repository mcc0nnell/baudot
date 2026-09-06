# Part 64 → synthetic Fund/Fineract claim handoff

Status: integration slice

This slice closes the regulatory-to-accounting loop without collapsing the authority boundaries that Baudot has built across Part 64.

## Core invariant

```text
externally established compensability
!= rate calculated
!= synthetic claim approved
!= provider payable accrued
!= payment authorized
!= cash disbursed
!= settlement reconciled
```

## Existing canonical accounting contract

Baudot's merged Fineract journal contract already defines:

```text
providerClaimApproved
  Dr 5100 TRS Provider Compensation Expense
  Cr 2100 Provider Payable

providerDisbursement
  Dr 2100 Provider Payable
  Cr 1100 TRS Fund Cash
```

Those journal shapes are consumed here rather than redefined. Fineract remains `synthetic-accounting-adapter-only`.

## Handoff gates

A provider-claim accrual may be emitted only when all of the following are independently true:

1. upstream Part 64 evidence has a terminal `externally-established-compensable` decision;
2. the § 64.643 rate engine has produced a calculated amount from those terminal minutes;
3. the synthetic Fund claim decision is `approved`;
4. the approved claim amount exactly matches the rate-engine result; and
5. the synthetic business transaction ID has not already produced a posting.

Only then may the adapter emit the canonical `providerClaimApproved` journal intent.

## Positive arm

`FUND-HANDOFF-APPROVED-001` consumes `VRS-RATE-VIDEO-TEXT-1000`:

```text
external compensability   yes
§ 64.643 amount            $8,830.00
synthetic claim decision   approved
approved amount            $8,830.00

journal intent
  Dr 5100                  $8,830.00
  Cr 2100                  $8,830.00
```

This creates a **synthetic provider payable**, not a payment. Fund cash remains unchanged because payment authorization is still `not-determined`.

## Fail-closed arms

The adapter emits no provider payable for:

- regulatory compensability still pending;
- regulatory denial;
- payment/claim suspension;
- a synthetic claim still pending;
- an approved claim whose amount differs from the § 64.643 result by even one cent; or
- replay of a business transaction ID already posted.

The one-cent mismatch control exists specifically to prevent an accounting or claim layer from silently rewriting the regulatory rate result.

## Idempotency

`syntheticBusinessTransactionId` is the canonical Baudot adapter idempotency key, consistent with the existing Fineract journal contract.

```text
claim-vrs-2026-08-example-001 first approved handoff
  -> one provider-payable accrual

same ID replay
  -> zero additional financial effect
```

The adapter does not infer that two different claim IDs are economically duplicates. Upstream claim identity remains a synthetic Fund-domain responsibility.

## Payment boundary

`FUND-HANDOFF-DISBURSEMENT-BLOCKED-001` starts with an existing provider payable but no payment authorization.

It therefore refuses the canonical `providerDisbursement` posting:

```text
provider payable exists
!= payment authorized
!= Fund cash may move
```

A later payment slice can consume explicit synthetic payment authorization and then exercise the `Dr 2100 / Cr 1100` journal path, settlement result, and reconciliation.

## Composition

The resulting end-to-end authority graph is:

```text
Part 64 registration / numbering / validation
        |
        v
provider-change / continuity / certification evidence
        |
        v
call evidence + monthly controls
        |
        v
external compensability determination
        |
        v
§ 64.643 rate engine
        |
        v
synthetic Fund claim decision
        |
        v
canonical Fineract providerClaimApproved journal intent
        |
        v
separate payment authorization
        |
        v
canonical providerDisbursement journal intent
        |
        v
independent reconciliation
```

No edge is transitive merely because the components are connected.

## Clean-room boundary

No production Fund claim, provider payment, bank instruction, administrator decision, Fineract transaction, subscriber record, or provider-confidential data is represented. All financial transactions and identifiers are synthetic.
