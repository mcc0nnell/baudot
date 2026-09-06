# Synthetic TRS Fund proving ground

Baudot's TRS Fund work is a **public-data-calibrated, synthetic end-to-end Fund proving ground**. It is not a reconstruction of the Interstate TRS Fund administrator's production systems, and it is not a generic banking demo.

The purpose is to make the financial lifecycle reproducible enough to test policy arithmetic, contributor obligations, provider compensation, ledger behavior, adjustments, reconciliation, and evidence preservation as one composed system while keeping each authority boundary explicit.

A useful shorthand is:

> **Fineract is the financial kernel. Baudot owns the synthetic Fund model, scenarios, invariants, and evidence.**

## End-to-end lifecycle

The proving ground models the Fund as a lifecycle rather than as a collection of unrelated accounting examples:

```text
public policy / program-year inputs
        |
        v
synthetic contributor revenue
        |
        v
assessment -> billing -> collection
        |
        v
Fund cash / receivables
        |
        +-------------------------------+
        |                               |
        v                               v
synthetic provider activity        policy / rate inputs
        |                               |
        +--------------+----------------+
                       v
                 claim calculation
                       |
                       v
             approval -> payable
                       |
                       v
                  disbursement
                       |
                       v
          adjustment / recovery / true-up
                       |
                       v
             reconciliation + audit evidence
```

The target is not merely to produce balanced entries. It is to preserve enough evidence to answer, for every synthetic dollar, **why it was assessed or paid, which policy version authorized the calculation, what accounting event represented it, what changed later, and whether the final Fund state reconciles**.

## Architecture and authority boundary

The model deliberately separates program authority from accounting execution:

```text
FCC / Rolka Loube public formulas and reports
        |
        v
public Fund-model fixtures
        |
        v
Baudot synthetic Fund domain
  contributors / assessments / claims / approvals /
  collections / disbursements / adjustments / recoveries
        |
        v
Apache Fineract journal adapter
        |
        v
Fineract general ledger
        |
        v
independent Baudot reconciliation / evidence
```

- **FCC / Rolka Loube public material** owns the source values used to calibrate rates, projected demand, public Fund requirements, contribution factors, and published program-year totals.
- **Baudot Fund fixtures and reducers** own deterministic reproduction of those public calculations and synthetic test scenarios.
- **The synthetic Fund domain** owns scenario state and program semantics. It decides what event the test says occurred; it does not outsource TRS policy to a banking data model.
- **Apache Fineract** is the external financial kernel: an accounting executor / ledger substrate. It does not decide TRS eligibility, rate methodology, provider certification, contribution policy, demand assumptions, routing, numbering, or accessibility readiness.
- **Baudot reconciliation** decides whether postings and resulting balances match the expected synthetic accounting transaction and Fund invariant.

A balanced Fineract journal entry therefore does **not** prove that a provider was entitled to compensation or that a contributor was assessed correctly.

## Current executable slice

The first public slice establishes both sides of the Fund rather than treating provider reimbursement as the entire system:

- public Fund-size and provider-rate calibration from Rolka Loube material;
- 2026/27 contributor assessment fixtures using approved FCC contribution factors;
- synthetic monthly and annual billing cases;
- minimum-contribution behavior;
- negative assessment and receipt cases;
- a machine-readable Fineract journal contract for claims, payments, assessments, and receipts; and
- independent validation in `scripts/validate_trs_fund_public_model.py`.

Relevant artifacts:

```text
docs/trs-fund-public-ledger.md
testkit/fund/rolka-loube-2025-26.json
testkit/fund/contributor-assessments-2026-27.json
interop/fineract/journal-contract-v1.json
scripts/validate_trs_fund_public_model.py
.github/workflows/trs-fund-public-model.yml
```

This is the first proving slice, not the finish line. The next threshold is a pinned external Fineract instance in CI with synthetic chart-of-accounts bootstrap, live journal posting, reversal, accounting closure, returned transaction IDs, and independent reconciliation.

## Long-horizon Fund test bench

