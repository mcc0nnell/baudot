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
      ├── SIP / RFC 4103 adapter
      ├── WebRTC/application adapter
      └── research-runtime adapter
                │
                ▼
         preserved evidence
```

The first cross-project research integration is with ACE Omni: Omni can execute controlled communications experiments while Baudot owns the portable accessibility behavior and test vocabulary.

## Current vertical slice

The first transport harness uses JAIN SIP for signaling and Sandia Wiretap as an external controlled-network substrate. It records signaling and media-path reachability independently so a run can prove states such as:

```text
scenarioResult=PASS
callState=CALL_ESTABLISHED
mediaState=MEDIA_FAILED
```

That means the experiment successfully reproduced a call whose SIP dialog established while its media path did not. The current media check is a correlated UDP heartbeat, not RTP or RFC 4103 conformance.

See [`docs/sip-wiretap-harness.md`](docs/sip-wiretap-harness.md) for the boundary, distributed caller/callee roles, Wiretap route model, and evidence bundle.

## Architecture decisions

- [ADR-0001: Treat Apache OpenMeetings as prior art, not a runtime dependency](docs/adr/0001-openmeetings-boundary.md)

## Status

Early design and testkit bootstrap. No RFC 4103, T.140, SIP, or implementation conformance claim is made yet.

## Project name

The name honors Émile Baudot and the long lineage of real-time text communications. The project is independent and is not currently an Apache Software Foundation project.
