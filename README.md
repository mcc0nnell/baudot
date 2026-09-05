# Baudot

**Protocol interoperability and evidence-oriented proving for accessible real-time communications.**

Baudot is an experimental interoperability layer and test harness for accessible real-time communications. It focuses on proving protocol behavior at the seams between SIP, RTT, WebRTC, relay systems, gateways, and future communications services without collapsing identity, routing, signaling, media, and accessibility state into one stack.

## Architectural boundary

Baudot consumes routing decisions; it does not own durable communications identity.

**Tilden answers:** Where and how should this communications identity be reached?

**Baudot answers:** How do the selected communications systems interoperate?

That boundary can be summarized as:

> Resolve first. Connect second.

Tilden may return a logical SIP route, WebRTC route, RTT route, VRS route, or another supported endpoint. Baudot then performs the protocol work needed to establish or bridge the selected communication.

## Current proving ground

The repository is intentionally evidence-oriented. The harness separates signaling success, media reachability, RTT readiness, transport behavior, and rendered or decoded output rather than treating a single `connected` flag as proof.

Current work includes:

- JAIN-SIP signaling probes;
- SIP re-INVITE and REFER experiments;
- RTT/T.140 and RFC 4103 vectors;
- RFC 2198 redundancy and recovery tests;
- WebRTC data-channel accessibility vectors;
- cross-transport gateway contracts;
- Wiretap-based fault and recovery labs; and
- deterministic iTRS routing mocks.

## iTRS mock vertical slice

`testkit/itrs/` provides a clean-room, local-only mock of fielded iTRS-style routing behavior. It contains no live TRS Numbering Directory credentials, subscriber data, or production provider configuration.

The first executable handoff is:

```text
synthetic NANP number
       |
       v
mock iTRS resolution
       |
       v
logical SIP URI
       |
       v
JAIN-SIP INVITE
       |
       v
mock VRS peer
       |
       +--> 200 OK
       +--> ACK
```

The trial deliberately preserves the iTRS-derived logical SIP URI as the SIP Request-URI while using separate transport routing to reach the loopback peer. This proves the distinction between an authoritative communications route and the immediate network destination used to connect it.

Run the fixture matrix:

```bash
bash scripts/run-itrs-mocks.sh
```

Run the SIP handoff proof:

```bash
bash scripts/run-itrs-sip-handoff.sh
```

These are test fixtures, not production iTRS interfaces or provider-interoperability certifications.

## Project posture

Baudot favors small, deterministic, reproducible probes that produce evidence about a specific interoperability claim. Historical systems such as ACE Direct may provide behavioral prior art, but donor code and historical workarounds are not treated as current proof.

The long-term goal is a federated accessible-calling proving ground where protocol and accessibility behavior can be tested independently, composed deliberately, and subjected to repeatable failure conditions before production integration.
