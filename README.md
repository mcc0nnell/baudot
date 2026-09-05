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
      ├── WebRTC/application adapter
      └── research-runtime adapter
                │
                ▼
         preserved evidence
```

JAIN SIP is intentionally below the semantic boundary. It owns SIP transactions, dialogs, headers, routing, and carriage of SDP. It does **not** define T.140 behavior and it does **not** own the media plane.

The first cross-project research integration is with ACE Omni: Omni can execute controlled communications experiments while Baudot owns the portable accessibility behavior and test vocabulary.

## First executable slice

The first SIP proof is deliberately small and headless. Two loopback endpoints exercise a real JAIN SIP dialog with an SDP offer/answer and preserve deterministic, timestamp-free evidence for both layers:

```text
INVITE + SDP offer
  -> 100 Trying
  -> 180 Ringing
  -> 200 OK + SDP answer
  -> ACK
  -> BYE
  -> 200 OK
```

The fixture offers H.264 and VP8 and answers with H.264. Baudot records the stable semantic result `video RTP/AVP [H264/90000]` separately from dialog completion. RTP packets are not sent, received, or claimed by this slice.

Run it with:

```bash
mvn verify
cat target/baudot-evidence/sip-dialog.json
```

CI verifies the slice on Java 17 and Java 21. The evidence artifact is written even when the exercised path fails, preserving the partial observation for diagnosis.

## Status

Early design and testkit bootstrap. The JAIN SIP vertical slice demonstrates exercised signaling and SDP offer/answer mechanics only. No RFC 3261, RFC 4103, T.140, RTP/media, security, accessibility, or implementation conformance claim is made yet.

## Project name

The name honors Émile Baudot and the long lineage of real-time text communications. The project is independent and is not currently an Apache Software Foundation project.
