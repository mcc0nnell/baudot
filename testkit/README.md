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

## Scenario status

Scenarios may be:

- `planned` — behavior and evidence requirements are specified, but no executable proof exists;
- `runnable` — at least one adapter can execute the scenario;
- `proven` — declared evidence has been produced and verified by the project; or
- `regressed` — previously proven behavior is known to diverge.

Documentation alone cannot promote a scenario to `proven`.

## ACE Omni integration

ACE Omni is the first research runner targeted by this contract. The integration is a bridge between two independent authorities rather than a merge of their models:

```text
Baudot scenario / vectors / assertions
              │
              ▼
      Omni communications adapter
              │
              ▼
        attached runtime
              │
              ▼
     source-identified facts
              │
              ▼
       Omni evidence ledger
              │
              ▼
      Baudot terminal reducer
```

**Baudot owns portable accessibility behavior, readiness vocabulary, scenario assertions, claim scope, and terminal reduction. ACE Omni owns controlled run identity, deterministic execution planning, command sequencing, authoritative observation-envelope/evidence handling, replay, and export. Attached runtimes own external effects.**

The first machine-readable bridge protocol is [`bridges/omni-emulytics-bridge-v1.json`](bridges/omni-emulytics-bridge-v1.json). The architectural decision and authority boundary are documented in [`ADR-0002`](../docs/adr/0002-ace-omni-experiment-evidence-bridge.md).

A command remains intent, not evidence. For example, an Omni command requesting a REFER cannot itself establish `referAccepted=true`; that fact must come from an identified observation source. Likewise, successful signaling or RTT negotiation does not imply `rttReady=true` unless the active Baudot scenario's evidence rule is satisfied.

Execution through ACE Omni does **not** promote a Baudot scenario to `proven`. Existing evidence requirements and `requiredBeforeProven` conditions remain authoritative for the Baudot claim.

Historical ACE Direct behavior may motivate scenarios, but donor code and old workarounds are not treated as proof of a current implementation defect.
