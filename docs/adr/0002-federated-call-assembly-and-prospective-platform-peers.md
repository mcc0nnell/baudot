# ADR-0002: Federated call assembly and prospective platform peers

- Status: Accepted
- Date: 2026-09-05
- Decision owners: Baudot maintainers

## Context

Baudot began by separating accessible communications behavior from any one signaling stack, provider, or product. ADR-0001 established that JAIN SIP, Elixip, OpenMeetings, ACE Direct, Wiretap, and real provider endpoints have different evidence roles and that none of them defines correctness by itself.

The same separation is required at a larger boundary.

A Deaf caller should not need to reason about a communications product as the destination of the call. The desired end state is that the caller expresses an intent to communicate with a person or service, while an accessibility-aware federation layer determines which signaling, media, relay, identity, and presentation capabilities are required to make that session usable.

One motivating future case is:

```text
Deaf caller
    -> VRS provider / interpreter service
    -> Baudot federation boundary
    -> mainstream video calling endpoint
```

A prospective example is a VRS call whose hearing endpoint participates through FaceTime. That example is useful as an architecture test because it crosses several independently controlled systems, but FaceTime must not become a hidden dependency or an excuse to rely on undocumented Apple internals.

Current Apple platform behavior establishes several useful facts without establishing direct FaceTime federation:

- FaceTime links permit Android and Windows participants to join from a supported web browser.
- Apple's FaceTime requirements identify WebRTC-capable browsers and H.264 video support for web participants.
- iOS and iPadOS 18.2 and later permit a third-party CallKit or LiveCommunicationKit application to become the default calling application.
- Apple maintains a formal interoperability-request process for capabilities used by Apple services or accessories that are not otherwise available to third-party applications.

Those observations make a future supported bridge conceivable. They do not constitute a public SIP-to-FaceTime API, a FaceTime gateway contract, or evidence that Baudot can directly originate or terminate native FaceTime sessions today.

## Decision

Baudot will define a **federated call assembly** boundary in which accessibility services and communications endpoints are independent, replaceable participants selected from explicit capabilities and user intent.

### 1. A call is assembled from roles, not products

The logical model is:

```text
call intent
    |
    v
identity / destination resolution
    |
    v
capability discovery
    |
    +--> accessibility service participants
    |      - VRS / interpreter
    |      - RTT service
    |      - captions / transcription
    |      - speech or text transformation
    |
    +--> communications peers
    |      - SIP / PSTN
    |      - WebRTC
    |      - conferencing platforms
    |      - future platform-specific peers
    |
    v
session assembly
    |
    v
observable accessibility readiness
```

Products are adapters around those roles. A VRS provider is not the definition of a relay session. FaceTime, Teams, Zoom, Webex, a SIP softphone, or a PSTN endpoint is not the definition of a destination.

### 2. Accessibility services are explicit session participants

A sign-language interpreter, captioning service, relay provider, or transformation service that receives media is an explicit participant in the assembled session.

Baudot will not model an interpreter as a transparent man-in-the-middle. The evidence model must be able to state which participant received which media and which security boundary applied to each leg.

This matters for both privacy and testability. A session may be securely transported on every leg while still requiring an interpreter to receive decoded audio or video in order to provide the service.

### 3. Platform integrations are adapters, not protocol dependencies

A platform-specific peer adapter may exist only when there is a documented, supportable interoperability surface.

For FaceTime specifically:

- FaceTime is a **prospective federation peer**.
- Baudot does not depend on FaceTime internals.
- Baudot will not reverse engineer private signaling solely to claim FaceTime support.
- Existing FaceTime web participation may be used as an observable external endpoint where permitted, but it does not define a general FaceTime gateway API.
- Deeper integration requires an Apple-supported API, documented interoperability mechanism, or explicit platform partnership.

The same rule applies to other closed platforms.

### 4. Capability negotiation precedes route selection

Federation decisions must be driven by explicit capabilities rather than provider names.

