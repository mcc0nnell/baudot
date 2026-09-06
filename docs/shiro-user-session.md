# Apache Shiro for Baudot users and sessions

Apache Shiro is the bounded application identity/session layer in the Apache-native TRS architecture.

```text
credential / realm authentication
        -> Shiro subject + session
        -> minimal trusted actor context
        -> Baudot service
        -> Ranger policy decision
        -> protocol/business validation
        -> operation
```

The boundary is intentionally narrow:

```text
Shiro authenticates the application actor.
Shiro does not become the TRS User Registration Database.
Shiro does not establish subscriber eligibility.
Shiro does not perform TRS identity verification.
Shiro does not replace Ranger policy.
```

## Pin

```text
Apache Shiro 3.0.1
release tag:    shiro-root-3.0.1
release commit: 3dcc3fc2a8ddae21ea76a8c55637aa165f368357
```

3.0.1 is the current stable release for this profile. The release includes security hardening around RememberMe deserialization, request-path handling, filters, and authentication behavior.

## Subject context

Only a small actor/session projection may leave the Shiro boundary:

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

The first actor classes are:

```text
provider-user
operator
service-account
```

These are Baudot application identities. They are not subscriber eligibility records.

The Shiro context must not carry:

```text
password / passwordHash
access / refresh token
telephone number
subscriber name/address
eligibilityApproved
identityVerified
compensable
claimApproved
paymentAuthorized
```

## Remembered is not authenticated

Shiro distinguishes a remembered identity from a currently authenticated subject. Baudot makes that distinction terminal for protected TRS actions.

```text
isRemembered
!=
strong authenticated subject
```

A remembered actor may be useful for UI continuity. It does not provide the authentication strength required to submit a protected authorization request to Ranger.

## Ranger handoff

Only a trusted Baudot service may translate Shiro subject context into a Ranger authorization request.

```text
Shiro subject
  -> actorId / tenant / provider / roles / session correlation
  -> trusted service
  -> Ranger PDP
```

A direct client cannot assert another actor to Ranger.

Even after successful Shiro authentication:

```text
authenticated
!= Ranger ALLOW
!= protocol valid
!= subscriber eligible
!= compensable
```

## Synthetic matrix

The deterministic profile covers:

- valid provider-user authentication;
- invalid credentials;
- expired/logged-out session;
- authenticated subject plus Ranger DENY;
- remembered-only identity;
- untrusted subject assertion;
- logout/session invalidation; and
- Shiro + Ranger success followed by protocol-invalid rejection.

The fixtures contain no real user credentials or subscriber information.

## Relationship to Part 64 / URD modeling

The public Part 64 registration/numbering model is a different authority domain.

Shiro can authenticate an operator or provider user who is allowed to use an application. It cannot turn that application login into evidence that a TRS consumer:

- is eligible;
- completed required identity verification;
- has a valid registration record;
- owns or controls a telephone number; or
- is compensable for a call.

Those facts remain governed by the relevant TRS program, protocol, and evidence boundaries.

## Evidence basis

- Apache Shiro current release: <https://shiro.apache.org/download.html>
- Apache Shiro 3.0.1 release: <https://shiro.apache.org/blog/2026/08/apache-shiro-301-released.html>
- Apache Shiro documentation: <https://shiro.apache.org/documentation>
- Apache Shiro Git tag: <https://github.com/apache/shiro/releases/tag/shiro-root-3.0.1>

## Next threshold

Build a tiny Java 17 Shiro 3.0.1 fixture application with a synthetic realm and exercise the eight cases through real `Subject`, `Session`, remember-me, and logout behavior. Feed only the resulting minimal subject context to the existing Ranger fixture from #114 and preserve evidence that:

```text
remembered-only -> no protected Ranger request
expired session  -> no protected Ranger request
Ranger DENY      -> no operation
protocol invalid -> no operation
```

A later production identity provider can replace the synthetic realm without changing the Baudot authority contract.

## Claim boundary

This profile does not establish production authentication security, MFA conformance, production directory/IdP integration, TRS User Registration Database behavior, subscriber identity verification, iTRS authorization, provider certification, or accessibility readiness.
