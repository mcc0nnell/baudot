# Celix VRS compensability composition

This slice moves the next authority boundary into the Apache Celix runtime: VRS compensability classification derived from the clean-room Part 64 contract in PR #131.

It deliberately does **not** turn ordinary call placement, completed-call evidence, or a compensation candidate into a payable Fund claim.

## Decision chain

```text
PJSIP parser evidence
  -> call admission
  -> Shiro-shaped actor context
  -> Ranger-shaped authorization
  -> TRS ordinary-call placement authority
  -> completed-call / compensation-candidate evidence
  -> VRS compensability
  -> payable claim remains separate
```

The new contract is:

```text
ICompensabilityService 1.0.0
```

Its decision carries two independent booleans from the #131 semantics:

```text
eligibleToSeekCompensation
establishedCompensable
```

Those states must never be treated as equivalent.

## Narrow domestic VRS facts

The first profile consumes only synthetic clean-room facts:

```text
completedInternetBasedTrsCall
providerCommissionCertified
upstreamUserValidated
callRecordComplete
prohibitedIncentiveKnown
unauthorizedOrUnnecessaryUseKnown
providerInvolvedRemoteTraining
internationalIpOrigin
executiveCertificationPresent
auditPaymentSuspended
withholdingState
administratorDetermination
```

The international travel-exception profile, IVCS timing rules, withholding lifecycle, audit cure, and aggregate monthly controls remain in their existing Part 64 lanes rather than being silently flattened into this first Celix service.

## Three compositions

All three compositions preserve exactly the same upstream runtime evidence:

```text
SignalingParser       PJSIP_PARSE_ACCEPTED
CallAdmission         PJSIP_UAS_TEXT_PROFILE_ADMITTED
ActorAuthentication   SHIRO_CONTEXT_AUTHENTICATED
Authorization         RANGER_ALLOW
TrsBusinessAuthority  TRS_ORDINARY_CALL_PLACEMENT_ALLOWED
```

Only compensability facts differ.

### Explicit external determination

The complete synthetic domestic candidate includes an explicit external administrator/Commission determination of `compensable`:

```text
VrsCompensability     VRS_COMPENSABILITY_EXTERNALLY_ESTABLISHED
  eligibleToSeekCompensation = true
  establishedCompensable     = true

PayableClaimBoundary  NOT_MODELED
```

The external determination is an explicit synthetic input shaped by PR #131. Celix does not manufacture it.

### Candidate remains pending

With the same candidate evidence but `administratorDetermination = pending`:

```text
VrsCompensability     VRS_COMPENSABILITY_PENDING_EXTERNAL_DETERMINATION
  eligibleToSeekCompensation = true
  establishedCompensable     = false

PayableClaimBoundary  NOT_MODELED
```

This mechanically proves:

```text
eligible to seek compensation
!= established compensable
```

### Placement allowed but call never completed

The third control keeps the same successful parser, admission, authentication, authorization, and ordinary-call placement evidence, and even injects the same synthetic `compensable` determination string, but the completed-call fact is false:

```text
VrsCompensability     VRS_COMPENSABILITY_INELIGIBLE_CALL_NOT_COMPLETED
  eligibleToSeekCompensation = false
  establishedCompensable     = false

PayableClaimBoundary  NOT_MODELED
```

The service rejects the candidate before using the determination. This proves:

```text
ordinary call placement allowed
!= call completed
```

and prevents a downstream authority token from repairing missing upstream call evidence.

## Core invariants

```text
parser accepted
!= call admitted
!= actor authenticated
!= policy authorized
!= ordinary call placement allowed
!= call completed
!= compensation candidate eligible
!= externally established compensable
!= rate calculated
!= payable claim
!= journal entry
!= payment authorized
!= settlement
```

The validator requires parser, admission, actor, Ranger, and TRS business-authority evidence to remain identical across the three compensability profiles.

## Relationship to the existing Fund chain

PR #131 remains the semantic authority for the compensability state machine. Later aggregate controls consume call-level compensability without becoming a second compensability authority, and the rate engine consumes already-established compensable minutes without creating them. Accounting and settlement remain still later boundaries.

## Claim boundary

This is a contract-derived synthetic composition. It does not establish a real TRS Fund administrator decision, provider certification, production CDR truth, real compensable minutes, a payable claim, a compensation rate, a Fineract journal, payment authorization, settlement, or regulatory compliance.

## Next threshold

The next safe runtime boundary is **claim creation**, not another compensability rule. It should consume only terminal externally-established compensability plus the separate rate/aggregate prerequisites already modeled elsewhere, and prove that a compensable determination still cannot create a payable claim without an explicit claim-authority decision.
