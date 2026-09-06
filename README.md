# Baudot

**Accessible real-time communications, specified as behavior before implementation.**

Baudot is an independent open-source project for defining and testing interoperable accessible real-time communications behavior, with the same evidence-first machinery now applied to a public-data-calibrated synthetic TRS Fund proving lane.

Project site: **https://mcc0nnell.github.io/baudot/**

The communications work starts at the semantic boundary: **T.140 real-time text behavior and deterministic test vectors first**. SIP/RFC 4103, WebRTC, gateways, and application integrations are transport work layered on top of that core rather than substitutes for it.

## Why Baudot exists

Accessible real-time communications sit at the junction of disciplines that are usually documented and implemented separately: T.140/RTT semantics, SIP and SDP signaling, RFC 4103 media, call-state transitions, numbering and routing, VRS/iTRS service behavior, application gateways, controlled-network testing, and evidence preservation.

Interoperability failures tend to happen at those junctions. The knowledge needed to explain them often lives in different places: standards, vendor implementations, packet captures, production history, test harnesses, and institutional memory.

**Baudot's job is to make those boundaries executable.** It documents the parts of accessible telecommunications that otherwise tend to live only in institutional memory, vendor implementations, packet captures, and operational folklore, then turns them into portable scenarios, deterministic fixtures, observable facts, and reproducible evidence.

The project is not an attempt to replace every SIP stack, VRS provider, application, network component, financial platform, or program administrator. It provides a neutral test layer where implementations can be exercised against explicit behavior and claim boundaries.

## Working principles

1. **Behavior before stack choice.** A normative or interoperable behavior should be expressible as a portable test vector before it is tied to one SIP, WebRTC, application, or ledger implementation.
2. **Connected is not usable.** Signaling success, transport readiness, media receipt, presentation, and RTT readiness are separate observable facts.
3. **Balanced is not authorized.** An accepted accounting transaction does not establish provider eligibility, contributor liability, or program authorization.
4. **Evidence before conformance claims.** A fixture, implementation, or adapter does not become conformant because documentation says so; the evidence path must support the claim.
5. **Transport does not redefine text semantics.** T.140 behavior belongs to the core. RFC 4103/SIP and other transports carry it.
6. **Interop and operational failures become tests.** Historical production workarounds can motivate scenarios, but they are not copied forward or treated as proof that a modern implementation has the same defect.

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

## Synthetic TRS Fund proving ground

Baudot also carries a public-data-calibrated **synthetic end-to-end TRS Fund proving ground**. This is not a generic banking demo and not a reconstruction of the Fund administrator's production systems.

The Fund lane composes the financial lifecycle as explicit, testable boundaries:

```text
public policy / program-year inputs
        -> contributor assessments / billing / collections
        -> Fund receivables and cash
        -> provider claims / approvals / payables
        -> disbursements
        -> adjustments / recoveries / true-ups
        -> reconciliation and preserved audit evidence
```

**Apache Fineract is the financial kernel, not the TRS policy engine.** Baudot owns the synthetic Fund domain, scenario fixtures, policy/rate selection, authorization state, program invariants, and independent reconciliation; Fineract is exercised as an external general-ledger implementation. Accounting acceptance never substitutes for provider eligibility, contributor liability, payment authorization, routing authority, or accessibility readiness.

The live proving lane now crosses the external-ledger boundary. CI checks out Apache Fineract **1.15.0**, verifies source commit `d5636847ac556c30b437254c353f05526d172b97`, builds the test container from that exact source tree with Fineract's own `:fineract-provider:jibDockerBuild` task, and preserves the source tree, toolchain, local image ID, and runtime evidence before executing the synthetic accounting scenario.

The base loop is deliberately small but evidence-heavy:

```text
$10,000 contributor assessment
  -> $10,000 receipt
  -> $6,000 approved synthetic provider claim
  -> $6,000 disbursement
  -> explicit reversal
  -> distinct repost
  -> $4,000 expected ending Fund cash
```

The same disposable instance then closes accounting through the scenario date, requires a closed-date correction to fail with Fineract's accounting-closed error, accepts the same synthetic correction on the next open date, and reverses it explicitly. `FUND-CLS-001` is promoted only from observed live evidence.

The canonical synthetic chart currently keeps the ledger vocabulary small:

