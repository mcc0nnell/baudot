# Apache Celix native capability runtime

This lane proves that Baudot can compose replaceable native telecom capabilities as Apache Celix services without promoting parser success or service presence into authority.

## Runtime pins

```text
Apache Celix 2.4.0
PJSIP/PJPROJECT 2.17
commit 5a457451fa2712ba18e12b01738e8ff3af2b26fd
```

## Capability contract

```text
ISignalingParser       1.0.0
ICallAdmission         2.0.0
IRealtimeTextTransport 1.0.0
IEvidenceEmitter       1.0.0
```

`ISignalingParser` owns only the pinned native parser observation. `ICallAdmission` now owns a separate bounded UAS admission decision. The v2 version is intentional: v1 was still parser-shaped.

## Parser versus admission

A clean parsed INVITE emits:

```text
SignalingParser = PJSIP_PARSE_ACCEPTED
```

The synthetic native-UAS text profile mirrors Baudot's existing PJSIP UAS answer shape:

```text
audioCount = 0
videoCount = 0
textCount  = 1
```

For this proving lane the fixture must declare SDP, contain exactly one `m=text` line, include a `t140/1000` mapping, and contain no audio/video media line. A match emits `PJSIP_UAS_TEXT_PROFILE_ADMITTED`; otherwise a clean INVITE emits `PJSIP_UAS_TEXT_PROFILE_NOT_ADMITTED`.

This matcher is not a SIP, SDP, RFC 4103, or T.140 conformance oracle.

```text
PJSIP_PARSE_ACCEPTED
!= PJSIP_UAS_TEXT_PROFILE_ADMITTED
!= protocol conformance
!= authentication
!= authorization
!= TRS business authority
!= regulatory compliance
```

## Four compositions

Good:

```text
SignalingParser         PJSIP_PARSE_ACCEPTED
CallAdmission           PJSIP_UAS_TEXT_PROFILE_ADMITTED
RealtimeTextTransport   RTT_FIXTURE_ACCEPTED
AuthorityBoundary       NOT_MODELED
```

Parsed but not admitted:

```text
SignalingParser         PJSIP_PARSE_ACCEPTED
CallAdmission           PJSIP_UAS_TEXT_PROFILE_NOT_ADMITTED
RealtimeTextTransport   RTT_FIXTURE_ACCEPTED
AuthorityBoundary       NOT_MODELED
```

Fault-injected negative control:

```text
SignalingParser         CAPABILITY_MISSING
CallAdmission           FAULT_INJECTED_FAIL_OPEN
RealtimeTextTransport   FAULT_INJECTED_FAIL_OPEN
AuthorityBoundary       NOT_MODELED
```

Missing RTT:

```text
SignalingParser         PJSIP_PARSE_ACCEPTED
CallAdmission           PJSIP_UAS_TEXT_PROFILE_ADMITTED
RealtimeTextTransport   CAPABILITY_MISSING
AuthorityBoundary       NOT_MODELED
```

## Controlled lifecycle

The same native bundle currently exports parser and admission. Both must disappear and return together:

```text
active:   parser accepted / admission admitted
stopped:  parser missing  / admission missing
restored: parser accepted / admission admitted
```

Restored service presence does not restore or manufacture authorization, protocol conformance, TRS authority, or regulatory compliance.

## Next threshold

Split parser and admission into separate Celix bundles and make admission dynamically depend on parser availability. Prove that stopping only the parser removes or fail-closes admission while unrelated capabilities remain running. Then compose Shiro actor/session context and Ranger authorization as separate services without allowing either to alter parser/admission evidence.
