# Tilden selection adapter

Baudot consumes Tilden as an external routing contract. This directory contains deterministic fixtures for the executable adapter and handoff lanes.

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

## TILDEN-HANDOFF-001: selected route to signaling

Run the signaling-only handoff with:

```bash
bash scripts/run-tilden-selection-adapter.sh
```

The selected URI becomes the actual SIP Request-URI. A contradictory selected candidate / `selectedEndpoint` pair is rejected before signaling.

This lane proves only the route-to-signaling boundary. It does not infer media or accessibility readiness from a successful SIP dialog.

## TILDEN-HANDOFF-002: selected route to native RTT readiness

`selection.pjsip-rtt.json` selects the exact pinned PJSIP/PJMEDIA 2.17 incoming endpoint used by the next handoff profile.

Run it with a clean exact PJSIP 2.17 checkout:

```bash
PJSIP_ROOT=/path/to/pjproject-2.17 \
  bash scripts/run-tilden-pjsip-rtt-handoff.sh
```

The evidence chain is:

```text
TildenSelection
    |
    v
BaudotRoute
    |
    v
exact selected SIP Request-URI
    |
    v
PJSIP 2.17 native text endpoint
    |
    v
native PJMEDIA T.140 wire traffic
    |
    v
Baudot Python RFC 4103/T.140 reference
    |
    v
rttReady token
    |
    v
release only after readiness
```

The selected endpoint is routing evidence, not readiness evidence. PJSIP owns native call/media behavior, JAIN SIP owns controlled signaling, and the Baudot Python reference gate alone owns the positive `rttReady` classification.

`selectionId` is preserved across the route, SIP, readiness, and terminal evidence so Tilden's routing decision and Baudot's interoperability result can be joined without copying the caller's full ephemeral request into runtime state.

Neither handoff profile claims Tilden, SIP, RTP, RFC 4103, T.140, PJSIP, VRS, or end-to-end accessibility conformance.
