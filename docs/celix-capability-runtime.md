# Apache Celix native capability runtime

This lane proves one narrow architectural claim: Baudot can compose replaceable native telecom capabilities as Apache Celix services without allowing parser success, service presence, or service output to become an authentication, authorization, TRS business-authority, or regulatory-compliance verdict.

## Runtime pins

The CI lane builds Apache Celix 2.4.0 from the Apache source distribution and verifies its published SHA-512 before building the Baudot bundles. The native signaling provider is backed by the same pinned PJSIP/PJPROJECT 2.17 identity used by Baudot's existing native RTT lane.

```text
Apache Celix release     2.4.0
source archive           celix-2.4.0.tar.gz
SHA-512                  76FB2BA448028894841E7315F62E864A0913144A528B666106B4946A0044B45AF13629A558E627DE4EA6331788BAE482B63601AEE669E44BBC32435CC0B72FF0

PJSIP repository         pjsip/pjproject
PJSIP release            2.17
PJSIP commit             5a457451fa2712ba18e12b01738e8ff3af2b26fd
```

## Capability contract

The contract now contains four service interfaces:

```text
ISignalingParser       1.0.0
ICallAdmission         2.0.0
IRealtimeTextTransport 1.0.0
IEvidenceEmitter       1.0.0
```

`ISignalingParser` owns only the native parser observation. `ICallAdmission` owns only the bounded synthetic UAS admission profile. No Shiro actor/session context, Ranger policy decision, iTRS business rule, provider eligibility decision, Fund entitlement, or FCC compliance state is represented inside either service.

The version change on `ICallAdmission` is intentional. Its v1 behavior was still parser-shaped. v2 makes admission a distinct decision and prevents downstream consumers from treating `PJSIP_PARSE_ACCEPTED` as a call-admission verdict.

## PJSIP parser service

The PJSIP bundle exposes `ISignalingParser` and calls the pinned PJPROJECT `pjsip_parse_msg()` implementation against the supplied signaling bytes.

PJSIP's parser tables are initialized through the public `pjsip_endpt_create()` / `pjsip_endpt_destroy()` lifecycle. Endpoint creation constructs PJSIP's internal runtime managers, but this adapter does not register or start a UDP/TCP transport, bind a listening socket, create an account or dialog, or initialize PJSUA2 media.

A clean parsed INVITE emits:

```text
SignalingParser = PJSIP_PARSE_ACCEPTED
```

That means only that the pinned native parser produced a clean INVITE request.

## PJSIP UAS admission profile

The same bundle exposes a separate `ICallAdmission` service. It first requires native parser success, then applies the narrow signaling shape already exercised by Baudot's existing PJSIP native-text UAS seam:

```text
audioCount = 0
videoCount = 0
textCount  = 1
```

For the Celix proving lane, the synthetic admission fixture must therefore declare SDP, contain exactly one `m=text` media line, contain a `t140/1000` mapping, and contain no audio or video media line.

A matching fixture emits:

```text
CallAdmission = PJSIP_UAS_TEXT_PROFILE_ADMITTED
```

A clean INVITE that does not match that profile emits:

```text
CallAdmission = PJSIP_UAS_TEXT_PROFILE_NOT_ADMITTED
```

The profile matcher is intentionally not a SIP, SDP, RFC 4103, or T.140 conformance oracle. Its only role is to preserve the native UAS's text-only admission shape as a decision distinct from parser success.

The core boundary is now executable:

```text
PJSIP_PARSE_ACCEPTED
!= PJSIP_UAS_TEXT_PROFILE_ADMITTED
!= SIP/SDP/T.140 conformance
!= actor authenticated
!= operation authorized
!= TRS business authority established
!= regulatory compliance established
```

## Four compositions

### Good control

The good composition uses the pinned PJSIP bundle and a synthetic RTT fixture:

