# Synthetic TRS Fund: live Fineract proving lane

This lane is the first step beyond the public arithmetic model in `docs/trs-fund-public-ledger.md`.
It executes a deterministic Baudot-owned synthetic Fund scenario against an actual Apache Fineract instance and preserves the resulting external-ledger evidence.

It remains a **test bench**, not a production Fund implementation.

## Pinned implementation under test

The GitHub Actions lane pins Apache Fineract **1.15.0**, release commit:

```text
d5636847ac556c30b437254c353f05526d172b97
```

The workflow pulls the Apache-published Docker image tagged from that exact commit and uses the release's own Docker Compose configuration.
Fineract's Docker artifacts are treated only as development/test infrastructure.

The pin matters: an evidence bundle must identify which ledger implementation accepted a transaction.
A moving `latest` image would make a replay ambiguous.

## Base scenario

`testkit/fund/fineract-live-smoke-v1.json` declares the first complete accounting loop:

```text
$10,000 contributor assessment
        |
        v
$10,000 contributor receipt
        |
        v
$10,000 Fund cash
        |
        +--> $6,000 approved synthetic provider claim
        |             |
        |             v
        |        $6,000 payable
        |             |
        |             v
        +------> $6,000 disbursement
                      |
                      v
                 explicit reversal
                      |
                      v
                 explicit repost
```

Expected final synthetic balances:

```text
TRS Fund Cash                         4,000 debit
Contributor Receivable                   0
Provider Payable                         0
Contribution Revenue                10,000 credit
TRS Provider Compensation Expense    6,000 debit
```

The reversal is intentional. A happy-path posting alone does not prove that corrections preserve history.

## Accounting-closure probe

The same disposable Fineract instance then exercises a negative control:

```text
close accounting through 2026-09-05
        |
        +--> attempt $125 correction dated 2026-09-05
        |        expected: REJECT
        |        expected code:
        |        error.msg.glJournalEntry.invalid.accounting.closed
        |
        +--> post the same synthetic correction on 2026-09-06
                 expected: ACCEPT
                 |
                 v
              explicit reversal on open date
```

The correction uses the program-administration expense/payable mapping only as a synthetic accounting probe. It is not a real Fund administrative charge.

The open-date correction is reversed after verification so the base scenario's expected economic end state remains unchanged at $4,000 Fund cash.

`FUND-CLS-001` is **evidence-gated**. The static scenario intentionally does not list it in `requiredInvariants` before a live run. `scripts/run_fineract_fund_closure_probe.py` adds it to the evidence manifest only after all of the following are observed:

- the accounting closure exists for the declared office/date;
- the closed-date journal fails;
- the failure contains Fineract's specific accounting-closed error code;
- no successful transaction is accepted for that attempt;
- the same correction posts on the declared open date; and
- the open-date correction's original journal rows are marked reversed after cleanup.

This keeps a declared capability behind executable evidence rather than documentation.

## Authority boundary

Baudot determines the synthetic business event and expected accounting consequence.
Fineract only executes the journal instruction.

```text
synthetic event
    |
    v
Baudot event/authority reducer
    |
    v
journal contract
    |
    v
Fineract manual journal API
    |
    v
Fineract transaction ID + journal rows
    |
    v
independent Baudot reconciliation
```

Therefore:

```text
Fineract accepted the journal
!= provider was eligible
!= contributor was liable
!= payment was authorized by the FCC or Fund administrator
!= production Fund accounting is correct
```

## Account bootstrap

The live lane creates dedicated detail accounts using a `BAUDOT-` prefix and maps the synthetic Fund chart into Fineract resource IDs at runtime:

```text
1100  TRS Fund Cash
1200  Contributor Receivable
2100  Provider Payable
4100  Contribution Revenue
5100  TRS Provider Compensation Expense
5200  TRS Program Administration Expense
5300  NDBEDP Program Expense
```

The source account numbers remain Baudot's stable synthetic vocabulary. Fineract-generated numeric resource IDs are execution evidence, not domain identifiers.

## Evidence bundle

A run writes:

```text
artifacts/trs-fund-fineract/<scenario-id>/
  http/
    001-....json
    002-....json
    ...
  manifest.json
  summary.txt
```

The manifest records:

- synthetic business transaction IDs;
- event types and amounts;
- expected debit/credit accounts;
- Fineract transaction IDs;
- Fineract journal-entry IDs;
- the reversal API shape used;
- account-ID mappings;
- policy/source provenance;
- independently calculated ending balances;
- closure creation evidence;
- the rejected closed-date attempt and expected error code;
- the accepted open-date correction and cleanup reversal;
- invariant results; and
- a canonical SHA-256 over the manifest.

Before the closure probe rewrites the manifest hash, it preserves the pre-closure canonical hash inside the `closureProbe` evidence block. CI also retains the Fineract Docker Compose state and logs.

## Executable invariants

The lane reports these independently:

```text
FUND-ACC-001  every posted synthetic journal has the expected debit and credit
FUND-REC-001  contributor receivable returns to zero after receipt
FUND-CLM-001  an approved synthetic claim creates the declared accounting event
FUND-DIS-001  payable returns to zero after the effective disbursement
FUND-ADJ-001  reversal is explicit and followed by a distinct repost transaction
FUND-CLS-001  closed-date correction is rejected for ACCOUNTING_CLOSED and open-date correction succeeds
FUND-AUD-001  every effective event retains Fineract transaction/journal identifiers
FUND-AUT-001  Fineract acceptance never substitutes for program authorization
```

`EXPECTED-BALANCES` is also checked against the base scenario fixture.

## Reversal compatibility

The current lane first uses:

```text
POST /journalentries/{transactionId}?command=reverse
```

and retains compatibility with the older documented `/reversal` form as a fallback.
The evidence bundle records which API shape was actually accepted.

## Running locally

Against an already-running disposable Fineract test instance:

```bash
FINERACT_BASE_URL=https://localhost:8443/fineract-provider/api/v1 \
FINERACT_USERNAME=mifos \
FINERACT_PASSWORD=password \
FINERACT_TENANT=default \
FINERACT_INSECURE_TLS=1 \
TRS_FUND_EVIDENCE_DIR=artifacts/trs-fund-fineract \
python scripts/run_fineract_fund_lane.py

FINERACT_BASE_URL=https://localhost:8443/fineract-provider/api/v1 \
FINERACT_USERNAME=mifos \
FINERACT_PASSWORD=password \
FINERACT_TENANT=default \
FINERACT_INSECURE_TLS=1 \
TRS_FUND_EVIDENCE_DIR=artifacts/trs-fund-fineract \
python scripts/run_fineract_fund_closure_probe.py
```

Never point these scripts at a production Fineract tenant. They create synthetic GL accounts, post synthetic journals, and create an accounting closure.

## Next threshold

Once the live base lane and closure probe are green, the next increment is a **revised Form 499-A true-up without history rewriting**:

1. issue the original synthetic contributor assessment;
2. receive at least a partial payment;
3. introduce a revised filing with a changed revenue base;
4. calculate the delta as a new evidence-bearing adjustment rather than editing the original assessment;
5. exercise underpayment and overpayment/credit-balance cases;
6. preserve correlation between original filing, revision, assessment, receipt, and correction; and
7. reconcile the resulting receivable and cash positions through Fineract.

After that, the same event grammar can be replayed across multiple program years with a deterministic business-date clock.
