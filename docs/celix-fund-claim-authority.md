# Celix Fund claim authority

This slice extends Baudot's Celix authority graph through the synthetic TRS Fund claim decision without allowing claim approval to become accounting, payment, settlement, or regulatory authority.

## Semantic sources

The runtime contract is derived from three existing clean-room Baudot boundaries:

- PR #131 — terminal VRS compensability remains externally established;
- PR #136 — the § 64.643 rate engine produces a separate typed rate result and explicitly does not create a payable Fund claim;
- PR #137 — synthetic Fund claim approval consumes terminal compensability plus the exact rate result and remains distinct from provider-payable accrual and payment authorization.

## New service

```text
IFundClaimAuthority 1.0.0
```

The first operation is intentionally narrow:

```text
evaluateVrsClaim(compensability, rate, claimFacts)
```

It consumes:

```text
CompensabilityDecision
RateDecision
FundClaimFacts
```

and returns:

```text
FundClaimDecision
```

The claim service cannot calculate a compensation rate. `RateDecision` is a typed result supplied from the separate PR #136 authority boundary.

## Runtime chain

```text
PJSIP parse
  -> call admission
  -> Shiro-shaped authentication
  -> Ranger-shaped authorization
  -> TRS ordinary-call business authority
  -> VRS compensability
  -> typed VRS rate result
  -> Fund claim authority
  -> provider payable remains NOT_MODELED
```

## Five compositions

### 1. Approved

```text
VrsCompensability  VRS_COMPENSABILITY_EXTERNALLY_ESTABLISHED
VrsRateResult       VRS_RATE_RESULT_AVAILABLE ($8,830.00)
claimDecision       approved
approved amount     $8,830.00

FundClaimAuthority  FUND_CLAIM_APPROVED
ProviderPayableBoundary NOT_MODELED
```

This establishes only a synthetic claim decision.

### 2. Compensability pending

The profile deliberately supplies both a valid rate result and an injected `claimDecision=approved`, but compensability remains pending.

Required result:

```text
FUND_CLAIM_NOT_EVALUATED_COMPENSABILITY_REQUIRED
```

A downstream claim token cannot repair a missing terminal compensability decision.

### 3. Rate missing

Terminal compensability and `claimDecision=approved` are present, but no completed rate result exists.

Required result:

```text
FUND_CLAIM_NOT_EVALUATED_RATE_REQUIRED
```

The claim service does not calculate or infer the § 64.643 rate.

### 4. Claim pending

Terminal compensability and the exact $8,830.00 rate result are present, but the synthetic claim decision remains pending.

Required result:

```text
FUND_CLAIM_PENDING_DECISION
```

This proves:

```text
externally established compensability
!= rate calculated
!= claim approved
```

### 5. One-cent mismatch

```text
rate result            $8,830.00
approved claim amount  $8,829.99
```

Required result:

```text
FUND_CLAIM_REJECTED_AMOUNT_MISMATCH
```

The claim layer cannot silently rewrite the upstream regulatory calculation.

## Core invariant

```text
parser accepted
!= call admitted
!= actor authenticated
!= policy authorized
!= ordinary call placement allowed
!= call completed
!= externally established compensable
!= rate calculated
!= synthetic claim approved
!= provider payable accrued
!= Fineract journal posted
!= payment authorized
!= Fund cash moved
!= settlement reconciled
```

## Evidence behavior

The validator requires the parser, admission, authentication, authorization, and TRS business-authority observations to remain identical across all five claim profiles. Claim outcomes therefore cannot rewrite upstream evidence.

The successful claim observation includes the exact approved amount, but the terminal boundary remains:

```text
ProviderPayableBoundary  NOT_MODELED
```

No accounting mutation is performed by this slice.

## Privacy and clean-room boundary

The composition uses only synthetic IDs and fixed synthetic monetary values inherited from the clean-room rate/claim fixtures. It contains no production Fund claim, provider-confidential data, subscriber identity, bank information, payment instruction, or production Fineract transaction.

## What this does not establish

A green run does not establish:

- a real FCC or Fund administrator claim decision;
- a live § 64.643 rate calculation;
- provider eligibility or regulatory compliance;
- provider-payable accrual;
- Fineract posting;
- payment authorization;
- cash movement; or
- settlement/reconciliation.

## Next threshold

The next Celix authority boundary should be provider-payable accounting intent. It must consume an approved `FundClaimDecision` and preserve the canonical Fineract journal contract without allowing ledger acceptance to create claim approval or payment authorization.
