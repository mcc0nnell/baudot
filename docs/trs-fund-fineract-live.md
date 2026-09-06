# Live Apache Fineract TRS Fund proving slice

This lane crosses the next synthetic Fund threshold: canonical Baudot journal intents are posted to a real, ephemeral Apache Fineract instance and independently read back and reconciled.

It is deliberately **not** a reconstruction of a production TRS Fund administrator, a production payment system, or a statement that balanced accounting proves program entitlement.

## Authority chain

```text
public FCC / Rolka Loube evidence
        -> landed public Fund calibration
        -> canonical Fund lifecycle contract
        -> deterministic synthetic event runtime
        -> canonical journal intents
        -> this live Fineract adapter
        -> Fineract manual journal API
        -> independent readback / reconciliation
```

The live adapter consumes `journalIntents` emitted by `scripts/run_trs_fund_scenario.py`. It never consumes raw provider claims or contributor filings as direct accounting authority.

## Exact external implementation

The admitted implementation is:

```text
Apache Fineract release: 1.15.0
annotated tag object:    9e76f088db71a4458b68f7855b03b21d23b86f1c
release commit:          d5636847ac556c30b437254c353f05526d172b97
```

The annotated release tag is verified upstream. CI checks out the exact release commit and builds the local `fineract:latest` image from that source using Fineract's own Gradle/Jib build path. `latest` is therefore only the local image tag produced inside the job; it is **not** a floating registry authority.

The upstream Docker composition is testing-only. Baudot preserves that boundary. The adapter refuses non-loopback hosts and uses only the upstream default test tenant and default test credentials inside the ephemeral CI runner.

## API correction discovered by the proving ground

The first live-integration pass caught a contract error.

The old Baudot contract described reversal as:

```text
/api/v1/journalentries/{transactionId}/reversal
```

Apache Fineract 1.15.0 actually implements:

```text
POST /api/v1/journalentries/{transactionId}?command=reverse
```

The canonical `journal-contract-v1.json` is corrected on this branch and the static live-profile validator prevents the old shape from returning.

This is the intended role of the external implementation: it tests Baudot's accounting adapter contract rather than silently inheriting it.

## Executed transaction loop

The deterministic `fund-year-1-smoke` scenario emits four canonical intents:

```text
contributorAssessment  2400.00  Dr Contributor Receivable / Cr Contribution Revenue
contributorReceipt     2400.00  Dr Cash / Cr Contributor Receivable
providerClaimApproved  1650.00  Dr Provider Compensation Expense / Cr Provider Payable
providerDisbursement   1650.00  Dr Provider Payable / Cr Cash
```

The adapter then:

1. creates or verifies the seven-account synthetic chart from `journal-contract-v1.json`;
2. posts each intent as a balanced Fineract manual journal;
3. captures the returned Fineract transaction ID;
4. reads the transaction back by transaction ID;
5. verifies exact debit account, credit account, amount, and journal entry IDs;
6. independently reconstructs the scenario balances from Fineract readback;
7. proves adapter-level duplicate suppression without making a second Fineract call;
8. reverses the provider-claim transaction through the exact 1.15.0 reversal API;
9. verifies the original entries are marked reversed and the reversal entries invert debit/credit while preserving amount/date;
10. creates an accounting closure dated `2026-08-05`;
11. proves a new journal on the closed date is rejected; and
12. proves reversal of the `2026-08-05` provider-disbursement journal is rejected after closure.

The scenario-to-ledger reconciliation occurs **before** the deliberate reversal probe. The reversal then intentionally changes ledger state and is treated as separate lifecycle evidence rather than silently rewriting the synthetic business scenario.

## Canonical chart

The external ledger receives only the canonical synthetic accounts already defined by Baudot:

```text
1100 TRS Fund Cash                         ASSET
1200 Contributor Receivable                ASSET
2100 Provider Payable                      LIABILITY
4100 Contribution Revenue                  INCOME
5100 TRS Provider Compensation Expense     EXPENSE
5200 TRS Program Administration Expense    EXPENSE
5300 NDBEDP Program Expense                EXPENSE
```

Fineract assigns runtime resource IDs. Baudot preserves the stable GL codes and records the resulting code-to-resource-ID map as evidence.

## Idempotency boundary

Fineract transaction IDs are ledger identities, not Baudot business identities.

Baudot retains the synthetic business transaction ID as the adapter idempotency key:

```text
syntheticBusinessTransactionId
        -> adapter replay check
        -> at most one Fineract POST
        -> returned Fineract transactionId
```

The live gate deliberately retries the first accepted intent and requires the adapter to return the same recorded transaction ID without increasing the Fineract API-call count.

## Evidence

The workflow preserves:

- exact Fineract release and commit identity;
- canonical scenario evidence;
- live-profile and journal-contract hashes;
- GL code -> Fineract resource ID mapping;
- every sanitized API request/response body except authentication headers;
- Fineract transaction and journal-entry IDs;
- pre-reversal scenario reconciliation;
- reversal readback;
- accounting-closure response;
- closed-period posting and reversal failures;
- Docker Compose state/logs;
- local Fineract image inspection; and
- SHA-256 over the primary evidence files.

No authentication header or password is written to the evidence JSON.

## Claim boundary

A green live gate establishes a narrow execution fact:

> Apache Fineract 1.15.0, built from the pinned release source in an ephemeral test stack, accepted the four synthetic balanced journal intents; Baudot read them back and reconciled the declared pre-reversal scenario state; Fineract also executed the explicit reversal and enforced the declared accounting closure controls.

It does **not** establish:

- provider certification or reimbursement eligibility;
- contributor legal liability;
- FCC payment authorization;
- compatibility with a production Fund administrator;
- production banking/payment-rail operation;
- financial-statement or audit compliance;
- Apache Fineract conformance generally;
- routing or numbering authority; or
- communications accessibility readiness.

The stronger rule remains:

```text
balanced Fineract journal
!= approved TRS claim
!= authorized payment
```
