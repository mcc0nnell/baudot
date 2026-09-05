# Baudot

**Accessible real-time communications, specified as behavior before implementation.**

Baudot is an independent open-source project for defining and testing interoperable accessible real-time communications behavior.

The project starts at the semantic boundary: **T.140 real-time text behavior and deterministic test vectors first**. SIP/RFC 4103, WebRTC, gateways, and application integrations are transport work layered on top of that core rather than substitutes for it.

## Working principles

1. **Behavior before stack choice.** A normative or interoperable behavior should be expressible as a portable test vector before it is tied to one SIP, WebRTC, or application implementation.
2. **Connected is not usable.** Signaling success, transport readiness, media receipt, presentation, and RTT readiness are separate observable facts.
3. **Evidence before conformance claims.** A fixture, implementation, or adapter does not become conformant because documentation says so; the evidence path must support the claim.
4. **Transport does not redefine text semantics.** T.140 behavior belongs to the core. RFC 4103/SIP and other transports carry it.
5. **Interop failures become tests.** Historical production workarounds can motivate scenarios, but they are not copied forward or treated as proof that a modern implementation has the same defect.
6. **Freeze the protocol brain; modernize everything around it.** Treat JAIN SIP's transaction, dialog, timer, retransmission, parsing, and state-machine behavior as stable protocol infrastructure unless evidence demonstrates a protocol-level defect. Put modernization at the boundaries: current Java, dependency hygiene, TLS, observability, deployment, testing, accessibility semantics, WebRTC integration, security controls, and software-assurance evidence. Do not replace proven SIP behavior with application-layer cleverness.

## Initial shape

```text
T.140 semantics
      │
      ▼
normative vectors
      │
      ▼
baudot-testkit
      │
      ├── SIP / RFC 4103 adapter  ── JAIN SIP signaling kernel
      ├── RTP transport probe
      ├── WebRTC/application adapter
      └── research-runtime adapter
                │
                ▼
         preserved evidence
```

JAIN SIP is intentionally below the semantic boundary. It owns SIP transactions, dialogs, headers, routing, and carriage of SDP. It does **not** define T.140 behavior and it does **not** own the media plane.

The first cross-project research integration is with ACE Omni: Omni can execute controlled communications experiments while Baudot owns the portable accessibility behavior and test vocabulary.

## First executable slice

The first SIP proof is deliberately small and headless. Two loopback endpoints exercise a real JAIN SIP dialog, exchange an SDP video offer/answer, and preserve deterministic evidence for signaling, negotiated media description, and RTP transport observation.

The positive fixture proves this exercised path:

```text
INVITE -> 100 Trying -> 180 Ringing -> 200 OK -> ACK
SDP offer:  H.264 + VP8
SDP answer: H.264
RTP socket ready
first RTP v2 packet observed
payload type matches negotiated H.264 mapping
BYE -> 200 OK
```

The payload bytes are synthetic and are not claimed to be valid H.264. Decoder input and rendering remain explicitly unproven.

A second fixture deliberately sends no RTP after successful SIP and SDP negotiation. That diagnostic test passes when the expected no-packet condition is observed, while the resulting evidence still records `mediaTransportProven: false`. This is the first canonical Baudot black-screen failure class.

Run the suite with:

```bash
mvn verify
cat target/baudot-evidence/sip-dialog-rtp.json
cat target/baudot-evidence/sip-dialog-no-rtp.json
```

CI verifies the slice on Java 17 and Java 21 and preserves the Java 21 evidence directory.

## Status

Early design and testkit bootstrap. The JAIN SIP/RTP vertical slice demonstrates only the explicitly observed signaling, SDP, and RTP transport mechanics. No RFC 4103, T.140, SIP, RTP profile, codec, media rendering, security, accessibility, or implementation conformance claim is made yet.

## Project name

The name honors Émile Baudot and the long lineage of real-time text communications. The project is independent and is not currently an Apache Software Foundation project.
