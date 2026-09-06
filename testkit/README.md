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

This is deliberately stricter than inferring RTT readiness from successful SIP, WebRTC, video, or audio state.

It is **not by itself an RFC 4103 or T.140 conformance rule**.

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

The suite is deliberately marked `baseline`, not `conformant`. It does not yet settle grapheme-cluster deletion, optional presentation controls, RTP T140blocks, RFC 2198 redundancy, packet-loss recovery, SIP negotiation, or WebRTC data-channel carriage.

The source hierarchy for this layer is:

1. ITU-T T.140 for presentation semantics;
2. ITU-T T.140 Addendum 1 for the missing-text marker; and
3. RFC 4103 only where it clarifies the boundary between T.140 content and RTP transport.

That ordering matters: transport adapters will eventually have to satisfy the T.140 vectors rather than redefine them.

## iTRS mock proving ground

`itrs/` contains a deterministic, clean-room iTRS routing mock suite. It covers direct and aliased `E2U+sip` resolution, NAPTR priority, SIP service discovery, negative responses, authority outage, and latency without requiring live TRS Numbering Directory access.

The executable handoff trial keeps the iTRS-derived logical SIP URI as the SIP Request-URI while JAIN-SIP routes the packet to a separate loopback mock VRS peer. This is the first testkit proof of the Tilden/Baudot rule:

> Resolve the logical route first. Connect second.

The trial proves local route consumption and SIP transaction behavior only. It does not claim live iTRS access or production VRS interoperability.

The clean-room fixture validator also recomputes ENUM owner derivation, alias traversal, NAPTR order/preference selection, `E2U+sip` validation, and synthetic SIP NAPTR/SRV discovery from fixture data rather than trusting canned expected output.

## Scenario status

Scenarios may be:

- `planned` — behavior and evidence requirements are specified, but no executable proof exists;
- `runnable` — at least one adapter can execute the scenario;
- `proven` — declared evidence has been produced and verified by the project; or
- `regressed` — previously proven behavior is known to diverge.

Documentation alone cannot promote a scenario to `proven`.

## Evidence discipline

The testkit is deliberately implementation-independent. A reference adapter can produce observations, but it does not become normative merely because it runs first or is maintained in this repository.

A mature testkit claim should be reviewable as:

```text
portable scenario
    -> implementation A
    -> implementation B
    -> preserved observations
    -> independent reducer
    -> same bounded claim
```

Claim boundaries travel with the scenario. A green signaling test does not become a media-readiness claim; a route result does not become proof of transport success; implementation agreement does not become correctness by majority vote.

The broader project model, including clean-room donor discipline and the informal **Apache-style proof** framing, is documented in [`../docs/evidence-and-governance.md`](../docs/evidence-and-governance.md).

## ACE Omni integration

ACE Omni is the first research runner targeted by this contract. Omni owns controlled experiment execution and evidence collection. Baudot owns the portable accessibility behavior and test vocabulary.

Historical ACE Direct behavior may motivate scenarios, but donor code and old workarounds are not treated as proof of a current implementation defect.