```text
SignalingParser         PJSIP_PARSE_ACCEPTED
CallAdmission           PJSIP_UAS_TEXT_PROFILE_ADMITTED
RealtimeTextTransport   RTT_FIXTURE_ACCEPTED
AuthorityBoundary       NOT_MODELED
```

Both PJSIP observations preserve the exact release/commit identity.

### Parsed but not admitted

This is the new threshold proof. A syntactically clean INVITE with no text-only SDP profile must produce:

```text
SignalingParser         PJSIP_PARSE_ACCEPTED
CallAdmission           PJSIP_UAS_TEXT_PROFILE_NOT_ADMITTED
RealtimeTextTransport   RTT_FIXTURE_ACCEPTED
AuthorityBoundary       NOT_MODELED
```

Green CI therefore mechanically proves:

```text
parser success != admission
```

No policy or authority layer is permitted to fill that gap.

### Fault-injected negative control

The fault-injected composition deliberately keeps the unsafe synthetic call-admission and RTT providers. The PJSIP parser service is absent:

```text
SignalingParser         CAPABILITY_MISSING
CallAdmission           FAULT_INJECTED_FAIL_OPEN
RealtimeTextTransport   FAULT_INJECTED_FAIL_OPEN
AuthorityBoundary       NOT_MODELED
```

This is deliberate evidence that a replacement admission provider can bypass the parser boundary and that Baudot detects that unsafe shape. Green CI does not bless fail-open behavior.

### Missing RTT control

The missing-RTT composition keeps both native PJSIP services but omits the RTT capability:

```text
SignalingParser         PJSIP_PARSE_ACCEPTED
CallAdmission           PJSIP_UAS_TEXT_PROFILE_ADMITTED
RealtimeTextTransport   CAPABILITY_MISSING
AuthorityBoundary       NOT_MODELED
```

Native signaling admission does not manufacture an RTT capability or any authority verdict.

## Controlled PJSIP lifecycle

A standalone qualification executable creates a fresh Celix framework, installs the already-built PJSIP capability bundle, and performs synchronous bundle lifecycle operations from the process thread.

Because the parser and admission contracts are exported by the same native bundle in this slice, both must disappear and reappear together:

```text
active:
  SignalingParser   PJSIP_PARSE_ACCEPTED
  CallAdmission     PJSIP_UAS_TEXT_PROFILE_ADMITTED
  AuthorityBoundary NOT_MODELED

stopped:
  SignalingParser   CAPABILITY_MISSING
  CallAdmission     CAPABILITY_MISSING
  AuthorityBoundary NOT_MODELED

restored:
  SignalingParser   PJSIP_PARSE_ACCEPTED
  CallAdmission     PJSIP_UAS_TEXT_PROFILE_ADMITTED
  AuthorityBoundary NOT_MODELED
```

The stopped phase must have neither service registered. The restored phase must preserve the exact pinned PJPROJECT identity again. Lifecycle evidence may not promote restored service presence into restored authorization, protocol conformance, TRS business authority, or regulatory compliance.

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
!= call admitted

call admitted by synthetic UAS profile
!= SIP/SDP/T.140 conformance established

fault injected and observed
!= fault accepted as valid behavior

capability missing
!= authority inferred from another capability

bundle restarted
!= prior authority restored or recreated
```

## Why Celix belongs here

Celix remains the native modular runtime. PJSIP remains the native SIP implementation. Camel, NiFi, Kafka, Shiro, Ranger, Fineract, and the iTRS/Fund planes retain their own responsibilities.

This slice does not rewrite those systems. It establishes a versioned native contract where parser evidence and admission evidence are independently observable and can later be supplied by separate bundles without changing the consuming composition.

## Next threshold

Split parser and admission into separate Celix bundles and make `ICallAdmission` dynamically depend on `ISignalingParser`, so stopping only the parser removes or fail-closes admission without stopping unrelated capabilities. After that lifecycle dependency is proven, compose Shiro actor/session context and Ranger authorization as separate services without allowing either to alter parser/admission evidence.
