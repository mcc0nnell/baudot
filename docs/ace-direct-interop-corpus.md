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
videomail-service/src/server.js
```

At that commit ACE Direct documents a dependency on JsSIP 3.5.1. Its build replaces installed JsSIP `RTCSession.js` and `UA.js` files with project-local versions.

Those local modifications are useful to Baudot because they identify protocol boundaries where production interoperability pressure accumulated.

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

`BAUDOT-INTEROP-001` already captures the historical ACE Direct stalled-ICE boundary.

The useful invariant is not the old timeout value. It is that signaling success, ICE readiness, decoded media, rendered media, and RTT readiness are distinct observations.

### re-INVITE request correlation and SDP freshness

`BAUDOT-INTEROP-003` captures a second ACE-specific pressure point.

The patched `RTCSession` keeps current re-INVITE request and SDP state outside the individual transaction and exposes an application-level `respondReinvite()` path. The videomail service listens for a `reinvite` event and calls that response method.

Baudot therefore asks a transport-neutral question:

> When in-dialog re-INVITEs overlap or an answer is supplied externally, can every response be proven to bind to the intended request and to the intended SDP generation?

The first runnable slice should exercise four arms:

1. one ordinary re-INVITE with fresh SDP;
2. one externally supplied SDP response with preserved transaction identity;
3. two overlapping re-INVITEs whose responses must remain independently correlated; and
4. deliberate stale-SDP reuse, where signaling may remain healthy but readiness must not be promoted from signaling success alone.

The evidence bundle should preserve raw SIP messages, transaction/dialog identifiers, raw SDP with hashes, chronological readiness observations, and the terminal verdict. Dynamic transport identifiers may be normalized only after the raw evidence is preserved.

#### First executable gate: JAIN SIP message correlation

The first executable gate is intentionally narrower than the full scenario. `ReinviteCorrelationProbe` uses JAIN SIP message objects to construct stable in-dialog request identities and then exercises the correlation boundary directly.

The gate preserves Call-ID, From/To tags, CSeq, method, Via branch, raw SIP messages, raw SDP, and SHA-256 hashes. It observes the later overlapping request's `491 Request Pending` result before the earlier request's `200 OK`, verifies that both responses remain bound to the intended request identity, binds a declared external SDP answer to one request by hash, and deliberately returns stale SDP under a `200 OK` to prove that signaling success alone cannot establish SDP freshness.

This split also respects the JAIN SIP RI's own dialog behavior: the RI contains explicit re-INVITE serialization logic intended to avoid interleaving INVITEs while a previous INVITE transaction or ACK is pending. Baudot therefore does not treat two simultaneously successful re-INVITEs as a required baseline behavior.

A passing message-correlation gate still records:

```text
live.dialog.overlap.proven=false
media.readiness.proven=false
```

#### Second executable gate: live dialog overlap

`LiveReinviteOverlapProbe` moves the overlap arm onto the wire. A real JAIN SIP UAS establishes an `INVITE -> 200 -> ACK` dialog with an independent raw UDP peer. The peer then sends CSeq 2 and, while that server transaction is deliberately left pending, independently injects CSeq 3 with the same dialog identity.

The gate requires CSeq 3 to receive `491 Request Pending`, then releases CSeq 2 and requires its `200 OK` and matching ACK. Raw requests and responses are preserved as supplemental evidence under the same manifest machinery as the rest of Baudot.

The raw peer is intentional. JAIN SIP's normal outbound dialog helper serializes re-INVITEs to avoid this overlap condition; bypassing that convenience path lets Baudot apply the exact UAS-side pressure that the scenario is meant to observe without modifying the JAIN SIP implementation.

A passing live-overlap gate can set:

```text
live.dialog.overlap.proven=true
```

but still records:

```text
media.readiness.proven=false
```

`BAUDOT-INTEROP-003` therefore remains `planned`. The remaining runnable boundary is a live stale/mismatched-SDP arm plus independent media or RTT readiness observations that demonstrate why a `200 OK` cannot, by itself, establish usable post-renegotiation state.

## Next donor candidates

After the re-INVITE slice is executable, inspect ACE behavior around:

- hold/resume renegotiation;
- REFER and transfer handling;
- DTMF behavior across application and SIP layers;
- SDP codec/media-line normalization;
- browser-to-Asterisk/Kamailio dialog edge cases; and
- any local JsSIP changes that bypass normal peer-connection description generation.

Each candidate should become a separate scenario only when its failure condition and evidence boundary can be stated independently.

## Claim boundary

This corpus does not establish that ACE Direct was defective, that its workarounds were unnecessary, that current JsSIP or JAIN SIP reproduces the same behavior, or that a passing Baudot scenario establishes SIP, WebRTC, RFC 4103, T.140, VRS, or accessibility conformance.

It establishes a disciplined path for turning real production interoperability history into reproducible tests.
