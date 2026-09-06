# Part 64 → synthetic Fund payment, settlement, and reconciliation

Status: integration slice

This slice begins only after the Part 64/Fund handoff has produced a synthetic provider payable. It models the remaining financial-state transitions without allowing accounting or settlement evidence to create regulatory authority.

## Core invariant

```text
provider payable accrued
!= payment authorized
!= payment instruction emitted
!= settlement succeeded
!= cash moved
!= ledger readback matched
!= reconciliation complete
```

A reversal is another independent transition:

```text
posted disbursement
!= erroneous
!= reversal authorized
!= reversal posted
!= balances restored
```

## Existing canonical accounting contract

Baudot already defines:

```text
providerClaimApproved
  Dr 5100 TRS Provider Compensation Expense
  Cr 2100 Provider Payable

providerDisbursement
  Dr 2100 Provider Payable
  Cr 1100 TRS Fund Cash
```

This slice consumes those events. It does not redefine their business authority.

## Payment authority boundary

A provider payable is an accrued synthetic obligation only. A payment instruction may be emitted only after a separate synthetic payment-authorization decision.

Payment authorization does not prove settlement. Settlement confirmation does not prove ledger correctness. A Fineract posting response does not prove reconciliation.

## Executable scenarios

- `FUND-PAY-SETTLE-001` — $8,830 payable; payment separately authorized; full synthetic settlement succeeds; one `providerDisbursement` journal is observed; independent readback reduces payable to zero and Fund cash by $8,830; reconciliation passes.
- `FUND-PAY-AUTH-BLOCK-001` — payable exists but payment authorization is `not-determined`; no instruction, settlement, or cash journal may exist.
- `FUND-PAY-SETTLE-FAIL-001` — payment authorized and instruction emitted, but synthetic rail reports failure; payable/cash remain unchanged and no disbursement journal may post.
- `FUND-PAY-PARTIAL-001` — $8,830 instructed but only $8,000 settles; the accounting effect is limited to the settled amount and $830 payable remains. The scenario is not fully reconciled as a completed payment.
- `FUND-PAY-DUPLICATE-001` — replay of an already-observed settlement event ID produces zero additional financial effect.
- `FUND-PAY-READBACK-MISMATCH-001` — settlement says $8,830 but observed ledger cash/payable movement differs by one cent; reconciliation fails closed.
- `FUND-PAY-REVERSAL-001` — a posted $8,830 disbursement is explicitly reversed with an equal-and-opposite entry; original and reversal IDs are both preserved and balances return to the pre-disbursement state.
- `FUND-PAY-CLOSED-PERIOD-001` — settlement exists on a closed accounting date and no authorized open posting date is supplied; journal posting is blocked rather than silently backdated.

## Reconciliation contract

A completed payment requires agreement among four independently represented facts:

1. authorized payment amount;
2. settlement result amount/status;
3. observed ledger movement/readback; and
4. expected synthetic Fund balances.

For a full $8,830 settlement:

```text
before
  Provider Payable  8,830.00
  TRS Fund Cash    50,000.00

after
  Provider Payable      0.00
  TRS Fund Cash    41,170.00
```

The reducer verifies the delta, not merely the ending balance.

## Partial settlement rule

A partial external settlement does not justify posting the full authorized amount. The financial effect is bounded by the amount actually settled:

```text
instruction  8,830.00
settled      8,000.00

journal
  Dr 2100    8,000.00
  Cr 1100    8,000.00

residual payable 830.00
```

The payment remains operationally incomplete even though the partial journal can itself reconcile.

## Reversal rule

Corrections preserve history. A posted payment is never deleted or mutated in place.

```text
original disbursement
  Dr 2100  8,830.00
  Cr 1100  8,830.00

explicit reversal
  Dr 1100  8,830.00
  Cr 2100  8,830.00
```

The evidence bundle must preserve the original transaction ID, reversal transaction ID, authorization for reversal, and independent post-reversal readback.

## Accounting-closure rule

If the intended posting date is closed, the adapter must either:

- fail the posting; or
- receive an explicitly authorized open posting date from the synthetic accounting-control plane.

It may not silently move the transaction to another date.

## Clean-room boundary

No production payment instruction, bank account, ACH/wire transaction, provider payment, Fund administrator action, or real Fineract transaction is represented. Settlement and ledger readback are synthetic external-observation fixtures.

## Promotion threshold

The next stronger threshold is an exact pinned Fineract test instance in CI. That live lane should:

1. provision only the synthetic chart of accounts;
2. post the canonical provider payable and disbursement events;
3. read the resulting journal/balances back through Fineract;
4. exercise duplicate, reversal, and closed-period controls; and
5. require the external state to reduce to the same expected balances as this static contract.

A live Fineract HTTP success response would still be insufficient without independent readback and reconciliation.