The intended proving ground is **multi-period and replayable**. A mature scenario corpus should be able to advance the business date across multiple program years while preserving the policy version and evidence applicable to each event.

That allows scenarios such as:

```text
program year 1  ordinary assessments, receipts, claims, payments
program year 2  demand / contributor-base change
program year 3  delinquent contribution + anomalous provider claim
program year 4  rate or contribution-factor change + revised filing
program year 5  retroactive adjustment + recovery + final reconciliation
```

A replay can then change one declared policy or demand input and compare the resulting Fund state without mutating the original run.

The five-year corpus is a **test-bench direction**, not a claim that this first slice already implements five complete program years. Each scenario must earn its claim through executable fixtures, preserved transactions, and reconciliation evidence.

## Core Fund invariants

The test bench should make the important invariants machine-checkable. At minimum:

```text
FUND-ACC-001  every posted journal entry balances
FUND-REC-001  contributor receipts reconcile to assessments / credits
FUND-CLM-001  rejected or unapproved claims create no payable
FUND-DIS-001  duplicate payment attempts do not become duplicate Fund expense
FUND-ADJ-001  corrections preserve original history through reversal / compensation
FUND-CLS-001  closed-period behavior is explicit and evidence-preserving
FUND-AUD-001  reported balances are traceable to synthetic source events
FUND-AUT-001  accounting acceptance never substitutes for program authorization
```

Identifiers above define the proving-ground vocabulary; individual assertions become normative only when backed by executable fixtures and reducers in the repository.

## Public Fund-size calibration

The first executable Fund-size fixture uses Rolka Loube's April 30, 2025 Annual Report for the July 1, 2025 through June 30, 2026 program year and Rolka Loube's published per-minute rate table.

Public source pages:

- https://rolkaloube.com/programs/federal-itrs/forms-reports
- https://rolkaloube.com/programs/federal-itrs/trs-providers

The fixture reproduces the public analog calculation in Annual Report Table 4 from Table 3 projected minutes and the applicable 2024/25 and 2025/26 compensation rates:

```text
TTY
  Fund Requirement   = $5,660,825
  Two Month Reserve  =   $956,546

STS
  Fund Requirement   = $1,087,921
  Two Month Reserve  =   $185,804

CTS
  Fund Requirement   = $1,306,244
  Two Month Reserve  =   $193,282

Gross Analog Fund Requirement = $9,390,622
Net Analog Fund Requirement   = $8,212,726
```

The same April 2025 Annual Report publishes these proposal-stage 2025/26 totals, which the fixture preserves as historical reconciliation targets:

```text
Total Service Revenue Requirement  $1,753,281,830
NDBEDP                                 $10,000,000
Administrative Costs                   $30,079,185
Gross Fund Requirement              $1,793,361,015
Less projected Fund balance           $260,000,000
Net Fund Requirement                $1,533,361,015
```

The April report's proposed contribution bases and factors are retained as proposal-stage public calibration values:

```text
Analog contribution base  $31,985,845,946
Proposed analog factor     0.00026

IP-based contribution base $70,016,213,165
Proposed IP-based factor   0.02178
```

They are **not** treated as the final approved 2025/26 contribution factors. FCC Order DA-25-578 later approved `0.00025` for non-Internet-based TRS and `0.02086` for Internet-based TRS after updated demand, carryover, and contribution-base information.

## Contributor assessment model

The contributor side is modeled independently from provider compensation.

For Fund Year 2026/27, FCC Order DA-26-646 approves:

```text
Form 499-A line 514(b)
  interstate + international end-user revenue
  x 0.00021
  = non-Internet-based TRS obligation

Form 499-A line 514(a)
  intrastate + interstate + international end-user revenue
  x 0.02276
  = Internet-based TRS obligation
```

Public sources:

- https://docs.fcc.gov/public/attachments/DA-26-646A1.pdf
- https://rolkaloube.com/programs/federal-itrs/trs-contributors
- https://rolkaloube.com/trs-faqs
- https://docs.fcc.gov/public/attachments/DA-26-570A3.pdf

