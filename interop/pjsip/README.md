# PJSIP native RTT media lane

Baudot uses PJSIP/PJPROJECT here as an **external native-media oracle**, not as a replacement for the JAIN SIP glass-box signaling harness or the Elixip SIP/call-state oracle.

See [ADR-0002](../../docs/adr/0002-pjsip-native-rtt-media-oracle.md), accepted on the initial native-media qualification evidence.

## Pinned identity

```text
repository: pjsip/pjproject
release:    2.17
commit:     5a457451fa2712ba18e12b01738e8ff3af2b26fd
```

The checkout must be exact and clean.

## Qualified native-media profile

The first lane asks PJSIP to generate RTT through its own media stack:

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
PJSIP reports native text media active
        |
        v
PJSIP Call::sendText("H")
        |
        v
PJMEDIA native text stream
        |
        +-- live RTP datagrams
        v
Baudot datagram evidence
        |
        v
Python RFC 4103/T.140 reference
        `-- first non-empty text = "H"
```

The passing qualification preserved two direct-PT98 datagrams. The first non-empty packet independently reduced to `H`; the second carried an empty T.140 block. The terminal reference result records `rttReady=true`.

Java records signaling facts and raw datagram receipt but deliberately leaves `firstT140CharacterObserved` and `rttReady` as `UNCLASSIFIED_BY_JAVA`. `scripts.validate_pjsip_native_t140` owns the terminal semantic reduction.

Both the native sender and JAIN observer have explicit external execution bounds. Implementation process lifetime cannot silently become evidence of readiness.

## Qualified incoming-endpoint profile

Before using PJSIP as a replacement target, Baudot separately qualifies the incoming role:

```text
JAIN SIP UAC
  -> direct PT 98 t140/1000 offer
  -> PJSIP 2.17 UAS answers
  -> dialog confirmed
  -> PJSIP native text media active
  -> PJSIP Call::sendText("H")
  -> live Baudot Python readiness gate
  -> atomic rttReady token
  -> JAIN preserves exact token as opaque authority evidence
  -> only then JAIN sends BYE
  -> PJSIP independently observes remote release
```

The live readiness gate, not JAIN or PJSIP, owns semantic classification. It preserves the implementation-generated packet, parses it with Baudot's RFC 4103/T.140 reference, and atomically publishes readiness only when the expected first non-empty text is observed.

`scripts.validate_pjsip_native_t140_uas` reconciles the PJSIP-side state markers, SIP offer/answer evidence, exact token bytes, qualifying packet hash, and release ordering.

## BAUDOT-INTEROP-004 native replacement arm

The qualified pieces are composed into a controlled positive handoff:

```text
original JAIN dialog
  -> REFER accepted
  -> NOTIFY progression
  -> replacement INVITE to pinned PJSIP 2.17 UAS
  -> replacement dialog established
  -> direct PT 98 t140/1000 negotiated
  -> PJSIP native text media active
  -> PJSIP Call::sendText("H")
  -> live Baudot Python readiness gate accepts native wire traffic
  -> atomic rttReady token
  -> JAIN consumes exact token without parsing media
  -> original-leg BYE only after readiness
```

This arm deliberately removes canonical whole-packet equality from the release decision. RTP sequence number, timestamp, and SSRC remain implementation-generated. The Java transfer harness does not own the `m=text` UDP socket and cannot set `rttReady=true` itself.

The PJSIP replacement endpoint is also required to remain alive through the transfer verdict. A separate post-verdict completion signal is used only to terminate the CI process after evidence closure; that signal is outside the readiness and old-leg release path.

`scripts.validate_pjsip_refer_native_handoff` requires the JAIN transfer facts, PJSIP native-media observations, live readiness token and packet hash, and old-leg release ordering to agree before emitting PASS.

## Running locally

With a clean PJSIP 2.17 checkout at the pinned commit:

```bash
PJSIP_ROOT=/path/to/pjproject \
  bash scripts/run-pjsip-native-t140.sh

PJSIP_ROOT=/path/to/pjproject \
  bash scripts/run-pjsip-native-t140-uas.sh

PJSIP_ROOT=/path/to/pjproject \
  bash scripts/run-pjsip-interop004-native-handoff.sh
```

The runners build only the required PJSUA2/PJMEDIA dependency closure and the small Baudot-owned drivers ephemerally. The linked PJSIP executables are not uploaded as Baudot evidence artifacts. Source identity, build metadata, process observations, SIP evidence, native wire evidence, independent reductions, and SHA-256 manifests are preserved instead.

## Claim boundary

The accepted PJSIP profiles establish controlled implementation observations only:

- the pinned PJSIP 2.17 stack generated native text media that Baudot independently reduced to the expected T.140 text;
- the same pinned stack answered an incoming direct-T.140 call and remained active until a readiness-gated release; and
- the same incoming native-media behavior participated as the replacement endpoint in one controlled JAIN-originated `BAUDOT-INTEROP-004` positive arm.

They do **not** establish SIP, RTP, REFER, RFC 4103, RFC 2198, T.140, PJSIP, JAIN SIP, VRS, SBC/NAT, or production conformance.

A useful next threshold is broader independent native-media coverage: add another implementation and/or qualify PJSIP RFC 2198/T.140 redundancy behavior without weakening the direct-T.140 evidence path.
