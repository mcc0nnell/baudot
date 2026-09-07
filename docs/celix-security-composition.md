# Celix authentication and authorization composition

This lane composes Baudot's existing signaling-runtime work with the already-defined Shiro and Ranger authority boundaries without embedding either implementation into the native Celix runtime.

It proves composition semantics only.

```text
PJSIP parser
  != call admission
  != application authentication
  != policy authorization
  != TRS business authority
  != regulatory compliance
```

## Semantic sources

The actor-context contract is derived from PR #127's bounded Apache Shiro user/session plane. The authorization contract is derived from PR #114's Apache Ranger iTRS PDP profile.

This slice does **not** claim a live Shiro or Ranger runtime inside Celix. Their implementation-specific qualification remains in their own lanes.

## Actor context service

`IActorContextProvider` carries only the bounded application actor/session projection already defined by the Shiro profile:

```text
actorId
actorType
tenantId
providerId
roles
sessionId
authenticatedAt
authenticationStrength
```

It also preserves the terminal distinction:

```text
remembered
!= authenticated
```

No password, token, telephone number, subscriber identity/address, eligibility, compensability, claim, or payment authority field belongs in this service.

Two contract-derived fixtures are used:

```text
SHIRO_CONTEXT_AUTHENTICATED
SHIRO_CONTEXT_REMEMBERED_NOT_AUTHENTICATED
```

## Authorization service

`IAuthorizationService` consumes the actor context and the same neutral Ranger operation mapping already defined in PR #114:

```text
resourceType = telephone-number
action       = QUERY
permission   = query
```

The deterministic composition fixtures return an explicit:

```text
RANGER_ALLOW
```

or:

```text
RANGER_DENY
```

For a remembered-only actor, authorization stops before policy evaluation and emits:

```text
AUTHORIZATION_NOT_EVALUATED_AUTHENTICATION_REQUIRED
```

That mirrors the trusted-caller/authenticated-subject boundary: an unauthenticated actor must not become a protected Ranger request.

## Three security compositions

### Authenticated + ALLOW

```text
SignalingParser      PJSIP_PARSE_ACCEPTED
CallAdmission        PJSIP_UAS_TEXT_PROFILE_ADMITTED
ActorAuthentication  SHIRO_CONTEXT_AUTHENTICATED
Authorization        RANGER_ALLOW
AuthorityBoundary    NOT_MODELED
```

An ALLOW still does not establish TRS business authority or regulatory compliance.

### Authenticated + DENY

```text
SignalingParser      PJSIP_PARSE_ACCEPTED
CallAdmission        PJSIP_UAS_TEXT_PROFILE_ADMITTED
ActorAuthentication  SHIRO_CONTEXT_AUTHENTICATED
Authorization        RANGER_DENY
AuthorityBoundary    NOT_MODELED
```

This mechanically proves:

```text
authenticated != authorized
```

Parser and admission evidence are identical to the ALLOW profile.

### Remembered only

```text
SignalingParser      PJSIP_PARSE_ACCEPTED
CallAdmission        PJSIP_UAS_TEXT_PROFILE_ADMITTED
ActorAuthentication  SHIRO_CONTEXT_REMEMBERED_NOT_AUTHENTICATED
Authorization        AUTHORIZATION_NOT_EVALUATED_AUTHENTICATION_REQUIRED
AuthorityBoundary    NOT_MODELED
```

This proves that signaling success and admission do not promote a remembered application identity into authenticated or authorized state.

## Core invariants

```text
parser accepted
!= admitted

admitted
!= authenticated

authenticated
!= authorized

Ranger-shaped ALLOW
!= TRS business authority

remembered-only actor
=> no protected authorization evaluation
```

The validator also rejects evidence that leaks business/regulatory authority verdicts or forbidden actor-context fields.

## Why this is a contract-composition slice

The Shiro and Ranger implementations are already qualified elsewhere in Baudot. Rebuilding those implementations inside a C++ Celix bundle would collapse implementation qualification and composition qualification into one test.

Instead, this slice makes the cross-boundary contracts explicit and replaceable. A later adapter can supply a real Shiro-derived actor context or a live Ranger decision without changing the Celix consumers or the evidence vocabulary.

## Next threshold

The next useful step is to make one of these boundaries live across process/runtime edges while preserving the same contracts. The smallest candidate is a bridge from the existing live Shiro 3.0.1 lane into `IActorContextProvider`, followed by the existing Ranger PDP adapter, with the Celix composition proving that the same actor/session projection and explicit ALLOW/DENY evidence survive the handoff unchanged.