At minimum, a participant description may need to express:

```text
signaling:
  sip
  webrtc
  pstn
  platform-specific

media:
  audio
  video
  text/t140
  text/rfc4103
  captions

accessibility:
  sign-language-video
  realtime-text
  caption-presentation
  relay-participation

session:
  can-originate
  can-terminate
  can-add-participant
  can-transfer
  can-handoff

security:
  transport-security
  media-encryption
  endpoint-encryption
  media-termination-required
```

The final schema will be implemented separately. This ADR establishes the separation, not the serialization format.

### 5. Security claims are leg-specific and evidence-bound

Baudot will not use an unqualified `e2ee=true` claim for a federated call that contains media-transforming or interpreting participants.

Instead, the evidence model must be capable of expressing facts such as:

```text
caller <-> Baudot peer adapter          encrypted
peer adapter <-> VRS provider           encrypted
VRS provider <-> interpreter endpoint   encrypted
interpreter received decoded media      true
hearing endpoint received decoded media true
```

If a future architecture preserves end-to-end encryption across some participants without media termination, that fact may be asserted only for the exact path proven by evidence.

### 6. User intent remains above provider selection

The user-facing abstraction should converge toward:

```text
Call this person
with the accessibility services I require
```

rather than:

```text
Open provider X
choose provider-specific destination mode
place a provider-specific call
```

Provider choice may remain user-controlled, policy-controlled, or contract-controlled. The architectural rule is that provider selection is an input to session assembly, not the definition of the call itself.

### 7. Federation must degrade safely

If the preferred route cannot satisfy required accessibility capabilities, Baudot must not silently downgrade the session into a merely connected but unusable call.

A route may fail, fall back, or request a different peer only when the resulting capability set is explicit.

For example:

```text
video connected=true
interpreter connected=true
audio connected=true
required realtime text=false
terminal accessibility verdict=not ready
```

remains a failed accessibility outcome even if every signaling leg returned success.

## FaceTime as the architecture test case

The motivating target can be expressed without claiming current support:

```text
Sorenson / other VRS provider
          |
          | provider adapter
          v
+-----------------------------+
| Baudot federated call layer |
+-----------------------------+
          |
          | supported platform adapter
          v
     FaceTime participant
```

The provider name is illustrative. The same architecture must permit another VRS provider without changing the reducer or the destination semantics.

Likewise, replacing the destination with a SIP endpoint, WebRTC room, Teams call, Zoom session, Webex session, or another future peer should not change the accessibility-service model.

## Near-term implementation path

Baudot will build toward the federation boundary in stages that are independently testable.

### Stage 0 - preserve the current proving ground

Continue proving SIP, RFC 4103, T.140, REFER, re-INVITE, handoff, and evidence semantics. Federation must not weaken the lower-level test discipline.

### Stage 1 - provider-neutral VRS call model

Define a provider-neutral session participant and evidence vocabulary for a relay/interpreter leg without requiring any production provider integration.

Target proof:

```text
caller peer
+ interpreter participant
+ hearing peer
= one assembled session with explicit readiness facts
```

### Stage 2 - SIP/WebRTC federation

Demonstrate the same call model across a SIP participant and a browser WebRTC participant using open, controllable endpoints.

This is the first useful approximation of the future closed-platform case because it proves that the accessibility service is independent of the destination transport.

### Stage 3 - native calling surface

Implement a Baudot-compatible iOS client experiment using documented CallKit or LiveCommunicationKit behavior, including default-calling-app capability where appropriate.

This proves that federated routing can appear to the user as ordinary calling rather than a provider-specific workflow.

### Stage 4 - sanctioned closed-platform peer

Add a FaceTime or other closed-platform adapter only when a documented and supportable interoperability surface exists.

Until then, FaceTime remains a roadmap peer and external interoperability target, not a conformance claim.

## Evidence requirements for a federated call

A future federation scenario should preserve, where applicable:

