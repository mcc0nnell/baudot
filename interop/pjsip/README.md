# PJSIP native RTT media lane

Baudot uses PJSIP/PJPROJECT here as an **external native-media oracle**, not as a replacement for the JAIN SIP glass-box signaling harness or the Elixip SIP/call-state oracle.

See [ADR-0002](../../docs/adr/0002-pjsip-native-rtt-media-oracle.md), accepted on the initial native-media qualification evidence.

## Pinned direct-T.140 identity

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

## Native RFC 2198 characterization

RFC 2198/T.140 redundancy is deliberately a separate profile from the accepted direct-T.140 lane. The experiment requests PJSUA2 text redundancy level 2, negotiates PT100 `red/1000` plus PT98 `t140/1000`, sends ordinary `H` then `I` text through `Call::sendText()`, and preserves the PJMEDIA-generated packets without Java semantic classification.

The distinction under test is:

```text
RED negotiated
+ PT100 observed
!= recoverable RTT history
```

### Release 2.17 baseline

Exact release 2.17 at `5a457451fa2712ba18e12b01738e8ff3af2b26fd` negotiates the RED profile and emits PT100. In the controlled `H`/`I` observation, however, the preserved RED generations have zero-length historical payloads. The independent reducer therefore records:

```text
result=OBSERVED_LIMITATION
nativePjsipRfc2198PayloadObserved=true
zeroLengthRedundantGenerationObserved=true
lossRecovered=false
nativePjsipRfc2198RecoveryQualified=false
```

That is a negative baseline, not an RFC 2198 qualification.

### Post-2.17 upstream snapshots

The same Baudot harness was also run against two exact upstream fixes targeted toward PJSIP 2.18:

- #4984, `aed27c1ce1c9b47fb5b16b24bac68a1741baef67` — T.140 RTT engine / RFC 2198 RED work;
- #5117, `b9ce4d9b9b9a52df7e3ea93192dec01b9eb0887f` — T.140/RED payload assignment and RED activation work.

Both snapshots moved beyond the 2.17 empty-history behavior, but Baudot's unchanged strict RFC 2198/T.140 parser rejected the observed multi-generation RED because the redundant T140blocks were not in RFC 4103 age order. RFC 4103 requires the redundant data to be in age order with the most recent redundant T140block last. The parser was not relaxed and no loss-recovery PASS was emitted.

The CI characterization pins release 2.17 as the empty-history control and an exact current-upstream snapshot as an age-order limitation probe. These are **expected evidence outcomes**, not implementation exemptions: if either limitation stops reproducing, CI fails until the profile is deliberately reclassified.

A future native RED profile becomes qualified only when the same strict reducer can drop an earlier non-empty generation and recover it from a later implementation-generated RED packet without changing the RFC 2198/T.140 semantics.

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

The RFC 2198 characterization runner additionally requires the exact profile identity and expected evidence outcome, as encoded by `.github/workflows/pjsip-native-rfc2198.yml`.

The runners build only the required PJSUA2/PJMEDIA dependency closure and the small Baudot-owned drivers ephemerally. The linked PJSIP executables are not uploaded as Baudot evidence artifacts. Source identity, build metadata, process observations, SIP evidence, native wire evidence, independent reductions, and SHA-256 manifests are preserved instead.

## Claim boundary

The accepted PJSIP profiles establish controlled implementation observations only:

- the pinned PJSIP 2.17 stack generated native direct-T.140 media that Baudot independently reduced to the expected text;
- the same pinned stack answered an incoming direct-T.140 call and remained active until a readiness-gated release; and
- the same incoming native-media behavior participated as the replacement endpoint in one controlled JAIN-originated `BAUDOT-INTEROP-004` positive arm.

The RFC 2198 lane currently establishes **characterized limitations**, not recoverable native RED behavior. It prevents SDP negotiation or PT100 emission from being promoted to a stronger accessibility-readiness claim without usable historical redundancy.

None of these findings establish SIP, RTP, REFER, RFC 4103, RFC 2198, T.140, PJSIP, JAIN SIP, VRS, SBC/NAT, or production conformance.

The next RED threshold is narrow: an exact upstream profile must pass the existing strict age-order parser and recover a deliberately missing non-empty T140block from later native redundancy. Broader independent native-media implementations remain a separate ensemble goal.
