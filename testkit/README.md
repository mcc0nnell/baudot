# Baudot Testkit

The Baudot testkit expresses accessible real-time communications behavior as portable scenarios and observations before binding that behavior to a particular SIP, WebRTC, gateway, or application implementation.

## Boundary

The testkit separates:

```text
scenario intent
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

An adapter may execute effects and report observations. It may not silently redefine the scenario, assertion set, or conformance claim.

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

It is **not yet an RFC 4103 or T.140 conformance rule**. Normative T.140 vectors will define the semantics required to make that claim.

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
