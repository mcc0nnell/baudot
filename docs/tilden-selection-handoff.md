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
TildenSelectionAdapter
        |
        v
BaudotRoute
  |- selectionId
  |- target
  |- selectedEndpoint
  |- resolutionDigest
  `- requestDigest
        |
        v
Baudot runtime / SIP / WebRTC / RTT / media
        |
        v
session-level interoperability evidence
```

A successful `TildenSelection` means only that a route was deterministically selected from validated inputs. It does **not** mean that SIP, WebRTC, RTT, media, encryption, transfer, or relay interoperability has succeeded.

## Implemented adapter

`TILDEN-HANDOFF-001` is the first executable consumer boundary.

`org.mcc0nnell.baudot.tilden.TildenSelectionAdapter` accepts Draft 0.1 selection JSON and rejects the handoff unless:

- `version` is `0.1`;
- `terminal` is `selected`;
- required correlation fields are present;
- exactly one candidate has outcome `selected`; and
- that candidate URI exactly matches `selectedEndpoint`.

The adapter emits a smaller `BaudotRoute` rather than copying the complete Tilden selection or ephemeral request into runtime state.

## Live SIP lane

`org.mcc0nnell.baudot.harness.TildenSipCallMain` consumes the selection directly, uses the exact selected SIP URI as the INVITE request URI, and carries `selectionId` into Baudot evidence as the correlation id.

The current executable profile is intentionally narrow: it supports non-secure SIP over UDP so the route-to-runtime boundary can be exercised deterministically in CI. TLS, WebRTC, media capability enforcement, and other transports require later profiles rather than silent fallback.

Run it with:

```bash
bash scripts/run-tilden-selection-adapter.sh
```

The CI lane starts a local Baudot SIP callee, adapts a deterministic Tilden selection, launches the selected URI, and requires:

```text
tilden.selection.id=sel-local-0001
tilden.selected.endpoint=sip:callee@127.0.0.1:5088;transport=udp
signaling.dialog.established=true
runtime.claim=selected-route-signaling-only
```

A contradictory selection whose selected candidate does not match `selectedEndpoint` must fail before signaling begins.

## Evidence correlation

`selectionId` survives into Baudot evidence so route selection and runtime behavior can be joined without copying private caller preference data into every artifact.

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

This keeps two questions independently answerable:

1. **Why was this endpoint selected?** — Tilden evidence.
2. **Did the selected systems actually interoperate?** — Baudot evidence.

## Claim boundary

`TILDEN-HANDOFF-001` proves only that Baudot can validate one Tilden selection, preserve its correlation identity, use the selected UDP SIP URI as the live signaling target, and record whether that dialog was established.

It does not establish Tilden network deployment, provider interoperability, RTT readiness, video/sign-language media success, relay behavior, TLS support, WebRTC support, or end-to-end accessibility conformance. Those remain separate evidence claims.
