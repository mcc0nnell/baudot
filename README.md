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

## Shape

```text
T.140 semantics
      │
      ▼
normative vectors
      │
      ▼
baudot-testkit
      │
      ├── SIP / RFC 4103 adapters
      ├── WebRTC/application adapters
      └── external implementation oracles
                │
                ▼
         preserved evidence
                │
                ▼
        independent reducers
```

The first cross-project research integration is with ACE Omni: Omni can execute controlled communications experiments while Baudot owns the portable accessibility behavior and test vocabulary.

## Current proving ground

Baudot currently uses JAIN SIP as a glass-box signaling instrument and Sandia Wiretap as an external controlled-network substrate.

The executable proving ground now includes:

- deterministic T.140 semantic and presentation vectors;
- primary RTP/RFC 4103 T140block vectors and live SIP-negotiated RTT transport;
- RFC 2198 redundancy parsing and deterministic T.140 recovery;
- independently routed signaling and text-media paths through Wiretap;
- fail-fast topology preflight with evidence-bound reserved-prefix, route, namespace, host-link, and reverse-path assertions;
- `BAUDOT-INTEROP-003`, a runnable re-INVITE / SDP-freshness / RTT-readiness evidence chain;
- `BAUDOT-INTEROP-004`, a runnable REFER / replacement-dialog / accessibility-handoff evidence chain; and
- a bidirectional JAIN SIP ↔ Elixip `BAUDOT-INTEROP-004` matrix with controlled negative and positive readiness arms, preserved wire evidence, and independent terminal reduction.

A passing transfer does **not** mean that REFER succeeded. The relevant evidence can distinguish:

```text
REFER accepted=true
replacement dialog established=true
rttNegotiated=true
firstT140CharacterObserved=false
rttReady=false
old leg preserved
```

from a usable replacement leg where independently validated T.140 is observed before teardown.

The current cross-implementation matrix executes that decision in both implementation directions:

```text
JAIN SIP -> Elixip
  no observed T.140  => preserve original leg
  canonical T.140    => independently parse, then release original leg

Elixip -> JAIN SIP
  no observed T.140  => preserve original leg
  canonical T.140    => independently parse, then release original leg
```

The positive arms use explicitly Baudot-owned deterministic media stimulus and therefore do not claim native Elixip RFC 4103 media behavior.

See [`docs/sip-wiretap-harness.md`](docs/sip-wiretap-harness.md) for the routed harness and evidence model.

## Interoperability ensemble

[ADR-0001](docs/adr/0001-interoperability-ensemble-and-external-oracles.md) defines the current implementation boundary:

- **JAIN SIP** — primary glass-box signaling instrument;
- **Elixip** — first externally installed independent SIP/call-state oracle;
- **Apache OpenMeetings** — integration specimen and scenario donor, not the second independent SIP stack;
- **ACE Direct** — historical production donor corpus; and
- **Wiretap** — external network/evidence substrate, never verdict authority.

Baudot reducers and reference code retain terminal verdict authority within explicit claim boundaries. Implementation agreement is evidence, not correctness by majority vote.

The external-oracle lane is documented in [`interop/elixip/`](interop/elixip/). It admits one exact clean upstream Elixip checkout and hash-binds Baudot-owned FSL inputs before execution without vendoring or linking Elixip into Baudot. `BAUDOT-INTEROP-004` now exercises that boundary in both directions while keeping REFER acceptance, NOTIFY progression, replacement-dialog establishment, RTT negotiation, T.140 observation, old-leg teardown, and terminal readiness as separate evidence facts.

## Federation horizon

[ADR-0002](docs/adr/0002-federated-call-assembly-and-prospective-platform-peers.md) extends that separation to whole calls.

The target abstraction is not "call through provider X." It is:

```text
Call this person
with the accessibility services I require
```

Baudot treats VRS/interpreter services, RTT, captions, SIP/PSTN, WebRTC, conferencing systems, and future platform-specific peers as independent participants that can be assembled from explicit capabilities and user intent.

A motivating long-term case is a VRS provider participating in a call whose hearing endpoint is on a mainstream video platform such as FaceTime. **FaceTime is a prospective federation peer, not a current protocol dependency or conformance claim.** Baudot will use documented interoperability surfaces only; deeper closed-platform integration belongs behind a supportable platform adapter.

The near-term proving path is deliberately open: first model caller + interpreter + destination, prove the SIP and WebRTC endpoint boundaries independently, then join their media behavior through an explicit gateway. Native calling surfaces such as CallKit/LiveCommunicationKit come after that open gateway is evidenced. Closed-platform adapters come only after the missing interoperability boundary is precisely demonstrated.

The federation testkit currently includes:

- `BAUDOT-FED-001`, which reduces caller + interpreter + destination readiness and security claims without provider-specific semantics;
- `BAUDOT-FED-002`, which joins a live JAIN SIP caller-to-interpreter evidence gate with an RFC 8865/T.140 destination boundary and a real headless Chromium `RTCPeerConnection` endpoint exercise;
- `BAUDOT-FED-003`, which proves inline RFC 4103/RFC 2198-to-WebRTC T.140 continuity while keeping raw forwarding, primary T.140 semantics, browser transport state, and gateway media termination as separate evidence facts; and
- `BAUDOT-FED-004`, which uses a sender-controlled omission of RTP sequence 1 and proves that the gateway reconstructs the missing `B` exactly once from RFC 2198 redundancy before delivering `ABC` over a real Chromium `t140` data channel. The preserved SIP-side stream contains only sequences 0 and 2; gateway provenance is `(0,A,primary) → (1,B,redundant) → (2,C,primary)`; and the independent Python reducer must reach the same result with no missing-text marker.

Run the open SIP/interpreter boundary with:

```bash
bash scripts/run-fed002-open-boundary.sh
```

Run the inline gateway proving slice with:

```bash
bash scripts/run-fed003-inline-gateway.sh
```

Run the controlled RED recovery slice with:

```bash
bash scripts/run-fed004-red-loss-recovery.sh
```

The dedicated `federation-lab` workflow executes the browser and gateway lanes and preserves their evidence bundles. FED-004 is deliberately a **sender-controlled omission** proof, not a claim about network-induced loss, reordering timers, or broader standards conformance. The next recovery threshold is to induce loss in the routed network substrate itself while preserving the same packet/recovery evidence contract. A successful browser or gateway run is an execution fact, not WebRTC, RFC 4103, RFC 2198, SIP, VRS, or FaceTime conformance.

## Status and claim boundary

Baudot is in active proving-ground development. Several scenarios are **runnable**, but runnable is not the same as proven or conformant.

The repository does not currently claim full SIP, REFER, RFC 4103, RFC 2198, T.140, VRS, SBC/NAT, WebRTC, FaceTime, or implementation conformance. Promotion toward stronger interoperability claims requires additional independent implementations, broader endpoint/timing coverage, production-representative gateway evidence, native independent RFC 4103/T.140 media participation, and preserved evidence that satisfies each scenario's explicit `requiredBeforeProven` conditions.

## Project name

The name honors Émile Baudot and the long lineage of real-time text communications. The project is independent and is not currently an Apache Software Foundation project.
