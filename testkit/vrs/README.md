# VRS public-interoperability test inputs

This directory translates publicly documented VRS and Relay User Equipment (RUE) interoperability behavior into clean-room Baudot test inputs.

It is intentionally **not** a provider simulator, a copy of a production VRS configuration, a TRS Numbering Directory client, or a conformance suite.

## Contents

- `public-interoperability-matrix-v1.json` — public requirements mapped to planned/partial Baudot evidence lanes.
- `fixtures/provider-list-v1.json` — synthetic RFC 9248-shaped provider-selection input using reserved example domains.
- `fixtures/provider-config-provider-b-v1.json` — synthetic ProviderConfig input keeping one-stage and two-stage dial-around configuration explicit.
- `fixtures/rue-one-stage-dial-around-invite.txt` — synthetic SIP request binding one-stage dial-around route-selection facts without claiming media readiness.
- `fixtures/rue-two-stage-front-door-invite.txt` — synthetic two-stage front-door request that deliberately omits the final called number from the initial INVITE.
- `fixtures/rue-rtt-negotiation-arms-v1.json` — controlled RTT session arms separating local policy, remote T.140 offer, negotiation, first text observation, and terminal readiness.
- `executions/RUE-DIAL-001-jain.json` — bounded live JAIN SIP dial-around execution contract.
- `executions/RUE-RTT-001-negotiation-python.json` — deterministic RTT negotiation/readiness reduction contract.
- `executions/RUE-RTT-001-jain-negotiation.json` — live JAIN SIP RTT offer/answer execution with independent Python reduction.
- `research/public-implementation-donors-v1.json` — revision-pinned historical implementation donors that may motivate scenarios but never supply normative or terminal verdict authority.

The research and authority map lives in [`../../docs/vrs-public-interoperability-osint.md`](../../docs/vrs-public-interoperability-osint.md). Historical implementation archaeology lives in [`../../docs/vrs-public-implementation-archaeology.md`](../../docs/vrs-public-implementation-archaeology.md).

## Authority boundary

Keep these sources distinct:

```text
47 CFR § 64.621
  -> U.S. regulatory VRS interoperability obligation
  -> incorporates SIP Forum TWG-6-1.0

SIP Forum TWG-6-2.0
  -> newer ratified industry provider profile
  -> not silently substituted for the incorporated 1.0 text

RFC 9248
  -> public RUE <-> provider / RUE <-> RUE interoperability profile
  -> source for the RUE test rows in this directory
```

Operational event reports and MITRE National Test Lab descriptions show that repeatable multi-provider interoperability testing exists at significant scale. They are context, not normative authorities and not substitutes for actual test specifications.

## Clean-room rules

1. Use only synthetic telephone numbers, identities, contact records, credentials, locations, and domains in committed fixtures.
2. Do not commit live TRS Numbering Directory responses or subscriber records.
3. Do not copy production provider SIP traces into the repository.
4. Provider names in executable fixtures are `provider-a`, `provider-b`, etc.; a real provider name may appear only when accurately citing public historical material.
5. Route success, signaling success, transport readiness, video readiness, RTT readiness, and security claims remain separate observations.
6. A public standard identifies what to test; only preserved execution evidence can establish what an implementation did.
7. No emergency scenario may originate a real emergency call from the public test harness.
8. No production infrastructure is probed merely because an endpoint or domain can be discovered through OSINT.

## Dial-around progression

The first executable routing progression is deliberately narrow:

```text
synthetic provider selection
    -> selected provider entry point
    -> synthetic one-stage dial-around Request-URI
    -> controlled SIP peer
    -> dialog evidence
    -> separate media/RTT/security lanes
```

Two-stage dial-around remains a separate fixture shape: the initial SIP target is the provider-configured front door, while the final destination belongs to a later interaction phase. Baudot does not collapse those semantics into the one-stage route test.

## RTT negotiation is not RTT readiness

`RUE-RTT-001` now has three controlled executable negotiation arms:

```text
local RTT enabled + remote has no T.140
    -> rttNegotiated=false
    -> rttReady=false

remote offers T.140 + manipulated local policy disables RTT
    -> rttNegotiated=false
    -> rttReady=false

local RTT enabled + remote offers T.140 + answer accepts T.140
    -> rttNegotiated=true
    -> firstT140CharacterObserved=false
    -> rttReady=false
```

The third arm is intentionally a positive **negotiation** control and a negative **readiness** control. It prevents SDP success from being promoted into accessibility readiness.

### Deterministic reducer lane

```bash
python -m unittest tests.test_rue_rtt_negotiation
python -m scripts.validate_rue_rtt_negotiation
```

This lane writes bounded evidence to `target/evidence/RUE-RTT-NEGOTIATION/`.

### Live JAIN SIP negotiation lane

```bash
bash scripts/run-rue-rtt-negotiation-live.sh
```

The live lane creates three actual loopback SIP dialogs. The synthetic remote endpoint sends the arm-specific INVITE/SDP offer; the synthetic RUE sends the arm-specific 200 OK/SDP answer; ACK is observed; and both sides preserve the SDP bytes they actually received.

Java deliberately sends no RTT datagrams and does not classify the SDP. `scripts/validate_rue_rtt_live_execution.py` independently parses the preserved offer and answer, treats a port-zero `m=text` as rejected, joins the manipulated local policy fact, and writes its bounded results under `target/evidence/RUE-RTT-NEGOTIATION-LIVE/`.

For the positive negotiation control the live expected chain remains:

```text
real SIP dialog established
    -> remote T.140 offer observed
    -> active T.140 answer observed
    -> rttNegotiated=true
    -> no T.140 media originated
    -> firstT140CharacterObserved=false
    -> rttReady=false
```

A later media-bearing arm can feed the existing independent live T.140 observation gate into the same readiness rule. Negotiation still cannot manufacture readiness.

The local-disabled arm is deliberately a test-policy manipulation. It is not a claim that RFC 9248 permits an implementation to omit mandatory RTT capability. Likewise, a synthetic remote offer without T.140 is a session-state negative control, not by itself a provider-conformance finding.

## Implementation ensemble

This composes naturally with the existing Baudot implementation ensemble. JAIN SIP can remain the glass-box signaling instrument; Elixip/PJSIP/Linphone-class implementations can supply independent implementation behavior; Wiretap can remain network/evidence substrate; and Baudot reducers retain terminal verdict authority.

## Claim boundary

Nothing in this directory proves:

- current behavior of any VRS provider;
- access to or correctness of the live TRS Numbering Directory;
- VRS Provider Interoperability Profile compliance;
- RFC 9248, SIP, SRTP, ICE, H.264, RFC 4103, RFC 2198, RFC 8865, or T.140 conformance;
- production readiness; or
- regulatory certification.
