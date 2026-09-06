# Tilden-selected provider REFER to native RTT

`TILDEN-HANDOFF-003` composes Tilden route selection with Baudot's existing `BAUDOT-INTEROP-004` native REFER handoff without duplicating either authority.

## Purpose

The previous handoff slices establish two smaller facts:

- `TILDEN-HANDOFF-001`: a selected Tilden URI becomes the live SIP Request-URI;
- `TILDEN-HANDOFF-002`: a selected native PJSIP endpoint can reach independently classified RTT readiness.

`TILDEN-HANDOFF-003` moves the selected route one level earlier in a VRS-shaped transfer flow. Tilden selects the provider/referrer endpoint. Baudot then exercises that selected provider through the already-qualified REFER → replacement → native RTT path.

```text
TildenSelection
  selectedEndpoint = provider-a
          |
          v
BaudotRoute
          |
          v
exact original INVITE Request-URI
          |
          v
provider-a / JAIN SIP
          |
        REFER
          |
          v
pinned PJSIP 2.17 replacement
          |
          v
native PJMEDIA T.140
          |
          v
Baudot RFC 4103/T.140 reference
          |
       rttReady
          |
          v
old provider leg released
```

## Composition rule

The outer Tilden scenario does not reimplement transfer semantics. `scripts/run-tilden-provider-refer-rtt-handoff.sh`:

1. validates and reduces the Tilden selection into `BaudotRoute`;
2. requires the selected provider profile to be `sip:provider-a@127.0.0.1:5310`;
3. runs the existing `scripts/run-pjsip-interop004-native-handoff.sh` unchanged under a nested evidence root;
4. verifies that the inner `original-invite.request.sip` Request-URI exactly equals the Tilden `selectedEndpoint`;
5. requires the existing `BAUDOT-INTEROP-004` terminal result to remain `PASS`; and
6. emits a separate `TILDEN-HANDOFF-003` terminal result that binds route selection to the inner transfer evidence by digest.

The inner scenario remains the authority for REFER acceptance, replacement establishment, native PJSIP media observation, independent RTT readiness, and old-leg release ordering.

## Required terminal facts

The outer reducer requires:

```text
routeSelectionPreserved=true
selectedProviderUsedAsOriginalRequestUri=true
referAccepted=true
replacementDialogEstablished=true
replacementRttReady=true
oldLegReleasedAfterIndependentReadiness=true
```

The terminal verdict is `ready-after-transfer` only when all six facts are present.

## Evidence identity

The outer terminal result preserves:

- Tilden `selectionId`;
- selected provider URI;
- SHA-256 of the Tilden selection fixture;
- inner `BAUDOT-INTEROP-004` correlation ID;
- SHA-256 of the inner terminal result;
- SHA-256 of the inner bundle-manifest file; and
- SHA-256 of the native T.140 packet that caused the independent readiness classification.

This lets a later evidence consumer answer both questions without merging the models:

1. **Why was this provider selected?** — Tilden selection evidence.
2. **Did that selected provider successfully hand the call to an RTT-ready replacement?** — Baudot interoperability evidence.

## Authority boundary

- **Tilden** owns provider selection.
- **Baudot JAIN SIP** owns the controlled provider and REFER signaling observations.
- **PJSIP/PJMEDIA 2.17** owns replacement native-media behavior.
- **Baudot's Python RFC 4103/T.140 reference** alone owns positive `rttReady` classification.
- **`BAUDOT-INTEROP-004`** owns the transfer/readiness/release terminal reduction.
- **`TILDEN-HANDOFF-003`** only joins the selected provider identity to that already-qualified inner result.

## Claim boundary

This is a controlled route-to-transfer interoperability observation. It does not establish Tilden deployment, production provider routing, SIP/RTP/RFC 4103/T.140/PJSIP conformance, VRS provider conformance, numbering authority, relay-service behavior, TLS/WebRTC support, or production accessibility readiness.
