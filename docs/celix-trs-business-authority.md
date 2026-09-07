# Celix TRS business-authority composition

This slice moves the first Baudot-owned TRS business decision into the Apache Celix runtime without collapsing policy authorization, call placement, compensability, Fund authority, or regulatory compliance into one verdict.

The semantic source is the clean-room Part 64 registration, numbering, and per-call validation contract in PR #126.

## Decision chain

```text
PJSIP parser evidence
  -> call admission
  -> Shiro-shaped actor context
  -> Ranger-shaped authorization
  -> TRS ordinary-call business authority
  -> downstream Fund/compensability authority remains separate
```

The new service contract is:

```text
ITrsBusinessAuthority 1.0.0
```

and the first operation is deliberately narrow:

```text
evaluateOrdinaryCallPlacement(actor, authorization, facts)
```

## Privacy-safe facts

The service receives only synthetic boolean/state facts needed to exercise the PR #126 boundary:

```text
routePresent
registered
identityVerified
perCallValidated
emergencyException
serviceType
```

It does not receive a telephone number, subscriber name/address, raw identity attributes, credentials, CDR payload, compensability state, claim state, or payment state.

## Ordinary-call gate

For the first VRS composition, a protected ordinary call can reach the narrow placement verdict only when all of these remain independently true:

```text
actor authenticated
Ranger-shaped decision == ALLOW
route present
user registered
identity verified
per-call validation passed
```

A positive result emits:

```text
TRS_ORDINARY_CALL_PLACEMENT_ALLOWED
```

That verdict means only that the synthetic PR #126 ordinary-call gate was satisfied.

It does **not** mean:

```text
call connected
media usable
call truth established
minutes compensable
reimbursement eligible
claim approved
payment authorized
Fund entitlement established
FCC compliance established
```

## Three proving compositions

### Business good

```text
SignalingParser       PJSIP_PARSE_ACCEPTED
CallAdmission         PJSIP_UAS_TEXT_PROFILE_ADMITTED
ActorAuthentication   SHIRO_CONTEXT_AUTHENTICATED
Authorization         RANGER_ALLOW
TrsBusinessAuthority  TRS_ORDINARY_CALL_PLACEMENT_ALLOWED
FundAuthorityBoundary NOT_MODELED
```

### Ranger ALLOW, per-call validation fails

```text
SignalingParser       PJSIP_PARSE_ACCEPTED
CallAdmission         PJSIP_UAS_TEXT_PROFILE_ADMITTED
ActorAuthentication   SHIRO_CONTEXT_AUTHENTICATED
Authorization         RANGER_ALLOW
TrsBusinessAuthority  TRS_ORDINARY_CALL_PLACEMENT_DENIED_VALIDATION
FundAuthorityBoundary NOT_MODELED
```

This is the key new non-equivalence proof:

```text
RANGER_ALLOW
!= TRS ordinary-call placement authority
```

### Ranger DENY, business facts otherwise good

```text
SignalingParser       PJSIP_PARSE_ACCEPTED
CallAdmission         PJSIP_UAS_TEXT_PROFILE_ADMITTED
ActorAuthentication   SHIRO_CONTEXT_AUTHENTICATED
Authorization         RANGER_DENY
TrsBusinessAuthority  TRS_BUSINESS_NOT_EVALUATED_AUTHORIZATION_REQUIRED
FundAuthorityBoundary NOT_MODELED
```

The TRS business service fails closed before evaluating the synthetic Part 64 facts when protected-domain authorization is not ALLOW.

## Core invariants

```text
parser accepted
!= call admitted
!= actor authenticated
!= policy authorized
!= ordinary call placement allowed
!= call connected
!= compensable
!= reimbursable
!= claim approved
!= payment authorized
```

The business-composition validator also requires parser, admission, and actor evidence to remain byte-for-byte equivalent across the three business controls. Changing a downstream regulatory/business result therefore cannot rewrite upstream evidence.

## Claim boundary

This is a contract-derived synthetic composition. It does not establish live TRS User Registration Database behavior, live TRS Numbering Directory behavior, production user validation, provider compliance, production Ranger policy correctness, compensability, reimbursement eligibility, Fund authority, or regulatory compliance.

## Next threshold

The next safe step is a separate **compensability service** that consumes a completed-call/evidence record plus terminal regulatory prerequisites, without allowing `TRS_ORDINARY_CALL_PLACEMENT_ALLOWED` to become compensable minutes automatically. The existing Part 64/Fund PR chain should remain the semantic source for that service.
