# Part 64 VRS compensation rate engine

Status: implementation slice / public-rate calibrated

This slice connects the terminal VRS compensability decision to the compensation-rate calculation in 47 CFR § 64.643. It is the last regulatory arithmetic step before Baudot's synthetic Fund claim/accounting lifecycle.

## Core invariant

```text
externally established compensable minutes
!= rate class
!= rate calculation
!= payable Fund claim
!= journal entry
!= settlement
```

The rate engine may calculate a synthetic amount only after the upstream compensability lane supplies a terminal count of externally established compensable conversation minutes. It never creates compensable minutes itself.

## Authority split

Two public sources have deliberately different authority:

1. **47 CFR § 64.643** defines the regulatory tier semantics, annual inflation formula, Video-Text additive structure, and exogenous-cost conditions through June 30, 2028.
2. **Rolka Loube's public TRS Providers page** supplies the published 2026-27 per-minute reimbursement amounts used as the current operational rate input.

The public administrator page is therefore not allowed to redefine the CFR boundary. The current fixture explicitly records:

```text
small provider = one million monthly conversation minutes or less
large provider = more than one million monthly conversation minutes
```

## 2026-27 published inputs

For July 1, 2026 through June 30, 2027, the public fixture pins:

```text
small-provider rate      $8.61 / minute
large Tier I             $6.96 / minute for first 1,000,000
large Tier II            $4.35 / minute above 1,000,000
Video-Text additive      $0.22 / Video-Text minute
```

These are input data for synthetic calculation. The fixture does not claim rate-setting authority.

## Exact tier boundary

The first two executable arms intentionally sit one minute apart:

```text
1,000,000 minutes
  -> small-provider formula
  -> 1,000,000 * $8.61
  -> $8,610,000.00

1,000,001 minutes
  -> large-provider formula
  -> first 1,000,000 * $6.96
  -> next 1 * $4.35
  -> $6,960,004.35
```

The discontinuity is preserved because the reducer implements the rule as written rather than interpolating between classifications.

## Additional executable arms

- `VRS-RATE-LARGE-1250000` — first million at Tier I plus 250,000 Tier II minutes.
- `VRS-RATE-VIDEO-TEXT-1000` — all 1,000 small-provider minutes also receive the $0.22 Video-Text additive.
- `VRS-RATE-VIDEO-TEXT-PARTIAL` — only the 250 Video-Text minutes receive the additive.
- `VRS-RATE-EXOGENOUS-APPROVED` — a fully synthetic provider-specific adjustment is applied only when every § 64.643(d) gate and external Commission-approval input is true.
- `VRS-RATE-EXOGENOUS-NOT-APPROVED` — identical synthetic cost facts without Commission approval produce zero exogenous adjustment.
- `VRS-RATE-NO-COMPENSABILITY-001` — missing terminal compensable-minute input blocks rate calculation entirely.

## Formula-only controls

`vrs-rate-formula-cases.json` exercises the rule formulas without asserting real values:

```text
inflation:
A_FY = A_FY-1 * (1 + IF_FY)

exogenous adjustment:
approved claims / projected Fund-Year minutes
```

The formula controls are explicitly synthetic. They do not assert an FCC inflation factor, approved cost claim, published rate, or payment.

## Classification-minute caution

The first executable version requires:

```text
monthlyConversationMinutesForRateClassification
== externallyEstablishedCompensableMinutes
```

This is intentional. If a future source establishes how a divergent classification denominator must be treated, Baudot can add that arm explicitly. Until then, the reducer refuses to invent policy where the source model is ambiguous.

## Accounting handoff

A successful rate result remains a calculated regulatory amount only:

```text
Part 64 evidence
      |
      v
external compensability determination
      |
      v
§ 64.643 rate engine
      |
      v
synthetic calculated compensation amount
      |
      v
claim lifecycle / approval
      |
      v
Fineract journal adapter
```

Every fixture keeps `payableFundClaimCreated=false`. Fineract may consume a later approved claim amount; it cannot choose a § 64.643 rate, tier, exogenous adjustment, or compensability state.

## Clean-room boundary

No production provider minutes, real Fund claim, actual exogenous-cost claim, payment instruction, provider financial record, or rate-approval decision is present. Public rates are calibration inputs; all transaction/minute cases are Baudot-authored synthetic fixtures.
