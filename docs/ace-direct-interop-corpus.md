# ACE Direct interoperability donor corpus

Baudot uses historical production workarounds as **scenario donors**, not implementation donors.

The goal is to preserve the interoperability question that forced a workaround, then restate that question as a portable, evidence-bearing Baudot scenario. The original patch is not copied forward and is not treated as proof that a contemporary implementation has the same defect.

## Pinned donor

Repository: `mitre-ace-direct/ace-direct`

Pinned production commit:

```text
39c8f9ba73d889e743de56a2d49faf418b575c32
```

Relevant paths:

```text
README.md
acedirect-kurento/README.md
acedirect-kurento/Dockerfile
acedirect-kurento/confs/jssip-modifications/RTCSession.js
acedirect-kurento/confs/jssip-modifications/UA.js
acedirect-kurento/src/conf_manager.js
acedirect/public/js/jssip_agent.js
videomail-service/src/server.js
```

At that commit ACE Direct documents a dependency on JsSIP 3.5.1. Its build replaces installed JsSIP `RTCSession.js` and `UA.js` files with project-local versions.

Those local modifications and the surrounding application behavior are useful to Baudot because they identify protocol boundaries where production interoperability pressure accumulated.

## Donor rule

For each historical workaround:

```text
historical patch
      |
      v
interoperability question
      |
      v
portable Baudot scenario
      |
      v
controlled execution
      |
      v
preserved evidence
```

The donor source may motivate the question. It cannot supply the expected verdict by itself.

## Current donor cases

### ICE completion / readiness separation

`BAUDOT-INTEROP-001` captures the historical ACE Direct stalled-ICE boundary.

The useful invariant is not the old timeout value. It is that signaling success, ICE readiness, decoded media, rendered media, and RTT readiness are distinct observations.

### re-INVITE request correlation and SDP freshness

`BAUDOT-INTEROP-003` captures a second ACE-specific pressure point.

The patched `RTCSession` keeps current re-INVITE request and SDP state outside the individual transaction and exposes an application-level `respondReinvite()` path. The videomail service listens for a `reinvite` event and calls that response method.

Baudot therefore asks a transport-neutral question:

> When in-dialog re-INVITEs overlap or an answer is supplied externally, can every response be proven to bind to the intended request and to the intended SDP generation, and can signaling success be kept distinct from RTT usability?

The runnable scenario has four arms:

1. one ordinary re-INVITE with fresh SDP;
2. one externally supplied SDP response with preserved transaction identity;
3. two overlapping re-INVITEs whose responses remain independently correlated; and
4. deliberate stale-SDP reuse, where signaling remains healthy while RTT readiness is not promoted from signaling success alone.

The evidence bundle preserves raw SIP messages, transaction/dialog identifiers, raw SDP with hashes, chronological readiness observations, raw RTT datagrams, independent reference validation, and a terminal scenario verdict.

#### Gate 1: JAIN SIP message correlation

`ReinviteCorrelationProbe` uses JAIN SIP message objects to construct stable in-dialog request identities and exercise the correlation boundary directly.

The gate preserves Call-ID, From/To tags, CSeq, method, Via branch, raw SIP messages, raw SDP, and SHA-256 hashes. It observes the later overlapping request's `491 Request Pending` result before the earlier request's `200 OK`, verifies that both responses remain bound to the intended request identity, binds a declared external SDP answer to one request by hash, and deliberately returns stale SDP under a `200 OK` to prove that signaling success alone cannot establish SDP freshness.

This split respects the JAIN SIP RI's own dialog behavior: the RI contains explicit re-INVITE serialization logic intended to avoid interleaving INVITEs while a previous INVITE transaction or ACK is pending. Baudot therefore does not treat two simultaneously successful re-INVITEs as a required baseline behavior.

#### Gate 2: live dialog overlap

`LiveReinviteOverlapProbe` moves the overlap arm onto the wire. A real JAIN SIP UAS establishes an `INVITE -> 200 -> ACK` dialog with an independent raw UDP peer. The peer then sends CSeq 2 and, while that server transaction is deliberately left pending, independently injects CSeq 3 with the same dialog identity.

The gate requires CSeq 3 to receive `491 Request Pending`, then releases CSeq 2 and requires its `200 OK` and matching ACK. Raw requests and responses are preserved as supplemental evidence under the same manifest machinery as the rest of Baudot.

The raw peer is intentional. JAIN SIP's normal outbound dialog helper serializes re-INVITEs to avoid this overlap condition; bypassing that convenience path lets Baudot apply the exact UAS-side pressure that the scenario is meant to observe without modifying the JAIN SIP implementation.

