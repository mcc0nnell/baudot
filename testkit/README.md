# Baudot Testkit

The Baudot testkit expresses accessible real-time communications behavior as portable scenarios, vectors, and observations before binding that behavior to a particular SIP, WebRTC, gateway, or application implementation.

## Boundary

The testkit separates:

```text
scenario intent / protocol vector
            │
            ▼
      execution adapter
            │
            ▼
        observations
            │
            ▼
         assertions
            │
            ▼
      evidence / verdict
```

An adapter may execute effects and report observations. It may not silently redefine the scenario, vector, assertion set, or conformance claim.

## Readiness vocabulary

A communications session is not represented by one Boolean `connected` state. The initial readiness contract preserves these observations independently:

- session establishment;
- PeerConnection signaling state;
- connection state;
- ICE state;
- selected candidate-pair state;
- inbound audio;
- inbound video;
- decoded video;
- rendered video;
- RTT negotiation; and
- first T.140 character.

Each derived readiness state is one of:

- `unknown`
- `pending`
- `ready`
- `failed`

The central invariant is:

```text
SESSION_ESTABLISHED
  != ICE_READY
  != VIDEO_DECODED
  != VIDEO_RENDERED
  != RTT_READY
```

## RTT rule

For the initial portable contract:

```text
RTT_READY = RTT_NEGOTIATED && FIRST_T140_CHARACTER_OBSERVED
```

This is deliberately stricter than inferring RTT readiness from successful SIP, WebRTC, video, audio, or receipt of an RTT packet alone.

The routed RFC 4103 primary fixture therefore reports `RTT_RECEIVED`, not `RTT_READY`, when a canonical `text/t140` RTP packet is observed without SDP RTT negotiation. This preserves transport evidence without weakening the readiness contract.

That readiness rule is **not by itself an RFC 4103 or T.140 conformance rule**.

## T.140 baseline vectors

`vectors/t140-presentation-v1.json` is the first standards-grounded presentation suite. The validator recomputes both the declared UTF-8 encoding and the expected presentation result rather than trusting fixture output.

The first baseline covers:

- IRV text;
- Latin-1 supplement text;
- `BEL` (`U+0007`);
- `BS` (`U+0008`);
- preferred new line via `LINE SEPARATOR` (`U+2028`);
- supported, non-preferred `CR LF` new line; and
- the T.140 Addendum 1 missing-text marker (`U+FFFD`).

The presentation suite is deliberately marked `baseline`, not `conformant`. It does not by itself settle grapheme-cluster deletion, optional presentation controls, RTP carriage, RFC 2198 redundancy, packet-loss recovery, SIP negotiation, or WebRTC data-channel carriage.

The source hierarchy for this layer is:

1. ITU-T T.140 for presentation semantics;
2. ITU-T T.140 Addendum 1 for the missing-text marker; and
3. RFC 4103 only where it clarifies the boundary between T.140 content and RTP transport.

That ordering matters: transport adapters must satisfy the T.140 vectors rather than redefine them.

## RFC 4103 primary RTP baseline

`rfc4103/primary-rtp-v1.json` defines the direct, non-redundant primary `text/t140` RTP boundary. It covers exact wire bytes for:

- ordinary primary text;
- the marker bit after idle;
- an empty primary T140block; and
- a multibyte UTF-8 T140block.

The Python reference implementation validates the RTP v2 fixed header, the 1000 Hz T.140 clock boundary, exact primary payload bytes, strict UTF-8 T140blocks, and serialize/parse round trips against the declared `packetHex` values.

The routed runtime harness consumes those canonical bytes rather than maintaining a second serializer. The receiver independently checks the observed RTP fields, T140block bytes, UTF-8 validity, and packet SHA-256 after transport through the Wiretap fixture.

That runtime proof is intentionally narrower than complete RFC 4103 interoperation. It does not yet establish:

- SDP `text/t140` negotiation;
- RFC 2198 redundancy;
- packet-loss recovery or reordering behavior;
- RTCP;
- buffering/timing profile behavior; or
- complete sender/receiver conformance.

RFC 2198 and deterministic recovery have their own testkit vectors and validators; binding those semantics to the routed runtime is a separate evidence step.

## Scenario status

Scenarios may be:

- `planned` — behavior and evidence requirements are specified, but no executable proof exists;
- `runnable` — at least one adapter can execute the scenario;
- `proven` — declared evidence has been produced and verified by the project; or
- `regressed` — previously proven behavior is known to diverge.

Documentation alone cannot promote a scenario to `proven`.

## ACE Omni integration

ACE Omni is the first research runner targeted by this contract. Omni owns controlled experiment execution and evidence collection. Baudot owns the portable accessibility behavior and test vocabulary.

Historical ACE Direct behavior may motivate scenarios, but donor code and old workarounds are not treated as proof of a current implementation defect.