```text
1100  TRS Fund Cash
1200  Contributor Receivable
2100  Provider Payable
4100  Contribution Revenue
5100  TRS Provider Compensation Expense
5200  TRS Program Administration Expense
5300  NDBEDP Program Expense
```

Fineract-generated resource IDs are execution evidence; Baudot event IDs and account numbers remain the stable synthetic domain vocabulary. A provider or contributor is not automatically modeled as a Fineract banking client or product.

The next accounting slice is a revised Form 499-A true-up that preserves the original filing and assessment, posts only the evidence-bearing delta, exercises underpayment and overpayment, and introduces an explicit contributor-credit liability rather than hiding a credit as a negative receivable.

See:

- [`docs/trs-fund-public-ledger.md`](docs/trs-fund-public-ledger.md) — lifecycle, public calibration, authority model, account model, invariants, and long-horizon replay;
- [`docs/trs-fund-fineract-live-lane.md`](docs/trs-fund-fineract-live-lane.md) — source-pinned Fineract execution, reversal, closure probe, and evidence bundle; and
- [the Synthetic TRS Fund Lab webpage](https://mcc0nnell.github.io/baudot/fund-lab/) — public project view of the proving lane.

## Current proving ground

Baudot currently uses JAIN SIP as a glass-box signaling instrument and Sandia Wiretap as an external controlled-network substrate.

The executable communications proving ground now includes:

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

See [`docs/sip-wiretap-harness.md`](docs/sip-wiretap-harness.md) for the routed harness and evidence model.

## Interoperability ensemble

[ADR-0001](docs/adr/0001-interoperability-ensemble-and-external-oracles.md) defines the base implementation boundary:

- **JAIN SIP** — primary glass-box signaling instrument;
- **Elixip** — first externally installed independent SIP/call-state oracle;
- **PJSIP/PJPROJECT 2.17** — accepted external native RTT media oracle under ADR-0002, not a replacement for JAIN SIP or Elixip;
- **Apache OpenMeetings** — integration specimen and scenario donor, not the second independent SIP stack;
- **ACE Direct** — historical production donor corpus; and
- **Wiretap** — external network/evidence substrate, never verdict authority.

Baudot reducers and reference code retain terminal verdict authority within explicit claim boundaries. Implementation agreement is evidence, not correctness by majority vote.

The Elixip external-oracle lane is documented in [`interop/elixip/`](interop/elixip/). It admits one exact clean upstream Elixip checkout and hash-binds Baudot-owned FSL inputs before execution without vendoring or linking Elixip into Baudot. `BAUDOT-INTEROP-004` exercises that boundary in both directions while keeping REFER acceptance, NOTIFY progression, replacement-dialog establishment, RTT negotiation, T.140 observation, old-leg teardown, and terminal readiness as separate evidence facts.

The PJSIP native-media lane is documented in [`interop/pjsip/`](interop/pjsip/). It separately qualifies native outbound text generation, incoming native text endpoint behavior, and participation as the replacement native-media endpoint in a controlled `BAUDOT-INTEROP-004` positive arm. In all three profiles, PJSIP supplies implementation behavior while Baudot's independent reference retains semantic readiness authority.

## Status and claim boundary

Baudot is in active proving-ground development. Several scenarios are **runnable**, but runnable is not the same as proven or conformant.

The repository does not currently claim full SIP, REFER, RFC 4103, RFC 2198, T.140, VRS, SBC/NAT, WebRTC, PJSIP, Elixip, JAIN SIP, Fineract, TRS Fund administration, accounting, or other implementation conformance. The native PJSIP handoff arm is evidence that the pinned implementation participated in one controlled replacement-leg flow whose live media was independently reduced before old-leg release; it is not a general conformance finding. Likewise, a passing Fund scenario can establish only the observed behavior of the declared synthetic workload against the pinned ledger build, not real-world program authority or production suitability.

Promotion toward stronger claims requires broader endpoint/timing or financial-scenario coverage, production-representative gateway or accounting evidence where appropriate, additional independent implementations, and preserved evidence that satisfies each scenario's explicit gate conditions.

## Project name

The name honors Émile Baudot and the long lineage of real-time text communications. The project is independent and is not currently an Apache Software Foundation project.