The Rolka Loube contributor FAQ documents the billing behavior used by the synthetic fixture:

- assessments are based on Form 499-A data;
- annual assessments over $1,200 may be billed monthly at one-twelfth when the account is in good standing;
- annual assessments at or below $1,200 are billed annually;
- accounts not in good standing are billed annually even when the assessment exceeds $1,200; and
- the Form 499-A instructions establish a $25 minimum TRS contribution for filers with end-user revenues.

The testkit therefore includes synthetic contributors exercising all four cases: a large monthly-billed contributor, a small annually billed contributor, a large contributor not in good standing, and a filer whose calculated obligation is raised to the $25 minimum.

The contributor reducer also carries explicit negative scenarios:

```text
wrong program-year factor
line 514(a) / 514(b) swapped
duplicate assessment
revised 499-A without adjustment evidence
monthly billing below threshold
monthly billing while not in good standing
receipt applied to wrong assessment
overpayment without credit-balance evidence
```

## Why Fineract

Fineract already exposes general-ledger accounts, manual journal entries, reversals, running balances, accounting rules, and accounting closures. That makes it useful as an **external ledger implementation under test** without pretending its lending/savings domain model is the TRS Fund domain model.

The first adapter contract is intentionally small:

```text
provider claim approved
  Dr TRS Provider Compensation Expense
  Cr Provider Payable

provider disbursement
  Dr Provider Payable
  Cr Cash / TRS Fund

contributor assessment
  Dr Contributor Receivable
  Cr Contribution Revenue

contributor receipt
  Dr Cash / TRS Fund
  Cr Contributor Receivable
```

Adjustments use explicit compensating entries or Fineract's journal-entry reversal path; they are never silently rewritten in place.

## Synthetic transaction layer

Provider and contributor transactions in this repository are synthetic. A fixture may intentionally include:

- duplicate claim identifiers;
- the wrong compensation-rate period;
- a claim above the synthetic eligible-minute total;
- a payment posted twice;
- an adjustment after payment;
- an assessment/receipt mismatch;
- a revised Form 499-A contribution base;
- a duplicate or stale contributor assessment;
- a transaction crossing an accounting closure;
- a balanced journal whose business invariant is nevertheless false.

The point is to prove that **accounting validity and program validity remain separate facts**.

## Independence from iTRS routing

The Fund model does not consume the iTRS Numbering Directory as payment or contribution authority. Provider and contributor identities may be correlated across synthetic scenarios, but:

```text
iTRS route eligibility
!= FCC provider certification
!= reimbursable minutes
!= approved claim
!= payment authorization
!= successful ledger posting

Form 499-A revenue
!= contribution factor
!= assessment issued
!= receipt collected
!= ledger reconciliation
```

The routing CTE and the Fund ledger can therefore be composed later without either becoming authority for the other.

## Public-source boundary

The proving ground uses only public material and Baudot-owned synthetic records. It does not contain or reconstruct:

- nonpublic provider RSDR submissions;
- confidential provider cost or demand data;
- production Rolka Loube schemas, credentials, workflows, or banking details;
- live Form 499-A contributor revenue filings;
- live contributor account or invoice data;
- live subscriber records;
- production iTRS Numbering Directory data.

Where a public report states that underlying provider or contributor data are confidential, the repository treats the published aggregate/formula as the calibration boundary and does not infer hidden entity-level values.

## Claim boundary

A passing public-model test proves only that Baudot can reproduce the declared public arithmetic, calculate synthetic contributor assessments under the declared public rules, and map synthetic Fund events into a balanced accounting contract. A future live Fineract lane may prove that a pinned Fineract build accepted and reversed those synthetic journal entries.

The larger proving-ground architecture is intentionally capable of composing contribution, compensation, disbursement, adjustment, closure, and reconciliation scenarios over time, but **no scenario is considered proven merely because the architecture can represent it**.

It does **not** establish FCC approval, Rolka Loube production compatibility, provider reimbursement eligibility, contributor liability, Fund audit correctness, Fineract suitability for production TRS administration, financial-statement compliance, payment-network operation, or production security.
