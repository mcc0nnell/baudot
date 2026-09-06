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
- a bidirectional JAIN SIP ↔ Elixip `BAUDOT-INTEROP-004` matrix with controlled negative and positive readiness arms, preserved wire evidence, and independent terminal reduction; and
- `BAUDOT-INTEROP-005`, a runnable iTRS-derived route-handoff chain that keeps authoritative route identity distinct from immediate SIP transport discovery.

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

## iTRS / VRS interoperability lab

`testkit/itrs/` has grown from deterministic routing fixtures into a layered, clean-room interoperability proving ground. The architectural rule remains the same throughout: **classification, route authority, transport selection, signaling success, and media readiness are separate facts.**

The evidence ladder is now:

```text
public FCC routing semantics
          |
          v
synthetic iTRS CTE
URD / NPAC / provider state
          |
          +--> historical ACE /vrsverify/ classification adapter
          |
          v
pinned ACE Connect Lite A / B
real historical outbound-call handlers
          |
          v
real AMI Originate
          |
          v
controlled Asterisk A / B
          |
          | authenticated AllCallQuery
          v
exact logical SIP URI
          |
          | PJSIP + separate outbound proxy
          v
JAIN-SIP evidence peer
```

The CTE models public-evidence relationships such as TN→URI routing, service and user type, default-provider XSPID responsibility, URD-valid state, NPAC porting observations, provisioning/query replication, AllCallQuery context, transaction IDs, and reverse validation. It does not claim to reproduce a proprietary iconectiv/Neustar schema or nonpublic interface guide.

The ACE compatibility layer is deliberately narrow. The pinned historical source consumes `GET /vrsverify/?vrsnum=...` and branches on `message === "success"`; Baudot reproduces only that observed consumer shape. `/vrsverify/` remains classification. **AllCallQuery remains logical-route authority.**

The dual-provider runtime slices then preserve that separation through real application and PBX boundaries:

```text
provider A -> 2025550103 -> sip:2025550103@provider-b.invalid
provider B -> 2025550101 -> sip:2025550101@vrs-a.example.invalid
```

The controlled Asterisk dialplan does not hard-code those destination domains. After ACE chooses its historical `outbound-CA` context, the dialplan independently performs an authenticated AllCallQuery and sends the returned URI through PJSIP while a separate loopback proxy determines the immediate transport destination.

The intended signaling proof completes:

```text
ACE outbound-call
  -> real AMI
  -> Asterisk
  -> authenticated route lookup
  -> SIP INVITE
  -> 200 OK
  -> ACK
  -> BYE
  -> 200 OK
```

with `2025550105` as a URD-invalid negative control that must remain on ACE's `from-phones` path and never reach the route AGI or JAIN-SIP peer.

### Verification status

Status snapshot: **2026-09-05 21:12 America/New_York**.

The dual-ACE and dual-ACE/Asterisk GitHub Actions jobs are currently **queued**. They have not acquired a runner, executed steps, produced logs, or uploaded evidence artifacts. The correct current description is therefore:

> **Implemented and runnable; awaiting hosted runtime verification.**

The expected terminal strings:

```text
Dual ACE Connect Lite runtime lab: 5/5 PASS
Dual ACE -> Asterisk -> JAIN-SIP lab: 8/8 PASS
```

are target verdicts, not current results. Baudot does not promote queued workflows, expected output, syntax checks, or local compilation into interoperability claims.

See [`docs/itrs-vrs-interoperability-lab.md`](docs/itrs-vrs-interoperability-lab.md) for the full evidence ladder, source boundary, current status, and promotion rules.

Even after the signaling path turns green, that result will not establish media or RTT interoperability. T.140/RFC 4103 remains the next independent evidence layer.

## Interoperability ensemble

[ADR-0001](docs/adr/0001-interoperability-ensemble-and-external-oracles.md) defines the current implementation boundary:

- **JAIN SIP** — primary glass-box signaling instrument;
- **Elixip** — first externally installed independent SIP/call-state oracle;
- **Apache OpenMeetings** — integration specimen and scenario donor, not the second independent SIP stack;
- **ACE Direct** — historical production donor corpus; and
- **Wiretap** — external network/evidence substrate, never verdict authority.

Baudot reducers and reference code retain terminal verdict authority within explicit claim boundaries. Implementation agreement is evidence, not correctness by majority vote.

The external-oracle lane is documented in [`interop/elixip/`](interop/elixip/). It admits one exact clean upstream Elixip checkout and hash-binds Baudot-owned FSL inputs before execution without vendoring or linking Elixip into Baudot. `BAUDOT-INTEROP-004` now exercises that boundary in both directions while keeping REFER acceptance, NOTIFY progression, replacement-dialog establishment, RTT negotiation, T.140 observation, old-leg teardown, and terminal readiness as separate evidence facts.

## Evidence and governance

Baudot is being structured so that useful interoperability claims can outlive any one stack, provider, lab, or maintainer.

The project model is:

```text
claim
  -> portable contract
  -> controlled input
  -> replaceable execution adapter
  -> observations
  -> preserved evidence
  -> independent reduction
  -> bounded verdict
```

This is what the project informally means by **Apache-style proof**: the durable asset is becoming the shared contract, test corpus, evidence model, and implementation-independent interoperability process rather than one privileged implementation.

That phrase describes an engineering direction only. Baudot is not currently an Apache Software Foundation project or podling.

See [`docs/evidence-and-governance.md`](docs/evidence-and-governance.md) for the full model, including clean-room donor discipline, scenario promotion rules, implementation independence, and the evidence milestones required before stronger governance or conformance claims would be credible.

## Status and claim boundary

Baudot is in active proving-ground development. Several scenarios are **runnable**, but runnable is not the same as proven or conformant.

The repository does not currently claim full SIP, REFER, RFC 4103, RFC 2198, T.140, VRS, SBC/NAT, WebRTC, or implementation conformance. Promotion toward stronger interoperability claims requires additional independent implementations, broader endpoint/timing coverage, production-representative gateway evidence, native independent RFC 4103/T.140 media participation, and preserved evidence that satisfies each scenario's explicit `requiredBeforeProven` conditions.

## Project name

The name honors Émile Baudot and the long lineage of real-time text communications. The project is independent and is not currently an Apache Software Foundation project.
