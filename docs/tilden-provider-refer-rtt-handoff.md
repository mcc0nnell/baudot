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

## Acceptance evidence

The first dedicated `tilden-provider-refer-rtt-handoff` run passed on Baudot head `9a106ca6c22e21237c1d056641c72eca00de284e` (Actions run `34000704284`).

The outer evidence proved:

- Tilden selection `sel-provider-refer-rtt-0001` selected `sip:provider-a@127.0.0.1:5310`;
- the nested provider flow began with exact request line `INVITE sip:provider-a@127.0.0.1:5310 SIP/2.0`;
- `BAUDOT-INTEROP-004` correlation `jain-to-pjsip-native-handoff-v1` remained `PASS`;
- REFER was accepted;
- the pinned PJSIP replacement dialog established;
- the independent Baudot reference classified replacement `rttReady=true` from first T.140 text `H`;
- the original provider leg released only after independent readiness; and
- the outer terminal verdict was `ready-after-transfer` with all six required facts true.

Pinned evidence identities from that run:

- Tilden selection SHA-256: `a203a194ee5be855d5252ffdabbfb94f9da63b2b125417fdbd88e4cbd656dd45`;
- inner terminal SHA-256: `42c041ef79a8dd333e247f4c64667db16a7f8833ce14b8f7712dbe61d6f69668`;
- inner bundle-manifest SHA-256: `c82bb92a5db7b970a51e36d0f8b90ec1bb3e01a9f1d34c5f9459379a09843f4b`;
- qualifying native T.140 packet SHA-256: `d8d7411c59f54385d2809ce952ec27d47756efd9dd9ff3bfd1c8f2f60512651d`;
- outer bundle-manifest SHA-256: `3ad60282698b3f1351dcb8b94e63cfb36d2e90679fca2d1e2d370e0e47e2c6b0`;
- Actions artifact id: `9979436293`; and
- artifact ZIP digest: `sha256:b1367e07e5efe8fdd871909fb789cb502208ff0577a9b074890caf6d8a3d0a2e`.

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
