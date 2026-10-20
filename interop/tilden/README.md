# Tilden selection adapter

Baudot consumes Tilden as an external routing contract. This directory contains deterministic fixtures for the first executable adapter.

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

Run the executable check with:

```bash
bash scripts/run-tilden-selection-adapter.sh
```

This adapter does not claim that a selected endpoint is interoperable. It validates the routing handoff only; SIP/WebRTC/RTT/media evidence remains a Baudot responsibility.
