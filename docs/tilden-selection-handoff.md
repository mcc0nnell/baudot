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

## TILDEN-HANDOFF-001: signaling

`TILDEN-HANDOFF-001` is the first executable consumer boundary.

`org.mcc0nnell.baudot.harness.TildenSipCallMain` consumes the selection directly, uses the exact selected SIP URI as the INVITE request URI, and carries `selectionId` into Baudot evidence as the correlation id.

The current executable profile is intentionally narrow: it supports non-secure SIP over UDP so the route-to-runtime boundary can be exercised deterministically in CI. TLS, WebRTC, media capability enforcement, and other transports require later profiles rather than silent fallback.

Run it with:

```bash
bash scripts/run-tilden-selection-adapter.sh
```

The CI lane requires:

```text
tilden.selection.id=sel-local-0001
tilden.selected.endpoint=sip:callee@127.0.0.1:5088;transport=udp
signaling.dialog.established=true
runtime.claim=selected-route-signaling-only
```

A contradictory selection whose selected candidate does not match `selectedEndpoint` must fail before signaling begins.

## TILDEN-HANDOFF-002: RTT readiness

`TILDEN-HANDOFF-002` extends the handoff through Baudot's existing RTT evidence chain instead of inventing a second definition of readiness.

```text
TildenSelection(sel-rtt-...)
        |
        v
BaudotRoute
        |
        v
canonical selected SIP/UDP route
        |
        v
live JAIN SIP offer/answer
        |
        v
RTP T.140 + RFC 2198 RED datagrams
        |
        v
preserved sender/receiver wire evidence
        |
        v
baudot-python-reference
        |
        v
selected-route-rtt-ready
```

The profile uses `prepare_tilden_rtt_route.py` to map one narrow canonical selected URI shape into the established RTT harness:

```text
sip:callee@HOST:PORT;transport=udp
```

Any different user, missing port, SIPS URI, non-UDP transport, or additional unsupported URI shape fails closed rather than being rewritten into something the harness happens to understand.

The live run uses `selectionId` as the Baudot correlation id, negotiates the existing RFC 4103/RED/T.140 profile, preserves the actual SDP and datagrams, and then invokes `scripts.validate_wiretap_rtt`.

That independent reference validator must establish all of the following before the handoff reducer can pass:

- the sent and received RTT datagrams are byte-identical;
- the SDP carries the exercised `m=text` profile;
- the direct T.140 and RED payloads parse under the existing reference implementation;
- the resulting baseline T.140 presentation is `Hi`;
- no missing-text marker is introduced; and
- the RTT evidence verdict is `pass` with `validationAuthority=baudot-python-reference`.

Only after those checks does `validate_tilden_rtt_handoff.py` emit:

```text
runtimeClaim=selected-route-rtt-ready
```

Run the complete lane with:

```bash
bash scripts/run-tilden-rtt-handoff.sh
```

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

`TILDEN-HANDOFF-002` adds one stronger claim: for the exercised canonical SIP/UDP profile, the selected route established a live session whose preserved RTT transport evidence was independently reduced to a valid exercised RFC 4103/RFC 2198/T.140 presentation.

Neither profile establishes Tilden network deployment, provider interoperability in production, full SIP/RFC 4103/T.140 conformance, video/sign-language media success, relay behavior, TLS/SIPS support, WebRTC support, end-to-end encryption, or end-to-end accessibility conformance. Those remain separate evidence claims.
