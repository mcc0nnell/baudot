# Tilden selection adapter

Baudot consumes Tilden as an external routing contract. This directory contains deterministic fixtures for the executable Tilden-to-Baudot handoff profiles.

The adapter accepts a successful `TildenSelection`, validates the handoff invariants, and emits the smaller runtime-facing `BaudotRoute` object:

```text
TildenSelection
  |- selectionId
  |- target
  |- selectedEndpoint
  |- resolutionDigest
  |- requestDigest
  `- candidate outcomes
        |
        v
TildenSelectionAdapter
        |
        v
BaudotRoute
  |- selectionId
  |- target
  |- selectedEndpoint
  |- resolutionDigest
  `- requestDigest
```

The full Tilden request and candidate evidence do not become Baudot runtime state. `selectionId` survives so session evidence can be correlated back to the routing decision.

## TILDEN-HANDOFF-001

Run:

```bash
bash scripts/run-tilden-selection-adapter.sh
```

This profile proves the basic routing handoff: Baudot validates a successful selection, uses the selected SIP/UDP URI as the live signaling target, establishes a dialog, and preserves `selectionId` in runtime evidence.

Its terminal claim is:

```text
selected-route-signaling-only
```

## TILDEN-HANDOFF-002

Run:

```bash
bash scripts/run-tilden-rtt-handoff.sh
```

This profile advances the same evidence chain through the existing Baudot RTT proof path:

```text
TildenSelection
      |
      v
BaudotRoute
      |
      v
canonical selected SIP/UDP runtime route
      |
      v
live SIP + RFC 4103/RED/T.140 exercise
      |
      v
preserved wire datagrams + SDP
      |
      v
baudot-python-reference
      |
      v
selected-route-rtt-ready
```

`prepare_tilden_rtt_route.py` accepts only the narrow canonical URI profile currently exercised by the harness: `sip:callee@HOST:PORT;transport=udp`. It fails closed for other URI shapes or transports rather than silently changing the route.

The selected route is correlated by `selectionId`. After the live run, `validate_wiretap_rtt.py` independently validates the preserved SDP and RTP/RED/T.140 bytes. Only then may `validate_tilden_rtt_handoff.py` emit `runtimeClaim: selected-route-rtt-ready`.

The RTT handoff profile does **not** claim full SIP, RFC 4103, or T.140 conformance, and it does not establish TLS/SIPS, WebRTC, video, relay, E2EE, or production-network interoperability.

## Boundary

A Tilden selection is routing evidence, not proof that a selected endpoint is usable. Baudot owns the runtime evidence needed to make progressively stronger claims about the selected route.
