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
canonical vectors
      │
      ▼
baudot-testkit
      │
      ├── SIP / RFC 4103 runtime adapter
      ├── WebRTC/application adapter
      └── research-runtime adapter
                │
                ▼
         preserved evidence
```

The first cross-project research integration is with ACE Omni: Omni can execute controlled communications experiments while Baudot owns the portable accessibility behavior and test vocabulary.

## Current vertical slice

Baudot now has a routed transport harness using JAIN SIP for signaling and Sandia Wiretap as an external controlled-network substrate. Caller and callee run in separate Linux network namespaces, and signaling, generic media reachability, and RTT are preserved as independent observations.

The first routed invariant is:

```text
scenarioResult=PASS
callState=CALL_ESTABLISHED
mediaState=MEDIA_FAILED
```

That proves a complete SIP `INVITE -> 200 -> ACK` exchange can remain healthy while an independently routed media path is unavailable. The SIP leg uses RFC 3581 `rport` so responses return over Wiretap's transparent UDP flow.

The next slice binds Baudot's canonical RFC 4103 primary `text/t140` vectors to the same routed runtime without introducing a second packet serializer. The Python reference implementation materializes exact canonical RTP bytes; the Java runtime replays those bytes and independently validates the packet observed at the receiver.

The routed RFC 4103 primary scenario proves:

```text
scenarioResult=PASS
callState=CALL_ESTABLISHED
mediaState=MEDIA_FAILED
rttState=RTT_RECEIVED
sdpNegotiated=false
```

`RTT_RECEIVED` is intentionally **not** the same as `RTT_READY`: this scenario proves narrow primary `text/t140` RTP transport, but does not perform SDP `text/t140` negotiation. RFC 2198 redundancy, recovery, RTCP, buffering/timing behavior, and complete RFC 4103 sender/receiver behavior remain separate evidence layers.

See [`docs/sip-wiretap-harness.md`](docs/sip-wiretap-harness.md) for the routed topology, caller/callee roles, state model, canonical RFC 4103 runtime binding, and evidence bundle.

## Status

Baudot has executable T.140 presentation vectors, RFC 4103 primary RTP vectors, routed SIP/Wiretap transport evidence, and a routed canonical primary `text/t140` proof. These are deliberately narrow evidence boundaries, not project-wide conformance claims.

No complete RFC 4103, T.140, SIP, WebRTC, accessibility, NAT/SBC, browser, or production-network conformance claim is made yet.

## Project name

The name honors Émile Baudot and the long lineage of real-time text communications. The project is independent and is not currently an Apache Software Foundation project.
