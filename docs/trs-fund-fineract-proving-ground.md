# TRS fund proving ground with Apache Fineract

Baudot's provider interoperability lab can extend past call setup into a bounded, synthetic fund plane without pretending to reproduce any production TRS Fund administrator implementation.

The architectural split is:

```text
CALL / INTEROP PLANE

provider fixture
      |
      v
iTRS route decision
      |
      v
SIP / media / RTT evidence
      |
      v
Baudot call facts
      |
      v
synthetic CDR

FUND RULES PLANE

synthetic CDR
      |
      v
public-workflow-derived fund-admin fixture
  eligibility decision
  rate profile selection
  adjustment / duplicate rules
      |
      v
approved synthetic claim

FINANCIAL STATE PLANE

approved synthetic claim
      |
      v
Apache Fineract ledger adapter
      |
      +--> reimbursement expense
      +--> provider payable
      +--> fund cash
      +--> reversals / adjustments
      |
      v
synthetic settlement + reconciliation
```

## Decision

Apache Fineract is the preferred reference implementation for the **synthetic TRS Fund financial state**.

Fineract is deliberately **not** the authority for:

- whether a call is compensable;
- which reimbursement rate applies;
- provider eligibility;
- numbering or routing correctness;
- call-duration truth;
- provider certification;
- production payment authorization; or
- any production Rolka Loube workflow.

Those decisions must exist as explicit upstream synthetic facts before the ledger adapter is invoked.

The key invariant is:

```text
call observed
!= compensable
!= claim approved
!= payable posted
!= payment settled
!= reconciliation complete
```

## Why Fineract

The current Apache Fineract stable release is 1.15.0. Its published API surface includes journal-entry creation and reversal, and the platform documentation describes business-date handling plus a reliable external-event framework. Those capabilities are sufficient to make Fineract a useful financial-state implementation for this lab without granting it fund-policy authority.

References:

- <https://fineract.apache.org/>
- <https://fineract.apache.org/docs/stable/>
- <https://fineract.apache.org/docs/legacy/>

## Initial chart of accounts

The first profile is intentionally small and reimbursement-focused:

```text
1000  TRS Fund Cash                  asset
2100  Provider Payable               liability
6100  VRS Reimbursement Expense      expense
6200  IP CTS Reimbursement Expense   expense
1300  Provider Recovery Receivable   asset
```

The account numbers are **Baudot synthetic test identifiers**, not a representation of a production TRS Fund chart of accounts.

## Posting model

### Approved reimbursement claim

For a synthetic approved VRS claim of 60.00:

```text
Dr 6100 VRS Reimbursement Expense   60.00
Cr 2100 Provider Payable            60.00
```

### Settlement

When the synthetic payment fixture settles the approved claim:

```text
Dr 2100 Provider Payable            60.00
Cr 1000 TRS Fund Cash               60.00
```

### Downward adjustment before settlement

If an approved claim is reduced from 60.00 to 54.00 before payment:

```text
Dr 2100 Provider Payable             6.00
Cr 6100 VRS Reimbursement Expense     6.00
```

### Reversal

An erroneous posted claim is not deleted from history. The adapter must use an explicit reversal or equal-and-opposite posting so the evidence path preserves the original transaction and its correction.

## Idempotency boundary

Every approved synthetic claim carries an external idempotency key before it reaches Fineract.

The same claim replayed with the same key must not create another payable.

```text
claim-001 first submission  -> one balanced journal transaction
claim-001 replay            -> zero additional financial effect
```

The upstream fund-admin fixture owns the claim identity. Fineract may enforce or assist idempotent command handling, but it does not get to decide that two independently approved claims are economically identical.

## Evidence contract

A live Fineract-backed run should eventually preserve:

```text
call-evidence/
  signaling.json
  media.json
  cdr.json

fund-admin/
  eligibility-decision.json
  rate-profile.json
  approved-claim.json

fineract/
  instance-version.txt
  chart-of-accounts.json
  journal-request.json
  journal-response.json
  journal-readback.json
  reversal-response.json        # when applicable

payment/
  settlement-instruction.json
  settlement-result.json
  reconciliation.json

bundle.manifest.sha256
```

A Fineract HTTP success response is not sufficient. The live qualification must read financial state back and independently verify that debits equal credits, expected account balances changed exactly once, and duplicate/reversal scenarios preserve the intended state.

## First live threshold

This PR does **not** introduce a Fineract runtime dependency yet. It defines the contract and deterministic accounting invariants first.

The next executable threshold is:

1. start an exact pinned Fineract 1.15.0 test instance;
2. provision only the synthetic chart of accounts;
3. submit one approved claim through a thin `fineract-ledger-adapter`;
4. read the resulting journal transaction back;
5. execute settlement;
6. replay the original claim and prove no second payable is created;
7. execute one adjustment/reversal case; and
8. seal the API request/response/readback evidence with the existing Baudot evidence discipline.

## Naming boundary

The repository should not create a `MockRolkaLoube` implementation.

Preferred names are:

- `fund-admin-fixture` — synthetic policy/workflow boundary derived only from public material;
- `trs-fund-model` — provider-neutral fund contract;
- `fineract-ledger-adapter` — financial-state implementation;
- `payment-fixture` — synthetic settlement rail.

This prevents a deterministic test service from being mistaken for a reconstruction of a proprietary administrator system.

## End-to-end target scenario

The eventual proving-ground chain is:

```text
cross-provider VRS call
        -> iTRS route
        -> SIP / media evidence
        -> synthetic CDR
        -> explicit compensability decision
        -> approved synthetic claim
        -> Fineract journal posting
        -> synthetic settlement
        -> provider reconciliation
        -> sealed evidence bundle
```

The terminal result is a **synthetic lifecycle proof**. It is not a finding about production provider reimbursement, administrator implementation correctness, FCC payment authorization, Fineract conformance, or production TRS Fund accounting.