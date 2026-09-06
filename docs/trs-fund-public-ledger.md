# Public TRS Fund ledger proving ground

Baudot's TRS Fund work is a **public-data-backed accounting proving ground**, not a reconstruction of the Interstate TRS Fund administrator's production systems.

The model deliberately separates four authorities:

```text
FCC / Rolka Loube public formulas and reports
        |
        v
public fund-model fixtures
        |
        v
synthetic provider / contributor transactions
        |
        v
Apache Fineract manual journal-entry adapter
        |
        v
independent reconciliation / evidence
```

## Authority boundary

- **FCC / Rolka Loube public material** owns the source values used to calibrate rates, projected demand, public Fund requirements, contribution factors, and published program-year totals.
- **Baudot fund fixtures and reducers** own deterministic reproduction of those public calculations and synthetic test scenarios.
- **Apache Fineract** is an accounting executor / ledger substrate. It does not decide TRS eligibility, rate methodology, provider certification, contribution policy, demand assumptions, routing, numbering, or accessibility readiness.
- **Baudot reconciliation** decides whether the ledger postings produced by the adapter match the expected synthetic accounting transaction and public-model invariant.

A balanced Fineract journal entry therefore does **not** prove that a provider was entitled to compensation or that a contributor was assessed correctly.

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

The fund model does not consume the iTRS Numbering Directory as payment or contribution authority. Provider and contributor identities may be correlated across synthetic scenarios, but:

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

The routing CTE and the fund ledger can therefore be composed later without either becoming authority for the other.

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

It does **not** establish FCC approval, Rolka Loube production compatibility, provider reimbursement eligibility, contributor liability, Fund audit correctness, Fineract suitability for production TRS administration, financial-statement compliance, payment-network operation, or production security.
