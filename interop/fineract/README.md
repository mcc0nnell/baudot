# Fineract synthetic Fund execution lane

This directory is the accounting-execution boundary for Baudot's synthetic TRS Fund proving ground.

Baudot remains the business/policy oracle. Apache Fineract is an external ledger implementation under test.

## Contract

`journal-contract-v1.json` defines the synthetic chart of accounts, event-to-journal mappings, evidence fields, claim exclusions, and the pinned API assumptions for Apache Fineract 1.15.0.

The active write surfaces are:

```text
POST /api/v1/journalentries
POST /api/v1/journalentries/{transactionId}?command=reverse
POST /api/v1/glclosures
POST /api/v1/glaccounts        # only when explicit bootstrap is enabled
```

Every Fineract write receives the Baudot synthetic business transaction ID as the `Idempotency-Key` header. The same ID is also recorded as the manual journal `referenceNumber` when a journal entry is created.

A Fineract manual-journal reversal is not a generic later-period correction. Fineract creates the reversal on the original journal date and rejects it if that original date is already covered by an accounting closure. Baudot therefore permits `TRANSACTION_REVERSED` only when the target transaction date is still open and requires the reversal event to use that same accounting effective date. A correction to a closed-period transaction must be an explicit compensating adjustment posted in an open period.

## Executor

`fineract_executor.py` provides:

- contract-driven GL account resolution and optional synthetic account bootstrap;
- journal planning for assessments, receipts, claims, disbursements, and directional adjustments;
- explicit Fineract journal reversal using the transaction ID returned by Fineract, with original-date enforcement;
- accounting closure execution;
- transaction-level verification by reading the created debit/credit journal rows back from Fineract;
- final Fund reconciliation by independently comparing the natural balances of the dedicated synthetic GL accounts with Baudot's deterministic Fund reducer;
- an execution evidence ledger containing Fineract transaction IDs and journal-entry IDs.

A successful HTTP response is not a passing result. The executor reads the resulting Fineract journal rows back and marks an operation reconciled only when the expected debit, credit, amount, and balance are present.

## Five-year runner

From the repository root, validate the default five-year scenario without touching Fineract:

```bash
python scripts/run_fineract_fund_scenario.py --plan-only
```

For an explicitly configured test instance:

```bash
export FINERACT_BASE_URL=https://localhost:8443/fineract-provider
export FINERACT_USERNAME=mifos
export FINERACT_PASSWORD='...'
export FINERACT_TENANT_ID=default

python scripts/run_fineract_fund_scenario.py \
  --bootstrap-accounts \
  --evidence-out artifacts/fineract-five-year-evidence.json
```

`--bootstrap-accounts` is intentionally opt-in. Without it, all contract GL codes must already exist and missing accounts fail closed.

The live runner first folds and validates the complete Baudot scenario. Only after that succeeds does it issue Fineract writes. At the end it queries the dedicated synthetic accounts and exits nonzero if Fineract's balances do not match the independent Baudot state.

## Security and scope

- The repository contains no Fineract credentials.
- TLS verification is not disabled by the executor; a local HTTPS test instance must use a certificate trusted by the runner environment.
- The runner is for an isolated synthetic test instance, not a production financial system.
- The chart of accounts must be dedicated to the synthetic proving ground for final account-balance reconciliation to be meaningful.
- Fineract acceptance does not establish provider eligibility, contributor liability, payment authorization, FCC approval, production Rolka Loube compatibility, or financial-statement compliance.
