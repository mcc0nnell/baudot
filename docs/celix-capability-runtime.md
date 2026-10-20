# Apache Celix native capability runtime

This lane proves one narrow architectural claim: Baudot can compose replaceable native telecom capabilities as Apache Celix services without allowing service presence or service output to become an authentication, authorization, TRS business-authority, or regulatory-compliance verdict.

## Runtime pin

The CI lane builds Apache Celix 2.4.0 from the Apache source distribution and verifies its published SHA-512 before building the Baudot bundles.

```text
Apache Celix release     2.4.0
source archive           celix-2.4.0.tar.gz
SHA-512                  76FB2BA448028894841E7315F62E864A0913144A528B666106B4946A0044B45AF13629A558E627DE4EA6331788BAE482B63601AEE669E44BBC32435CC0B72FF0
```

## Capability contract

The first contract contains exactly three service interfaces:

```text
ICallAdmission
IRealtimeTextTransport
IEvidenceEmitter
```

They are deliberately small. No Shiro actor/session context, Ranger policy decision, iTRS business rule, provider eligibility decision, Fund entitlement, or FCC compliance state is represented inside these services.

## Three compositions

### Good control

The good composition registers a narrow synthetic call-admission service and a narrow synthetic realtime-text service. The probe must observe:

```text
CallAdmission           ADMISSION_FIXTURE_ACCEPTED
RealtimeTextTransport   RTT_FIXTURE_ACCEPTED
AuthorityBoundary       NOT_MODELED
```

These are fixture observations, not SIP, SDP, T.140, RFC 4103, media, or accessibility conformance claims.

### Fault-injected negative control

The fault-injected composition swaps in deliberately unsafe providers. Both services fail open for malformed synthetic inputs and must emit:

```text
CallAdmission           FAULT_INJECTED_FAIL_OPEN
RealtimeTextTransport   FAULT_INJECTED_FAIL_OPEN
AuthorityBoundary       NOT_MODELED
```

A green CI result means Baudot detected the expected negative control. It does not bless fail-open behavior.

### Missing capability control

The third composition omits the realtime-text bundle entirely. The same probe must preserve the distinction between an available admission service and an absent transport capability:

```text
CallAdmission           ADMISSION_FIXTURE_ACCEPTED
RealtimeTextTransport   CAPABILITY_MISSING
AuthorityBoundary       NOT_MODELED
```

This is the first proof that a Baudot native runtime can change composition without changing the semantic authority boundary.

## Core invariants

```text
service registered
!= service correct
!= protocol conformant
!= actor authenticated
!= operation authorized
!= TRS business authority established
!= regulatory compliance established

fault injected and observed
!= fault accepted as valid behavior

capability missing
!= authority inferred from another capability
```

## Why Celix belongs here

Celix is used only for the native modular runtime. Camel, NiFi, Kafka, Shiro, Ranger, Fineract, and other Baudot planes keep their own responsibilities. A future SIP/PJSIP or T.140 implementation may satisfy these interfaces, but this PR does not wire those live adapters yet.

## Promotion threshold

The next useful slice is to replace one synthetic provider with a real existing Baudot native adapter, preferably the PJSIP call-admission or realtime-text lane, while preserving the same service contract and evidence states. After that, add a controlled stop/start test that proves a capability can disappear and reappear at runtime without collapsing authentication, authorization, protocol validity, and TRS business authority into one decision.
