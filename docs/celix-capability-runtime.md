# Apache Celix native capability runtime

This lane proves one narrow architectural claim: Baudot can compose replaceable native telecom capabilities as Apache Celix services without allowing parser success, service presence, or service output to become an authentication, authorization, TRS business-authority, or regulatory-compliance verdict.

## Runtime pins

The CI lane builds Apache Celix 2.4.0 from the Apache source distribution and verifies its published SHA-512 before building the Baudot bundles. The native signaling parser is backed by the same pinned PJSIP/PJPROJECT 2.17 identity used by Baudot's existing native RTT lane.

```text
Apache Celix release     2.4.0
source archive           celix-2.4.0.tar.gz
SHA-512                  76FB2BA448028894841E7315F62E864A0913144A528B666106B4946A0044B45AF13629A558E627DE4EA6331788BAE482B63601AEE669E44BBC32435CC0B72FF0

PJSIP repository         pjsip/pjproject
PJSIP release            2.17
PJSIP commit             5a457451fa2712ba18e12b01738e8ff3af2b26fd
```

## Capability contract

The contract contains four service interfaces:

```text
ISignalingParser       1.0.0
ICallAdmission         2.0.0
IRealtimeTextTransport 1.0.0
IEvidenceEmitter       1.0.0
```

`ISignalingParser` owns only the native parser observation. `ICallAdmission` owns only the bounded synthetic UAS admission profile. No Shiro actor/session context, Ranger policy decision, iTRS business rule, provider eligibility decision, Fund entitlement, or FCC compliance state is represented inside either service.

The version change on `ICallAdmission` is intentional. Its v1 behavior was parser-shaped. v2 makes admission a distinct decision and prevents downstream consumers from treating `PJSIP_PARSE_ACCEPTED` as a call-admission verdict.

## Separate parser and admission bundles

The native signaling path is now physically split across two Celix bundles.

```text
PjsipSignalingParserBundle
  -> ISignalingParser
  -> links PJPROJECT

PjsipCallAdmissionBundle
  -> ICallAdmission
  -> no PJPROJECT linkage
  -> runtime dependency on ISignalingParser
```

Only the parser bundle owns the PJSIP/PJPROJECT runtime. The admission bundle asks Celix for an `ISignalingParser` service on every decision. If no parser service is available, admission remains registered but returns:

```text
PARSER_CAPABILITY_MISSING
```

That verdict is fail-closed. The admission service may not reinterpret, synthesize, or cache parser success after the parser disappears.

## PJSIP parser service

`PjsipSignalingParserBundle` calls the pinned PJPROJECT `pjsip_parse_msg()` implementation against supplied signaling bytes.

PJSIP's parser tables are initialized through the public `pjsip_endpt_create()` / `pjsip_endpt_destroy()` lifecycle. Endpoint creation constructs PJSIP's internal runtime managers, but this adapter does not register or start a UDP/TCP transport, bind a listening socket, create an account or dialog, or initialize PJSUA2 media.

A clean parsed INVITE emits:

```text
SignalingParser = PJSIP_PARSE_ACCEPTED
```

That means only that the pinned native parser produced a clean INVITE request.

## UAS admission profile

`PjsipCallAdmissionBundle` consumes parser evidence and then applies the narrow signaling shape already exercised by Baudot's existing PJSIP native-text UAS seam:

```text
audioCount = 0
videoCount = 0
textCount  = 1
```

For the Celix proving lane, the synthetic admission fixture must declare SDP, contain exactly one `m=text` media line, contain a `t140/1000` mapping, and contain no audio or video media line.

A matching fixture emits:

```text
CallAdmission = PJSIP_UAS_TEXT_PROFILE_ADMITTED
```

A clean INVITE that does not match that profile emits:

```text
CallAdmission = PJSIP_UAS_TEXT_PROFILE_NOT_ADMITTED
```

The profile matcher is intentionally not a SIP, SDP, RFC 4103, or T.140 conformance oracle. Its only role is to preserve the native UAS's text-only admission shape as a decision distinct from parser success.

The core boundary is executable:

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

```text
SignalingParser         PJSIP_PARSE_ACCEPTED
CallAdmission           PJSIP_UAS_TEXT_PROFILE_ADMITTED
RealtimeTextTransport   RTT_FIXTURE_ACCEPTED
AuthorityBoundary       NOT_MODELED
```

