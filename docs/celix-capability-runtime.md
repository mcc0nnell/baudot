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

`ICallAdmission` is satisfied in the positive compositions by a Celix bundle linked to the pinned PJPROJECT `pjsip` target. The adapter calls PJSIP's native `pjsip_parse_msg()` parser against a complete synthetic INVITE fixture and accepts only a clean parsed INVITE request.

PJSIP's parser tables are initialized through the public `pjsip_endpt_create()` / `pjsip_endpt_destroy()` lifecycle. Endpoint creation constructs PJSIP's internal runtime managers, including its transport manager, but this adapter does not register or start a UDP/TCP transport, bind a listening socket, create an account or dialog, or initialize media/PJSUA2.

That observation is intentionally narrow:

```text
PJSIP_PARSE_ACCEPTED
!= SIP protocol conformance established
!= signaling policy satisfied
!= actor authenticated
!= operation authorized
!= TRS business authority established
```

The endpoint exists only to establish the supported PJSIP parser/runtime lifecycle. The adapter proves that an existing native Baudot dependency can satisfy the Celix capability contract without moving any authority boundary into Celix.

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

## Controlled PJSIP lifecycle

A separate qualification executable creates a fresh Celix framework using `celix::createFramework()`, installs the already-built PJSIP admission bundle, and performs synchronous bundle lifecycle operations from the process thread.

The required sequence is:

```text
active:
  CallAdmission       PJSIP_PARSE_ACCEPTED
  AuthorityBoundary   NOT_MODELED

stopped:
  CallAdmission       CAPABILITY_MISSING
  AuthorityBoundary   NOT_MODELED

restored:
  CallAdmission       PJSIP_PARSE_ACCEPTED
  AuthorityBoundary   NOT_MODELED
```

The stopped phase must have no registered `ICallAdmission` service. The restored phase must again preserve the exact pinned PJPROJECT identity. The lifecycle validator rejects authority or protocol-conformance verdicts in any phase.

This proves a stronger runtime property than the static missing-RTT composition: the same native capability can disappear and reappear in one running Celix framework without another subsystem filling the gap or inferring authority from absence/presence.

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

bundle restarted
!= prior authority restored or recreated
```

## Why Celix belongs here

Celix remains only the native modular runtime. PJSIP remains the native SIP implementation. Camel, NiFi, Kafka, Shiro, Ranger, Fineract, and the iTRS/Fund planes retain their own responsibilities. The service contract does not change when a synthetic provider is replaced, stopped, or restored.

## Next threshold

Move one real admission decision from the existing native PJSIP UAS seam behind `ICallAdmission` while retaining `PJSIP_PARSE_ACCEPTED` as parser evidence only. The next provider should distinguish native parser success from the UAS's own signaling-admission decision, and both must remain separate from Shiro authentication, Ranger authorization, iTRS business authority, and regulatory compliance.