```text
call intent identity
destination identity
selected provider identity
selected peer adapter
advertised participant capabilities
required accessibility capabilities
negotiated media capabilities
participant join order
media path / termination points
security properties by leg
first usable audio observation
first usable video observation
first usable T.140 observation
interpreter readiness observation
handoff / transfer chronology
fallback decisions
terminal accessibility verdict
```

The central invariant remains unchanged:

> connected is not the same fact as usable.

## Consequences

### Positive

- VRS becomes an accessibility service that can participate in many communications surfaces rather than a closed destination model.
- Mainstream calling platforms can be added as replaceable peers without redefining accessibility semantics.
- Baudot can test the same relay behavior against open WebRTC endpoints before any closed-platform partnership exists.
- The architecture gives Apple, Microsoft, Zoom, Cisco, VRS providers, and other implementers a narrow integration boundary rather than requiring them to adopt the whole Baudot stack.
- Security claims become more precise because interpreter/media termination is modeled explicitly.
- User experience can converge toward ordinary calling with accessibility services assembled behind the call intent.

### Costs

- Capability negotiation, identity resolution, authorization, and participant consent become first-class architecture concerns.
- A federated call may require multiple independently secured media legs rather than one end-to-end cryptographic domain.
- Closed platforms may never expose the APIs needed for direct federation.
- Production VRS integrations may require provider agreements, regulatory analysis, numbering/routing work, or certification beyond what the open-source test harness can establish.

## Rejected alternatives

### Make one VRS provider the federation hub

Rejected. That would reproduce the provider-specific architecture Baudot is intended to decouple.

### Treat FaceTime as a current implementation target

Rejected. Current public Apple behavior supports web participation and third-party calling apps but does not establish a general-purpose FaceTime gateway contract.

### Reverse engineer FaceTime private signaling

Rejected as an architectural dependency. It would be brittle, unsupported, difficult to test as a stable interoperability contract, and unnecessary for proving the federation model.

### Hide the interpreter inside a media gateway

Rejected. It obscures consent, privacy, media termination, evidence, and the actual accessibility service being delivered.

### Claim end-to-end encryption across a terminating interpreter

Rejected. Encryption claims must describe the actual media path and endpoints that possess decoded media.

## Follow-up

1. Add a provider-neutral `federation` vocabulary for call intent, participants, required capabilities, and negotiated capabilities.
2. Define the first three-party accessibility scenario: caller + interpreter + destination.
3. Implement the scenario with open SIP/WebRTC peers before integrating any production VRS provider.
4. Extend evidence manifests with participant roles and media-termination points.
5. Add an iOS CallKit/LiveCommunicationKit experiment as a separate adapter proof, not as core semantics.
6. Draft a platform-interoperability request package only after Stage 2 demonstrates the exact missing capability that a closed platform would need to expose.
7. Keep FaceTime named in roadmap material as a prospective peer, never as currently supported interop.

## Source observations pinned for this decision

Observed 2026-09-05:

- Apple Support, "Join a FaceTime call from an Android or Windows device": FaceTime links permit browser participation from Android and Windows.
  - https://support.apple.com/en-us/109364
- Apple FaceTime requirements: supported web participation requires a WebRTC-capable browser and, for video, H.264 support.
  - https://support.apple.com/guide/facetime/fctm35515/mac
- Apple Developer, "Preparing your app to be the default calling app": iOS and iPadOS 18.2+ permit third-party calling apps to handle calls through the default-calling-app mechanism.
  - https://developer.apple.com/documentation/CallKit/Preparing-your-app-to-be-the-default-calling-app
- Apple Developer, "Interoperability requests": Apple provides a process for requesting access to otherwise unavailable OS capabilities used by Apple services or accessories and may develop a documented solution for a future software release.
  - https://developer.apple.com/support/interoperability-requests

These observations establish architectural feasibility signals and platform boundaries. They do not establish direct FaceTime federation.