The parser observation preserves the exact PJPROJECT release/commit identity. The admission observation preserves its own Baudot profile implementation identity.

### Parsed but not admitted

A syntactically clean INVITE with no text-only SDP profile produces:

```text
SignalingParser         PJSIP_PARSE_ACCEPTED
CallAdmission           PJSIP_UAS_TEXT_PROFILE_NOT_ADMITTED
RealtimeTextTransport   RTT_FIXTURE_ACCEPTED
AuthorityBoundary       NOT_MODELED
```

Green CI mechanically proves:

```text
parser success != admission
```

### Fault-injected negative control

The fault-injected composition deliberately keeps unsafe synthetic call-admission and RTT providers while the PJSIP parser service is absent:

```text
SignalingParser         CAPABILITY_MISSING
CallAdmission           FAULT_INJECTED_FAIL_OPEN
RealtimeTextTransport   FAULT_INJECTED_FAIL_OPEN
AuthorityBoundary       NOT_MODELED
```

This is deliberate evidence that a replacement admission provider can bypass the parser boundary and that Baudot detects that unsafe shape. Green CI does not bless fail-open behavior.

### Missing RTT control

```text
SignalingParser         PJSIP_PARSE_ACCEPTED
CallAdmission           PJSIP_UAS_TEXT_PROFILE_ADMITTED
RealtimeTextTransport   CAPABILITY_MISSING
AuthorityBoundary       NOT_MODELED
```

Native signaling admission does not manufacture an RTT capability or any authority verdict.

## Parser-only dependency lifecycle

A standalone qualification executable creates a fresh Celix framework and installs three already-built bundles:

```text
PjsipSignalingParserBundle
PjsipCallAdmissionBundle
GoodRealtimeTextBundle
```

It captures the admission and RTT service IDs, then stops only the parser bundle.

Required sequence:

```text
active:
  SignalingParser         PJSIP_PARSE_ACCEPTED
  CallAdmission           PJSIP_UAS_TEXT_PROFILE_ADMITTED
  RealtimeTextTransport   RTT_FIXTURE_ACCEPTED
  AuthorityBoundary       NOT_MODELED

parser-stopped:
  SignalingParser         CAPABILITY_MISSING
  CallAdmission           PARSER_CAPABILITY_MISSING
  RealtimeTextTransport   RTT_FIXTURE_ACCEPTED
  AuthorityBoundary       NOT_MODELED

restored:
  SignalingParser         PJSIP_PARSE_ACCEPTED
  CallAdmission           PJSIP_UAS_TEXT_PROFILE_ADMITTED
  RealtimeTextTransport   RTT_FIXTURE_ACCEPTED
  AuthorityBoundary       NOT_MODELED
```

The parser-stopped phase must satisfy all of these conditions simultaneously:

- no `ISignalingParser` service is registered;
- the same `ICallAdmission` service remains registered;
- admission fails closed because its parser dependency is unavailable;
- the same `IRealtimeTextTransport` service remains registered and usable; and
- no authority or protocol-conformance verdict appears.

After the parser bundle restarts, the same admission and RTT service registrations must still be present and healthy admission must resume.

This is stronger than stopping a combined capability bundle. It proves a real service dependency can disappear independently and that unrelated runtime capability remains live.

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

parser capability missing
=> parser-dependent admission fails closed

parser capability missing
!= unrelated RTT capability missing

call admitted by synthetic UAS profile
!= SIP/SDP/T.140 conformance established

fault injected and observed
!= fault accepted as valid behavior
```

## Why Celix belongs here

Celix remains the native modular runtime. PJSIP remains the native SIP implementation. Camel, NiFi, Kafka, Shiro, Ranger, Fineract, and the iTRS/Fund planes retain their own responsibilities.

The key architectural move is now real rather than aspirational: parser and admission are separate runtime components with separate implementation identities, separate lifecycle, and an explicit fail-closed dependency.

## Next threshold

Introduce independent authentication and authorization services into the composition without changing parser or admission evidence. The smallest useful next slice is a bounded actor-context service plus a Ranger-style authorization decision service, with a protected-operation composition proving:

```text
parser accepted
!= admitted
!= authenticated
!= authorized
!= TRS business authority
```

Each decision must remain separately observable and independently fault-injectable.