#### Gate 3: live stale SDP and RTT readiness

`LiveReinviteRttReadinessProbe` joins signaling state to an independently observable RTT path.

The control re-INVITE returns fresh `m=text` / `t140/1000` SDP under `200 OK`. The peer follows that SDP and sends Baudot's existing canonical primary T.140 RTP datagram. The Java harness preserves the wire bytes but does not classify them as valid T.140. `scripts.validate_reinvite_rtt_readiness` independently parses the received packet through Baudot's Python RFC 4103 reference before `firstT140CharacterObserved` can become true. The control arm therefore reduces to:

```text
sipStatus=200
rttNegotiated=true
firstT140CharacterObserved=true
rttReady=true
```

The stale arm deliberately returns the prior answer SDP under another `200 OK` while the intended fresh RTT receiver has moved to a new port. The peer follows the stale advertised port, the stale answer is detected by SHA-256, and no first T.140 character reaches the intended fresh receiver within the bounded observation window:

```text
sipStatus=200
staleSdpDetected=true
rttNegotiated=true
firstT140CharacterObserved=false
rttReady=false
```

That is the accessibility invariant the donor history is useful for preserving: **successful SIP renegotiation is not the same fact as usable RTT after renegotiation.**

#### Terminal reduction

`scripts.validate_ace_reinvite_scenario` joins the three gates only after their evidence remains separate. It requires request correlation, external-SDP binding, live 491 glare, fresh control RTT readiness, stale-SDP detection, and failed stale-arm RTT readiness before writing:

```text
terminalVerdict=RUNNABLE_PASS
```

The complete scenario can be executed with:

```text
bash scripts/run-ace-reinvite-scenario.sh
```

`BAUDOT-INTEROP-003` is therefore **runnable**, not proven. Moving to `proven` requires repeatability across additional implementations and broader timing/endpoint evidence without weakening the current claim boundaries.

### REFER transfer and provider handoff

`BAUDOT-INTEROP-004` captures transfer as a continuity problem rather than a REFER-response problem.

ACE provides a concrete donor path. Its conference manager resolves a transfer target, records warm-transfer state separately from blind transfer, and invokes `jssip_session.refer(...)`. In the multiparty agent flow, the departing host first selects a backup host and emits the host transition before asking the media layer to transfer and then terminating the old leg.

Those behaviors motivate a provider-neutral question:

> Can a call move from provider A to provider B while the REFER transaction, NOTIFY outcome, replacement dialog, target identity, old-leg teardown, and accessibility readiness remain independently attributable?

The first gate is deliberately implementation-neutral. `testkit/refer/provider-transfer-matrix.json` defines three synthetic provider identities, every directed cross-provider pair, and blind/warm transfer as separate dimensions. That produces twelve provider/mode cells without assigning protocol semantics to any provider label.

`scripts/validate_refer_provider_matrix.py` then exercises positive and negative reducer cases. It keeps these facts separate:

```text
REFER accepted
NOTIFY reports success
replacement dialog established
replacement target correlated
old-leg continuity preserved
RTT negotiated
first T.140 character observed
RTT ready
```

The terminal transfer verdict cannot be `PASS` unless all required layers pass. In particular:

```text
REFER 2xx + NOTIFY 2xx + replacement dialog
    != RTT ready
```

The reducer also distinguishes target-correlation drift, premature old-leg teardown, signaling failure, and accessibility-readiness failure rather than collapsing all of them into a generic transfer failure.

`BAUDOT-INTEROP-004` remains **planned** because this first gate is a deterministic transfer contract, not a live SIP transfer. The next execution slice is a live JAIN SIP REFER/NOTIFY adapter with two independently addressed provider-role endpoints, raw original/replacement dialog evidence, and independent replacement-leg RTT observation. Provider names remain configuration so the same test can later become an A→B, A→C, B→A, or other real-world matrix without rewriting the reducer.

## Next donor candidates

With re-INVITE runnable and REFER modeled, inspect ACE behavior around:

- hold/resume renegotiation;
- DTMF behavior across application and SIP layers;
- SDP codec/media-line normalization;
- browser-to-Asterisk/Kamailio dialog edge cases; and
- any local JsSIP changes that bypass normal peer-connection description generation.

Each candidate should become a separate scenario only when its failure condition and evidence boundary can be stated independently.

## Claim boundary

This corpus does not establish that ACE Direct was defective, that its workarounds were unnecessary, that current JsSIP or JAIN SIP reproduces the same behavior, or that a passing Baudot scenario establishes SIP, REFER, WebRTC, RFC 4103, T.140, VRS, or accessibility conformance.

It establishes a disciplined path for turning real production interoperability history into reproducible tests.
