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
