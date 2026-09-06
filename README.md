# Baudot

**Accessible real-time communications, specified as behavior before implementation.**

Baudot is an independent open-source project for defining and testing interoperable accessible real-time communications behavior.

The project starts at the semantic boundary: **T.140 real-time text behavior and deterministic test vectors first**. SIP/RFC 4103, WebRTC, gateways, and application integrations are transport work layered on top of that core rather than substitutes for it.

## Why Baudot exists

Accessible real-time communications sit at the junction of disciplines that are usually documented and implemented separately: T.140/RTT semantics, SIP and SDP signaling, RFC 4103 media, call-state transitions, numbering and routing, VRS/iTRS service behavior, application gateways, controlled-network testing, and evidence preservation.

Interoperability failures tend to happen at those junctions. The knowledge needed to explain them often lives in different places: standards, vendor implementations, packet captures, production history, test harnesses, and institutional memory.

**Baudot's job is to make those boundaries executable.** It documents the parts of accessible telecommunications that otherwise tend to live only in institutional memory, vendor implementations, packet captures, and operational folklore, then turns them into portable scenarios, deterministic fixtures, observable facts, and reproducible evidence.

The project is not an attempt to replace every SIP stack, VRS provider, application, or network component. It provides a neutral semantic and test layer where those systems can be exercised against explicit behavior and claim boundaries.

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
- `BAUDOT-INTEROP-004`, a runnable REFER / replacement-dialog / accessibility-handoff evidence chain;
- a bidirectional JAIN SIP ↔ Elixip `BAUDOT-INTEROP-004` matrix with controlled negative and positive readiness arms, preserved wire evidence, and independent terminal reduction;
- a PJSIP 2.17 native-media qualification lane in which PJSUA2/PJMEDIA generates live text traffic that Baudot independently reduces to T.140 behavior;
- an incoming PJSIP 2.17 native-text endpoint qualification in which JAIN releases the controlled call only after the live Baudot reference publishes readiness;
- a JAIN SIP → PJSIP 2.17 `BAUDOT-INTEROP-004` positive arm in which native PJMEDIA text replaces Baudot-owned canonical stimulus and original-leg release is gated by the independent live readiness token; and
- an ACE Direct Kamailio/rtpengine donor gate that keeps proxy routing, SDP/media relay control, packet observation, and terminal T.140 readiness as separate evidence facts before a live proxy/relay experiment is admitted.

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

The Elixip matrix executes that decision in both implementation directions:

```text
JAIN SIP -> Elixip
  no observed T.140  => preserve original leg
  canonical T.140    => independently parse, then release original leg

Elixip -> JAIN SIP
  no observed T.140  => preserve original leg
  canonical T.140    => independently parse, then release original leg
```

Those Elixip positive arms use explicitly Baudot-owned deterministic media stimulus and therefore do not claim native Elixip RFC 4103 media behavior.

The native PJSIP positive arm crosses a different threshold:

```text
JAIN SIP original dialog
  -> REFER accepted
  -> PJSIP replacement dialog established
  -> direct PT 98 t140/1000 negotiated
  -> PJSIP native text media active
  -> PJSIP Call::sendText("H")
  -> Baudot Python reference accepts live implementation-generated RTP/T.140
  -> atomic rttReady token published
  -> JAIN consumes token as opaque authority evidence
  -> only then original leg released
```

Java does not parse the implementation-generated RTP and does not compare it to canonical packet bytes. PJSIP does not declare readiness. The live Python reference owns the replacement `m=text` observation socket and is the only component that can publish `rttReady=true` for this arm.

[ADR-0002](docs/adr/0002-pjsip-native-rtt-media-oracle.md) admits PJSIP/PJPROJECT 2.17 as an external native RTT media oracle at exact commit `5a457451fa2712ba18e12b01738e8ff3af2b26fd`. The accepted profile remains external and ephemeral; the linked qualification executable is not distributed as a Baudot artifact.

See [`docs/sip-wiretap-harness.md`](docs/sip-wiretap-harness.md) for the routed harness and evidence model.

## Interoperability ensemble

[ADR-0001](docs/adr/0001-interoperability-ensemble-and-external-oracles.md) defines the base implementation boundary:

- **JAIN SIP** — primary glass-box signaling instrument;
- **Elixip** — first externally installed independent SIP/call-state oracle;
- **PJSIP/PJPROJECT 2.17** — accepted external native RTT media oracle under ADR-0002, not a replacement for JAIN SIP or Elixip;
- **Apache OpenMeetings** — integration specimen and scenario donor, not the second independent SIP stack;
- **ACE Direct** — historical production donor corpus, including the Kamailio/rtpengine proxy-and-relay boundary;
- **Wiretap** — external network/evidence substrate, never verdict authority.

Baudot reducers and reference code retain terminal verdict authority within explicit claim boundaries. Implementation agreement is evidence, not correctness by majority vote.

The Elixip external-oracle lane is documented in [`interop/elixip/`](interop/elixip/). It admits one exact clean upstream Elixip checkout and hash-binds Baudot-owned FSL inputs before execution without vendoring or linking Elixip into Baudot. `BAUDOT-INTEROP-004` exercises that boundary in both directions while keeping REFER acceptance, NOTIFY progression, replacement-dialog establishment, RTT negotiation, T.140 observation, old-leg teardown, and terminal readiness as separate evidence facts.

The PJSIP native-media lane is documented in [`interop/pjsip/`](interop/pjsip/). It separately qualifies native outbound text generation, incoming native text endpoint behavior, and participation as the replacement native-media endpoint in a controlled `BAUDOT-INTEROP-004` positive arm. In all three profiles, PJSIP supplies implementation behavior while Baudot's independent reference retains semantic readiness authority.

The ACE Kamailio/rtpengine donor lane is documented in [`interop/ace-kamailio/`](interop/ace-kamailio/). Its static vectors preserve production-derived proxy/media-relay pressure without running external services. A future live lane will insert an ephemeral Kamailio + rtpengine substrate between independently qualified native endpoints while keeping relay-control observations out of the terminal RTT verdict.

## Status and claim boundary

Baudot is in active proving-ground development. Several scenarios are **runnable**, but runnable is not the same as proven or conformant.

The repository does not currently claim full SIP, REFER, RFC 4103, RFC 2198, T.140, VRS, SBC/NAT, WebRTC, PJSIP, Elixip, JAIN SIP, Kamailio, rtpengine, or other implementation conformance. The native PJSIP handoff arm is evidence that the pinned implementation participated in one controlled replacement-leg flow whose live media was independently reduced before old-leg release; it is not a general conformance finding. The ACE Kamailio/rtpengine lane is currently a static donor boundary, not live proxy/media-relay qualification. Promotion toward stronger interoperability claims requires broader endpoint/timing coverage, production-representative gateway evidence, additional independent native-media implementations, and preserved evidence that satisfies each scenario's explicit `requiredBeforeProven` conditions.

## Project name

The name honors Émile Baudot and the long lineage of real-time text communications. The project is independent and is not currently an Apache Software Foundation project.
