# PJSIP native RTT media lane

Baudot uses PJSIP/PJPROJECT here as an **external native-media oracle**, not as a replacement for the JAIN SIP glass-box signaling harness or the Elixip SIP/call-state oracle.

See [ADR-0002](../../docs/adr/0002-pjsip-native-rtt-media-oracle.md).

## Pinned identity

```text
repository: pjsip/pjproject
release:    2.17
commit:     5a457451fa2712ba18e12b01738e8ff3af2b26fd
```

The checkout must be exact and clean.

## First qualification

The initial lane asks PJSIP to generate RTT through its own media stack:

```text
Baudot-owned PJSUA2 driver
        |
        +-- textCount = 1
        +-- audioCount = 0
        +-- videoCount = 0
        v
PJSIP / PJSUA2 / PJMEDIA 2.17
        |
        +-- SIP INVITE with text media
        v
Baudot JAIN SIP UAS
        |
        +-- selects direct PT 98 t140/1000
        +-- confirms dialog
        v
PJSIP Call::sendText("H")
        |
        v
PJMEDIA native text stream
        |
        +-- UDP/RTP bytes on the wire
        v
Baudot datagram evidence
        |
        v
Python RFC 4103/T.140 reference
        `-- first non-empty text must be "H"
```

Java records signaling facts and raw datagram receipt but deliberately leaves `firstT140CharacterObserved` and `rttReady` as `UNCLASSIFIED_BY_JAVA`.

`scripts.validate_pjsip_native_t140` owns the terminal semantic reduction.

## Running locally

With a clean PJSIP 2.17 checkout at the pinned commit:

```bash
PJSIP_ROOT=/path/to/pjproject \
  bash scripts/run-pjsip-native-t140.sh
```

The runner builds PJSIP and the small qualification executable ephemerally, starts the JAIN receiver, executes the native text send, independently validates the preserved packet(s), and creates an outer SHA-256 evidence bundle.

The linked PJSIP qualification executable is not uploaded as a Baudot evidence artifact. Only its hash, build metadata, process logs, SIP evidence, wire evidence, and reducers are preserved.

## Claim boundary

A passing run means that the exact pinned PJSIP 2.17 implementation generated wire traffic through its native PJSUA2/PJMEDIA text path that Baudot independently reduced to the expected T.140 text under the controlled direct-PT98 profile.

It does **not** establish SIP, RTP, RFC 4103, RFC 2198, T.140, PJSIP, JAIN SIP, VRS, SBC/NAT, or production conformance.

The next threshold is to use this qualified PJSIP native-media path as the replacement-leg RTT producer in `BAUDOT-INTEROP-004`, replacing the current Baudot-owned canonical positive stimulus without changing the transfer reducer semantics.
