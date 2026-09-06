---
title: Baudot
description: An open proving ground for accessible real-time communications interoperability.
template: splash
hero:
  title: Accessible communications, proven by evidence.
  tagline: Baudot specifies behavior before implementation and preserves the evidence needed to distinguish a connected call from a usable one.
  actions:
    - text: Explore scenarios
      link: /baudot/scenarios/
      icon: right-arrow
    - text: View source
      link: https://github.com/mcc0nnell/baudot
      icon: external
      variant: minimal
---

## One boundary, many implementations

Baudot starts with portable accessibility behavior and then tests implementations against it. SIP stacks, WebRTC runtimes, gateways, network substrates, and external media implementations can supply evidence. They do not get to redefine the claim.

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
      ├── WebRTC / application adapters
      └── external implementation oracles
                │
                ▼
         preserved evidence
                │
                ▼
        independent reducers
```

## The core invariant

**Signaling success is not accessibility readiness.** Baudot keeps these observations separate:

| Layer | Example question |
| --- | --- |
| signaling | Did the dialog or transfer establish? |
| negotiation | Was the accessible modality negotiated? |
| transport | Did media or text reach the observation boundary? |
| presentation | Was it decoded and made usable? |
| readiness | Is the replacement or active leg actually safe to rely on? |

A scenario earns only the claim supported by its preserved evidence.

## Current proving ground

Baudot already has runnable scenarios around re-INVITE correlation, stale SDP, RFC 4103/T.140 readiness, and REFER handoff continuity. JAIN SIP is used as a glass-box signaling instrument; independent stacks and reference reducers are added where agreement or native media evidence strengthens the experiment.

The project is independent, open source in development, and does not claim general SIP, RFC 4103, T.140, VRS, gateway, or provider conformance.
