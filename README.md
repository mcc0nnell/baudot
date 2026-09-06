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
- `BAUDOT-INTEROP-004`, a runnable REFER / replacement-dialog / accessibility-handoff evidence chain;
- a bidirectional JAIN SIP ↔ Elixip `BAUDOT-INTEROP-004` matrix with controlled negative and positive readiness arms, preserved wire evidence, and independent terminal reduction;
- a PJSIP 2.17 native-media qualification lane in which PJSUA2/PJMEDIA generates live text traffic that Baudot independently reduces to T.140 behavior;
- an incoming PJSIP 2.17 native-text endpoint qualification in which JAIN releases the controlled call only after the live Baudot reference publishes readiness; and
- a JAIN SIP → PJSIP 2.17 `BAUDOT-INTEROP-004` positive arm in which native PJMEDIA text replaces Baudot-owned canonical stimulus and original-leg release is gated by the independent live readiness token.

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

[ADR-0003](docs/adr/0003-linphone-native-rtt-candidate.md) proposes the Linphone SDK as the next independent native RTT implementation candidate. It pins an exact clean upstream source profile and a public-API-only Baudot driver, but it does **not** admit Linphone as an oracle until live implementation-generated wire traffic is independently reduced to the expected T.140 behavior.

See [`docs/sip-wiretap-harness.md`](docs/sip-wiretap-harness.md) for the routed harness and evidence model.

## Interoperability ensemble

[ADR-0001](docs/adr/0001-interoperability-ensemble-and-external-oracles.md) defines the base implementation boundary:

- **JAIN SIP** — primary glass-box signaling instrument;
- **Elixip** — first externally installed independent SIP/call-state oracle;
- **PJSIP/PJPROJECT 2.17** — accepted external native RTT media oracle under ADR-0002, not a replacement for JAIN SIP or Elixip;
- **Linphone SDK** — proposed second independent native RTT implementation candidate under ADR-0003; source-admitted for qualification, not yet an oracle;
- **Apache OpenMeetings** — integration specimen and scenario donor, not the second independent SIP stack;
- **ACE Direct** — historical production donor corpus; and
- **Wiretap** — external network/evidence substrate, never verdict authority.

Baudot reducers and reference code retain terminal verdict authority within explicit claim boundaries. Implementation agreement is evidence, not correctness by majority vote.

The Elixip external-oracle lane is documented in [`interop/elixip/`](interop/elixip/). It admits one exact clean upstream Elixip checkout and hash-binds Baudot-owned FSL inputs before execution without vendoring or linking Elixip into Baudot. `BAUDOT-INTEROP-004` exercises that boundary in both directions while keeping REFER acceptance, NOTIFY progression, replacement-dialog establishment, RTT negotiation, T.140 observation, old-leg teardown, and terminal readiness as separate evidence facts.

The PJSIP native-media lane is documented in [`interop/pjsip/`](interop/pjsip/). It separately qualifies native outbound text generation, incoming native text endpoint behavior, and participation as the replacement native-media endpoint in a controlled `BAUDOT-INTEROP-004` positive arm. In all three profiles, PJSIP supplies implementation behavior while Baudot's independent reference retains semantic readiness authority.

The Linphone candidate lane is documented in [`interop/linphone/`](interop/linphone/). Its admission workflow verifies the exact pinned `BelledonneCommunications/linphone-sdk` source identity and the public/native RFC 4103/T.140 implementation surfaces that justify a live qualification. The candidate driver stays at the public Liblinphone API boundary and emits one deterministic application character; it neither constructs canonical RTP/T.140 packets nor owns the terminal readiness verdict.

## Status and claim boundary

Baudot is in active proving-ground development. Several scenarios are **runnable**, but runnable is not the same as proven or conformant.

The repository does not currently claim full SIP, REFER, RFC 4103, RFC 2198, T.140, VRS, SBC/NAT, WebRTC, PJSIP, Elixip, JAIN SIP, Linphone, or other implementation conformance. The native PJSIP handoff arm is evidence that the pinned implementation participated in one controlled replacement-leg flow whose live media was independently reduced before old-leg release; it is not a general conformance finding. Linphone remains only a proposed candidate until ADR-0003's live wire-evidence requirements are satisfied. Promotion toward stronger interoperability claims requires broader endpoint/timing coverage, production-representative gateway evidence, additional independent native-media implementations, and preserved evidence that satisfies each scenario's explicit `requiredBeforeProven` conditions.

## Project name

The name honors Émile Baudot and the long lineage of real-time text communications. The project is independent and is not currently an Apache Software Foundation project.
