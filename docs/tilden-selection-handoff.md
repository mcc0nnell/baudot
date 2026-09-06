# Tilden selection handoff

Baudot and Tilden have separate responsibilities.

- **Tilden** resolves an accessible identity, applies one call's ephemeral capability requirements, and emits deterministic endpoint-selection evidence.
- **Baudot** takes the selected route and determines whether independently implemented systems can actually establish a usable accessible session.

The dependency direction is intentionally one-way:

```text
Tilden contracts ---> Baudot consumer/integration
Tilden runtime  -X-> Baudot internals
```

Baudot must not become a prerequisite for implementing Tilden, and Tilden must not encode Baudot-specific signaling state.

## Handoff shape

The intended boundary is:

```text
human-reachable identifier
        |
        v
Tilden discovery + trust
        |
        v
TildenResolution
        +
TildenRequest (ephemeral, caller-side)
        |
        v
TildenSelection
  |- selectionId
  |- selectedEndpoint
  |- resolutionDigest
  |- requestDigest
  |- candidate outcomes
  `- terminal result
        |
        v
Baudot policy gate
        |
        v
SIP / WebRTC / RTT / video / relay adapters
        |
        v
session-level interoperability evidence
```

A successful `TildenSelection` means only that a route was deterministically selected from the validated inputs. It does **not** mean that SIP, WebRTC, RTT, media, encryption, transfer, or relay interoperability has succeeded.

## Minimum Baudot inputs

A future Baudot Tilden adapter should consume at least:

- `selectedEndpoint`;
- `selectionId` for evidence correlation;
- the validated `TildenResolution` or the runtime-relevant subset of it;
- only the request constraints still necessary for session policy or negotiation.

The full `TildenRequest` should remain caller-side unless a later Tilden profile explicitly permits disclosure.

## Evidence correlation

`selectionId` should survive into Baudot evidence so route selection and runtime behavior can be joined without copying private caller preference data into every artifact.

```text
TildenSelection(sel-...)
        |
        v
Baudot session attempt
        |
        +-- signaling evidence
        +-- media evidence
        +-- RTT readiness evidence
        +-- transfer/fallback evidence
        `-- terminal interoperability result
```

This makes it possible to answer two different questions independently:

1. **Why was this endpoint selected?** — Tilden evidence.
2. **Did the selected systems actually interoperate?** — Baudot evidence.

## Reference executable

Tilden's current reference CLI exercises the handoff locally:

```text
tilden resolve ...  -> TildenResolution
tilden request ...  -> TildenRequest
tilden select ...   -> TildenSelection
tilden explain ...  -> human-readable routing evidence
```

A future Baudot integration may expose an interface shaped like:

```text
baudot call --selection selection.json
```

That command is an architectural target, not a claim that Baudot implements this exact CLI today.

## Claim boundary

Until a concrete adapter lands, Baudot does not claim native Tilden integration. This document fixes the intended project boundary so implementation can proceed without coupling the two specifications incorrectly.
