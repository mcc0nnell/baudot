# Apache Celix native capability runtime

This lane proves one narrow architectural claim: Baudot can compose replaceable native telecom capabilities as Apache Celix services without allowing service presence or service output to become an authentication, authorization, TRS business-authority, or regulatory-compliance verdict.

## Runtime pins

The CI lane builds Apache Celix 2.4.0 from the Apache source distribution and verifies its published SHA-512 before building the Baudot bundles. The call-admission provider is now backed by the same pinned PJSIP/PJPROJECT 2.17 identity used by Baudot's existing native RTT lane.

```text
Apache Celix release     2.4.0
source archive           celix-2.4.0.tar.gz
SHA-512                  76FB2BA448028894841E7315F62E864A0913144A528B666106B4946A0044B45AF13629A558E627DE4EA6331788BAE482B63601AEE669E44BBC32435CC0B72FF0

PJSIP repository         pjsip/pjproject
PJSIP release            2.17
PJSIP commit             5a457451fa2712ba18e12b01738e8ff3af2b26fd
```

## Capability contract

The contract still contains exactly three service interfaces:

```text
ICallAdmission
IRealtimeTextTransport
IEvidenceEmitter
```

No Shiro actor/session context, Ranger policy decision, iTRS business rule, provider eligibility decision, Fund entitlement, or FCC compliance state is represented inside these services.

## PJSIP admission adapter

`ICallAdmission` is now satisfied in the positive compositions by a Celix bundle linked to the pinned PJPROJECT `pjsip` target. The adapter calls PJSIP's native `pjsip_parse_msg()` parser against a complete synthetic INVITE fixture and accepts only a clean parsed INVITE request.

That observation is intentionally narrow:

```text
PJSIP_PARSE_ACCEPTED
!= SIP protocol conformance established
!= signaling policy satisfied
!= actor authenticated
!= operation authorized
!= TRS business authority established
```

The adapter does not start a transport, account, media stack, dialog, or PJSUA2 endpoint. It proves only that an existing native Baudot dependency can satisfy the Celix capability contract without moving any authority boundary into Celix.

## Three compositions

### Good control

The good composition registers the real PJSIP-backed call-admission service and the existing synthetic realtime-text service. The probe must observe:

```text
CallAdmission           PJSIP_PARSE_ACCEPTED
RealtimeTextTransport   RTT_FIXTURE_ACCEPTED
AuthorityBoundary       NOT_MODELED
```

The call-admission evidence preserves the exact PJPROJECT release commit in its detail field. The RTT observation remains a fixture result rather than T.140, RFC 4103, media, or accessibility conformance evidence.

### Fault-injected negative control

The fault-injected composition deliberately keeps the unsafe synthetic providers. Both fail open for malformed synthetic inputs and must emit:

```text
CallAdmission           FAULT_INJECTED_FAIL_OPEN
RealtimeTextTransport   FAULT_INJECTED_FAIL_OPEN
AuthorityBoundary       NOT_MODELED
```

A green CI result means Baudot detected the expected negative control. It does not bless fail-open behavior.

### Missing capability control

The third composition uses the same PJSIP-backed admission provider but omits the realtime-text bundle entirely:

```text
CallAdmission           PJSIP_PARSE_ACCEPTED
RealtimeTextTransport   CAPABILITY_MISSING
AuthorityBoundary       NOT_MODELED
```

This preserves the distinction between a native signaling capability and an absent RTT capability without inferring authority from the remaining service.

## Core invariants

```text
service registered
!= service correct
!= protocol conformant
!= actor authenticated
!= operation authorized
!= TRS business authority established
!= regulatory compliance established

native parser accepted fixture
!= protocol conformance established

fault injected and observed
!= fault accepted as valid behavior

capability missing
!= authority inferred from another capability
```

## Why Celix belongs here

Celix remains only the native modular runtime. PJSIP remains the native SIP implementation. Camel, NiFi, Kafka, Shiro, Ranger, Fineract, and the iTRS/Fund planes retain their own responsibilities. The service contract did not change when the synthetic admission provider was replaced with the PJSIP-backed implementation.

## Promotion threshold

The next useful slice is controlled runtime lifecycle evidence: stop or remove the PJSIP admission bundle, observe `CAPABILITY_MISSING`, restart or reinstall it, and observe the native capability return. That lifecycle must not manufacture authentication, authorization, protocol-conformance, TRS business-authority, or regulatory-compliance verdicts.
