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

A balanced Fineract journal entry therefore does **not** prove that a provider was entitled to compensation.

## First public calibration target

The first executable fixture uses Rolka Loube's April 30, 2025 Annual Report for the July 1, 2025 through June 30, 2026 program year and Rolka Loube's published per-minute rate table.

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

The same public Annual Report publishes these broader 2025/26 totals, which the fixture preserves as reconciliation targets:

```text
Total Service Revenue Requirement  $1,753,281,830
NDBEDP                                 $10,000,000
Administrative Costs                   $30,079,185
Gross Fund Requirement              $1,793,361,015
Less projected Fund balance           $260,000,000
Net Fund Requirement                $1,533,361,015
```

The reported contribution bases and factors are also retained as public calibration values:

```text
Analog contribution base  $31,985,845,946
Analog factor              0.00026

IP-based contribution base $70,016,213,165
IP-based factor            0.02178
```

The validator calculates the unrounded ratios and requires them to round to the reported five-decimal factors.

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
- a transaction crossing an accounting closure;
- a balanced journal whose business invariant is nevertheless false.

The point is to prove that **accounting validity and program validity remain separate facts**.

## Independence from iTRS routing

The fund model does not consume the iTRS Numbering Directory as payment authority. Provider identities may be correlated across synthetic scenarios, but:

```text
iTRS route eligibility
!= FCC provider certification
!= reimbursable minutes
!= approved claim
!= payment authorization
!= successful ledger posting
```

The routing CTE and the fund ledger can therefore be composed later without either becoming authority for the other.

## Public-source boundary

The proving ground uses only public material and Baudot-owned synthetic records. It does not contain or reconstruct:

- nonpublic provider RSDR submissions;
- confidential provider cost or demand data;
- production Rolka Loube schemas, credentials, workflows, or banking details;
- live contributor revenue filings;
- live subscriber records;
- production iTRS Numbering Directory data.

Where a public report states that underlying provider data are confidential, the repository treats the published aggregate as the calibration boundary and does not infer hidden provider-level values.

## Claim boundary

A passing public-model test proves only that Baudot can reproduce the declared public arithmetic and can map synthetic fund events into a balanced accounting contract. A future live Fineract lane may prove that a pinned Fineract build accepted and reversed those synthetic journal entries.

It does **not** establish FCC approval, Rolka Loube production compatibility, provider reimbursement eligibility, Fund audit correctness, Fineract suitability for production TRS administration, financial-statement compliance, payment-network operation, or production security.