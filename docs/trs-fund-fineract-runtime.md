# TRS Fund runtime lifecycle with Apache Fineract

Baudot keeps the **public Fund model** and the **financial runtime** as separate authority planes.

```text
public FCC / Rolka Loube evidence
        |
        v
public Fund calibration + policy model
        |
        v
explicit synthetic business decision
        |
        v
runtime lifecycle contract
        |
        v
Apache Fineract ledger implementation
        |
        v
synthetic settlement + reconciliation
```

The runtime layer starts only after an upstream synthetic decision exists. It cannot decide whether a call is compensable, select a reimbursement rate, certify a provider, authorize a production payment, or redefine the Fund chart of accounts.

The canonical inputs remain:

- `testkit/fund/rolka-loube-2025-26.json` for the public calibration fixture;
- `interop/fineract/journal-contract-v1.json` for the synthetic chart of accounts and event-to-journal mappings; and
- `docs/trs-fund-public-ledger.md` for the public-model authority boundary.

`testkit/fund/trs-fund-runtime-contract-v1.json` deliberately contains **no `accounts` object and no `rateProfiles` object**. The validator fails if either is added.

## Runtime lifecycle scenarios

The first lifecycle profile exercises five bounded behaviors.

### FUND-001 — approved claim posting

An upstream-approved synthetic amount becomes a provider payable using the canonical `providerClaimApproved` event:

```text
Dr 5100 TRS Provider Compensation Expense
Cr 2100 Provider Payable
```

The runtime does not derive the approved amount from minutes or a rate.

### FUND-002 — settlement

A synthetic settlement clears the payable using the canonical `providerDisbursement` event:

```text
Dr 2100 Provider Payable
Cr 1100 TRS Fund Cash
```

### FUND-003 — duplicate replay

Replaying the same approved claim with the same external idempotency key must create no second journal posting and no additional financial effect.

### FUND-004 — downward adjustment

A downward adjustment is an explicit compensating entry. It is not a silent mutation of the original transaction:

```text
Dr 2100 Provider Payable
Cr 5100 TRS Provider Compensation Expense
```

### FUND-005 — reversal

An erroneous approved claim is reversed with an equal-and-opposite posting while the original transaction identity remains addressable. Deleting or rewriting the original evidence is outside the contract.

## Fineract boundary

The static profile pins **Apache Fineract 1.15.0** as the reference ledger implementation. The project site and stable documentation identify 1.15.0 as the current stable release.

References:

- <https://fineract.apache.org/>
- <https://fineract.apache.org/docs/stable/>
- <https://github.com/apache/fineract/releases>

This contract uses only the bounded journal surface already recorded in `interop/fineract/journal-contract-v1.json`:

```text
POST /api/v1/journalentries
GET  /api/v1/journalentries
POST /api/v1/journalentries/{transactionId}/reversal
```

Accounting closures remain part of the canonical journal contract and are a later live-runtime threshold.

A successful Fineract request would prove only that the external ledger accepted a posting. It would not prove that the claim was eligible, correctly rated, authorized for payment, or compliant with any production administrator workflow.

## Static validation

Run:

```bash
python scripts/validate_trs_fund_public_model.py
python scripts/validate_trs_fund_runtime_contract.py
```

The runtime validator requires that:

- the public calibration and canonical journal schema remain the dependencies;
- every non-empty posting balances;
- every account reference exists in the canonical journal contract;
- claim and settlement postings exactly match canonical event mappings;
- the adjustment and reversal are equal-and-opposite to the approved-claim event;
- duplicate replay creates zero additional posting;
- Fineract never receives policy or payment-authorization authority; and
- the runtime layer defines neither rates nor an account catalog.

## Live Fineract threshold

This PR does **not** claim live Fineract execution. The next evidence threshold is a separate runtime lane:

1. start an exact pinned Fineract 1.15.0 test instance;
2. create only the canonical synthetic chart from `journal-contract-v1.json`;
3. post FUND-001 and read the resulting journal transaction back;
4. settle it with FUND-002;
5. replay FUND-001 and prove no second payable is created by the Baudot adapter;
6. execute the explicit adjustment and reversal cases;
7. exercise an accounting closure and a late-post negative case; and
8. preserve requests, responses, Fineract transaction IDs, readback state, and a sealed evidence manifest.

Suggested evidence shape:

```text
fund-runtime/
  expected.json
  journal-request.json
  journal-response.json
  journal-readback.json
  settlement-response.json
  reversal-response.json
  closure-response.json
  terminal-result.json
  bundle.manifest.sha256
```

## Claim boundary

The terminal result is a **synthetic financial-lifecycle proof** only. It is not a finding about production provider reimbursement, FCC payment authorization, Rolka Loube implementation compatibility, Fineract conformance, financial-statement compliance, provider certification, routing authority, or accessibility readiness.
