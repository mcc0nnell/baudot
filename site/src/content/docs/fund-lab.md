---
title: Synthetic TRS Fund Lab
description: A public-data-calibrated, replayable Fund workload with Apache Fineract as an external accounting kernel.
---

Baudot's Fund lane asks a different version of the same question as the communications lab: **what can the preserved evidence actually prove?**

The Synthetic TRS Fund Lab turns public program rules and Baudot-owned synthetic records into a reproducible financial workload. It is not a reconstruction of the Interstate TRS Fund administrator's production system, and it is not a generic banking demo.

The design goal is a Fund-in-a-bottle test bench that can replay assessments, receipts, claims, disbursements, corrections, accounting closures, and future true-ups while preserving the authority boundary for every step.

## One synthetic dollar loop

The current base scenario deliberately exercises more than a happy-path journal:

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
                 distinct repost

expected ending Fund cash: $4,000
```

The reversal matters. A system that can post a transaction but cannot preserve correction history has not demonstrated the accounting behavior this lab is trying to prove.

## Program authority stays outside the ledger

Apache Fineract is used as an **external accounting implementation under test**. It does not become the TRS policy engine.

| Baudot / synthetic Fund domain owns | Fineract owns |
| --- | --- |
| provider and contributor identity | GL resource IDs |
| filing and revision lineage | journal acceptance or rejection |
| public-rule and rate selection | debit and credit rows |
| claim approval state | transaction and journal-entry IDs |
| payment authorization state | explicit reversals |
| scenario correlation and idempotency | accounting closure |
| independent expected balances | ledger balances |

A provider is therefore not automatically modeled as a Fineract client, and an accepted Fineract journal is not evidence that a provider was eligible or a contributor was liable.

```text
ledger accepted = true
program authorized = ?
```

Those are separate facts.

## Canonical synthetic chart

The first ledger contract uses a deliberately small account vocabulary:

| Account | Synthetic role | Type |
| --- | --- | --- |
| `1100` | TRS Fund Cash | Asset |
| `1200` | Contributor Receivable | Asset |
| `2100` | Provider Payable | Liability |
| `4100` | Contribution Revenue | Income |
| `5100` | TRS Provider Compensation Expense | Expense |
| `5200` | TRS Program Administration Expense | Expense |
| `5300` | NDBEDP Program Expense | Expense |

The core event mapping is deterministic:

```text
contributorAssessment
  Dr 1200 Contributor Receivable
  Cr 4100 Contribution Revenue

contributorReceipt
  Dr 1100 TRS Fund Cash
  Cr 1200 Contributor Receivable

providerClaimApproved
  Dr 5100 TRS Provider Compensation Expense
  Cr 2100 Provider Payable

providerDisbursement
  Dr 2100 Provider Payable
  Cr 1100 TRS Fund Cash
```

Future overpayments are intended to use an explicit contributor-credit liability rather than hiding a credit balance as a negative receivable.

## The Fineract lane is source-pinned

The live lane checks out Apache Fineract `1.15.0`, verifies the expected source commit, and builds the test container from that exact tree with Fineract's own `:fineract-provider:jibDockerBuild` task.

The evidence bundle records:

- release and source commit;
- source tree;
- Java and Gradle versions;
- build task;
- local container image ID and tags;
- Fineract transaction and journal-entry IDs;
- account resource mappings;
- sanitized API requests and responses;
- independent ending balances; and
- a canonical scenario-manifest hash.

That means the test does not depend on a moving external `latest` image or assume that a matching Docker Hub release tag exists. Fineract's upstream Compose file still expects `fineract:latest`, so CI aliases the exact locally built image to that name only after provenance has been captured.

## Accounting closure is a negative control

The lab also asks Fineract to reject something:

```text
close accounting through 2026-09-05
        |
        +--> post $125 correction on 2026-09-05
        |        expected: reject as ACCOUNTING_CLOSED
        |
        +--> post the same correction on 2026-09-06
                 expected: accept
                 |
                 v
              reverse it explicitly
```

`FUND-CLS-001` is evidence-gated. The invariant is not promoted merely because the fixture says it should work; the live run must preserve the observed rejection, open-date acceptance, and cleanup reversal.

## Toward a five-year replay

The useful destination is not one balanced month. It is a deterministic workload that can carry policy and evidence across time:

```text
Year 1  ordinary assessments, receipts, claims, payments
Year 2  demand and contribution-base change
Year 3  delinquency and anomalous provider activity
Year 4  rate change plus revised Form 499-A
Year 5  retroactive adjustment, recovery, and final reconciliation
```

A revised filing should create a new evidence-bearing delta, not rewrite the original assessment. The same principle applies to provider corrections: preserve the original event, record the correction, and make the resulting ledger state explainable.

## What a passing run would mean

A successful live lane can establish that a pinned Fineract build executed the declared synthetic accounting behavior and that Baudot independently reconciled the result.

It does **not** establish FCC approval, provider eligibility, contributor liability, production Rolka Loube compatibility, payment-network operation, financial-statement compliance, production Fineract suitability, or production security.

That claim boundary is part of the result, not a disclaimer added afterward.

### Source material

- [Synthetic TRS Fund proving ground](https://github.com/mcc0nnell/baudot/blob/main/docs/trs-fund-public-ledger.md)
- [Live Fineract proving lane](https://github.com/mcc0nnell/baudot/blob/main/docs/trs-fund-fineract-live-lane.md)
- [Machine-readable journal contract](https://github.com/mcc0nnell/baudot/blob/main/interop/fineract/journal-contract-v1.json)
