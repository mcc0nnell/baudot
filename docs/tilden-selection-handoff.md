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

`org.mcc0nnell.baudot.tilden.TildenSelectionAdapter` accepts Draft 0.1 selection JSON and rejects the handoff unless:

- `version` is `0.1`;
- `terminal` is `selected`;
- required correlation fields are present;
- exactly one candidate has outcome `selected`; and
- that candidate URI exactly matches `selectedEndpoint`.

The adapter emits a smaller `BaudotRoute` rather than copying the complete Tilden selection or ephemeral request into runtime state.

## TILDEN-HANDOFF-001 — selected route to SIP signaling

`org.mcc0nnell.baudot.harness.TildenSipCallMain` consumes the selection directly, uses the exact selected SIP URI as the INVITE Request-URI, and carries `selectionId` into Baudot evidence as the correlation id.

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

## TILDEN-HANDOFF-002 — selected route to native RTT readiness

The second lane composes the same accepted handoff with Baudot's already-qualified PJSIP/PJMEDIA 2.17 native T.140 endpoint and live independent readiness gate.

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
PJSIP 2.17 incoming native-text endpoint
        |
        v
PJSUA2 / PJMEDIA native T.140 wire traffic
        |
        v
Baudot Python RFC 4103/T.140 reference
        |
        v
atomic rttReady token
        |
        v
JAIN caller releases selected dialog only after token
```

Run it with:

```bash
PJSIP_ROOT=/path/to/pjproject-2.17 \
  bash scripts/run-tilden-pjsip-rtt-handoff.sh
```

The selected endpoint remains a Tilden routing fact. It does not become evidence that RTT is usable. The responsibilities are deliberately split:

- **Tilden selection evidence** owns why `selectedEndpoint` won;
- **JAIN SIP** owns the controlled INVITE/dialog/BYE observations;
- **PJSIP/PJMEDIA 2.17** owns native endpoint and media generation behavior;
- **Baudot's Python RFC 4103/T.140 reference** alone may publish `rttReady=true`; and
- **the terminal reducer** correlates those evidence planes into the bounded `TILDEN-HANDOFF-002` verdict.

The terminal reducer requires the exact selected endpoint to appear as the SIP Request-URI, a T.140 answer, a positive independent readiness token, and release after readiness. Java records the readiness token as opaque external authority evidence rather than reclassifying its contents.

### Acceptance evidence

The dedicated `tilden-pjsip-rtt-handoff` workflow passed end-to-end on 2026-09-05/06 at Baudot head `2b7ec5d9169f973a9fdd34078434b4b690c828f9` (Actions run `34000399709`).

The passing run preserved:

- `selectionId=sel-pjsip-rtt-0001`;
- exact selected Request-URI `sip:pjsip-target@127.0.0.1:5322;transport=udp`;
- exact clean `pjsip/pjproject` 2.17 checkout at `5a457451fa2712ba18e12b01738e8ff3af2b26fd`;
- native PJSIP text media active before `Call::sendText("H")`;
- one qualifying direct PT98 T.140 packet with SHA-256 `d9747db76b980c817f1641c93747a252d50d5e9c723ba58b73fb1db652d58963`;
- independent Baudot reference result `rttReady=true` with first T.140 text `H`;
- JAIN's opaque observation `rttReady=EXTERNAL_BAUDOT_REFERENCE_TOKEN`;
- BYE sent only after the readiness token and acknowledged with 200 OK; and
- terminal verdict `ready` with all seven declared facts true.

The outer evidence-manifest file has SHA-256 `6a1d0276156ad672c9eed942e75c63dfcb44c5f27cd60896afe38e3096069912`. The preserved Actions artifact is `9979329402`, with ZIP digest `sha256:9cb231fe914c26ebf588b807a88b1edf5fd5c229a1b221a3fdf44cb5766c99f1`.

The first instrumented attempt exposed a process-lifetime problem only after the SIP, RTT, and BYE evidence had completed: JAIN implementation worker threads kept Maven's exec process alive. The final profile uses `TildenPjsipRttProcessMain` solely as an explicit process boundary after the evidence-producing call main returns. It has no signaling, media, readiness, routing, or verdict authority.

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

`TILDEN-HANDOFF-002` adds a controlled observation that the exact selected PJSIP endpoint negotiated native T.140, produced wire traffic accepted by Baudot's independent readiness reference, and was released only after that readiness evidence appeared.

Neither lane establishes Tilden network deployment, provider interoperability, SIP/RTP/RFC 4103/T.140/PJSIP conformance, video/sign-language media success, relay behavior, TLS support, WebRTC support, or end-to-end accessibility conformance. Those remain separate evidence claims.
