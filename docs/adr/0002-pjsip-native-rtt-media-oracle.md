# ADR-0002: PJSIP as a native RTT media oracle

- Status: Accepted
- Date: 2026-09-05
- Decision owners: Baudot maintainers

## Context

ADR-0001 established JAIN SIP as Baudot's glass-box signaling instrument and Elixip as the first external independent SIP/call-state oracle. `BAUDOT-INTEROP-004` now has controlled positive and negative accessibility-handoff arms in both JAIN SIP -> Elixip and Elixip -> JAIN SIP directions.

Those positive arms still use a Baudot-owned canonical RTP/T.140 stimulus. That is sufficient to prove the handoff policy boundary:

```text
replacement signaling success
+ independently observed canonical RTT bytes
=> old leg may be released
```

but it does not by itself show a third implementation generating the positive RTT traffic through its own media stack.

PJSIP/PJPROJECT 2.17 provides that next implementation boundary. At the pinned release commit `5a457451fa2712ba18e12b01738e8ff3af2b26fd`:

- PJMEDIA advertises T.140 text media;
- PJSUA2 exposes `Call::sendText()`;
- the PJSUA text layer delegates to `pjmedia_txt_stream_send_text()`; and
- the upstream PJSUA2 sample explicitly requests `textCount = 1` and sends text through that API.

PJSIP therefore adds the most value to Baudot first as a **native RTT media implementation**, not as a replacement for JAIN SIP or Elixip.

The upstream source distribution contains GPLv2 terms. This ADR does not make a legal determination about all possible PJSIP licensing arrangements. It requires Baudot to keep the initial qualification lane external and ephemeral: no vendored PJSIP source, no committed PJSIP binary, and no distribution of the linked qualification executable as a Baudot release artifact without separate licensing review.

## Decision

### 1. PJSIP 2.17 is admitted as an external native-media oracle

The initial profile is exact:

```text
repository: pjsip/pjproject
release:    2.17
commit:     5a457451fa2712ba18e12b01738e8ff3af2b26fd
role:       native RTT media observation
```

A different release, moving branch, dirty checkout, fork, or patched source is not the same oracle profile.

PJSIP does not define Baudot verdict semantics. It supplies implementation behavior and wire evidence.

### 2. Native media is qualified independently from transfer policy

Before PJSIP participates in a REFER handoff, Baudot qualifies the smaller native-media behavior:

```text
PJSIP/PJSUA2 UAC
  -> requests exactly one text stream
  -> JAIN SIP Baudot UAS selects direct PT 98 t140/1000
  -> SIP dialog reaches confirmed state
  -> PJSIP reports the native text media active
  -> PJSIP invokes Call::sendText("H")
  -> PJMEDIA emits the resulting RTP traffic
  -> Baudot preserves the raw datagram(s)
  -> Python reference independently parses first non-empty T.140 text as "H"
```

The JAIN receiver deliberately does not classify the packet as valid RTP/T.140. Java may record only signaling facts, packet receipt, byte counts, and hashes. The Python RFC 4103/T.140 reference owns the terminal semantic reduction.

Both implementation processes are externally time-bounded. A stalled sender or observer is a failed observation, never implicit success.

### 3. Direct T.140 is selected for the qualification lane

The controlled Baudot SDP answer selects only:

```text
m=text <port> RTP/AVP 98
a=rtpmap:98 t140/1000
```

This keeps the first native-media observation focused on direct T.140 rather than mixing the independent-implementation threshold with RFC 2198 recovery behavior. RFC 2198 remains a separate evidence case and does not inherit the direct-T.140 qualification merely because the same implementation participates.

### 4. PJSIP is not promoted to the second SIP oracle

Elixip remains the first independent SIP/call-state oracle under ADR-0001. JAIN SIP remains the primary glass-box signaling instrument.

PJSIP's first ensemble role is narrower and stronger:

> independently implemented RTT media generation and reception.

If later scenarios use PJSIP signaling, that does not erase the role distinction or make implementation agreement a conformance vote.

### 5. The linked qualification binary is ephemeral

Baudot may keep a small Baudot-owned PJSUA2 driver source file that exercises the public native text API. CI may build that driver against the exact external PJSIP checkout to execute the experiment.

The lane preserves:

- exact upstream repository/release/commit identity;
- clean-checkout evidence;
- Baudot driver source hash;
- compiler and CMake versions;
- linked executable hash;
- bounded process stdout/stderr and exit status;
- raw SIP offer/answer evidence;
- raw received RTP datagrams;
- independent reference reduction; and
- SHA-256 manifests.

The linked executable itself is not uploaded as a Baudot evidence artifact.

### 6. Passing qualification does not establish conformance

A successful run establishes only that the pinned PJSIP 2.17 implementation, through its native PJSUA2/PJMEDIA text path, generated wire traffic that Baudot independently reduced to the expected first T.140 text under this controlled SDP profile.

It does not establish full PJSIP, SIP, RTP, RFC 4103, RFC 2198, T.140, VRS, SBC/NAT, or production conformance.

## Acceptance evidence

The initial PJSIP 2.17 qualification passed on 2026-09-05 against commit `5a457451fa2712ba18e12b01738e8ff3af2b26fd`.

The accepted evidence chain records these facts separately:

```text
exact clean PJSIP 2.17 checkout
-> one PJSUA2 text stream offered
-> Baudot selects direct PT 98 t140/1000
-> SIP ACK observed
-> PJSIP native text media reports active
-> Call::sendText("H") invoked
-> two PT 98 datagrams preserved
-> first non-empty datagram independently reduced to T.140 "H"
-> rttReady=true in the independent terminal reducer
```

The first non-empty packet is preserved as `rtt-datagram-001.bin`; the second observed packet carries an empty T.140 block. The outer evidence manifest independently re-verifies the implementation identity, build metadata, process observations, SIP evidence, terminal reduction, and both datagrams.

This evidence accepts the architecture decision and the pinned **direct-T.140** native-media oracle profile. It does not promote the profile to SIP, RTP, RFC 4103, RFC 2198, T.140, or production conformance.

## Implementation status

The transfer threshold described by this ADR has now also been exercised in controlled evidence.

First, Baudot qualifies PJSIP 2.17 as an incoming native-text endpoint independently from REFER:

```text
JAIN direct-T.140 INVITE
-> PJSIP UAS answers
-> native text media active
-> PJSIP Call::sendText("H")
-> live Baudot reference publishes readiness
-> JAIN consumes exact token
-> only then controlled call release
```

Then `BAUDOT-INTEROP-004` composes that qualified endpoint into a positive replacement leg:

```text
REFER accepted
-> replacement PJSIP dialog established
-> direct PT 98 t140/1000 negotiated
-> native PJSIP text media active
-> native PJSIP RTT emitted
-> live Baudot reference accepts implementation-generated packet
-> atomic rttReady token published
-> JAIN consumes token without parsing media
-> only then original-leg release
```

This composition intentionally does not use whole-packet equality as the readiness condition. RTP sequence number, timestamp, and SSRC remain implementation-generated. The Java transfer harness does not own the replacement `m=text` socket or classify T.140 semantics; the independent Python reference remains the only component that can publish the readiness token.

The PJSIP replacement endpoint is required to remain alive through the transfer verdict. A separate completion signal may terminate the test process only after the original-leg release decision is complete; that cleanup signal is not part of readiness.

These implementation observations satisfy the architectural next step that motivated this ADR. They do not change the conformance boundary in Decision 6.

## RFC 2198 characterization status

Baudot has now exercised PJSIP's native RFC 2198/T.140 path as a **separate characterization**, without changing the accepted direct-T.140 profile.

The controlled RED profile requests PJSUA2 text redundancy level 2 and negotiates:

```text
m=text <port> RTP/AVP 100 98
a=rtpmap:100 red/1000
a=fmtp:100 98/98/98
a=rtpmap:98 t140/1000
```

The driver sends ordinary `H` and `I` text through `Call::sendText()`. PJMEDIA owns all RTP and RED construction. JAIN preserves packets but reports RFC 2198 and recovery as `UNCLASSIFIED_BY_JAVA`; Baudot's Python reference remains terminal authority.

### Release 2.17 baseline

Exact release 2.17 at `5a457451fa2712ba18e12b01738e8ff3af2b26fd` negotiates RED and emits PT100, but the controlled observation carries zero-length redundant history. The independent reducer records `OBSERVED_LIMITATION` and requires `lossRecovered=false`.

This establishes a useful negative baseline:

```text
RED negotiated=true
PT100 observed=true
usable historical redundancy=false
controlled recovery=false
```

It does not establish an RFC 2198 implementation failure outside this controlled profile, and it does not weaken the accepted direct-T.140 evidence.

### Post-2.17 upstream fixes

Two exact upstream snapshots were then exercised with the same Baudot driver and unchanged strict parser:

- PJPROJECT #4984, merge commit `aed27c1ce1c9b47fb5b16b24bac68a1741baef67`, titled `pjmedia: Fix T.140 RTT engine and RFC 2198 RED compliance`;
- PJPROJECT #5117, merge commit `b9ce4d9b9b9a52df7e3ea93192dec01b9eb0887f`, titled `pjmedia: fix RTT T140 and RED payload type assignment. Made it case insensitive`.

Both snapshots moved beyond the 2.17 empty-history behavior, but their observed multi-generation RED was rejected by Baudot's RFC 2198/T.140 reference because the redundant T140blocks were not in required age order. RFC 4103 §4.2 requires redundant data to be placed in age order, with the most recent redundant T140block last.

Baudot did **not** respond by relaxing that invariant. A PT100 packet rejected by the strict parser cannot become accessibility readiness evidence, and no simulated-loss recovery PASS is emitted from it.

The characterization workflow therefore treats version-specific limitations as executable expected outcomes. It pins release 2.17 to the zero-length-history baseline and an exact current-upstream snapshot to an age-order limitation probe. If an upstream change makes either expectation stale, CI fails until the evidence is reclassified.

This status does not admit any PJSIP RFC 2198 recovery profile under ADR-0002. Direct PT98 T.140 remains the accepted PJSIP native-media oracle profile.

## Next threshold

For native RED, the next threshold is deliberately narrow:

```text
exact upstream identity
-> RED negotiated
-> implementation-generated RED accepted by unchanged strict parser
-> earlier non-empty primary deliberately treated as lost
-> later RED recovers that exact T140block
-> independent terminal result PASS
```

Until that chain exists, RED negotiation and PT100 emission remain observations rather than readiness evidence.

Broader independent native-media work remains separate: add another native RTT implementation, expand timing/loss patterns, and exercise gateway, SBC/NAT, and production-representative paths without weakening the direct-T.140 evidence model.

Any stronger claim must remain tied to explicit evidence requirements rather than implementation agreement alone.

## Source observations pinned for this decision

- PJSIP release 2.17 was published in April 2026 and resolves to commit `5a457451fa2712ba18e12b01738e8ff3af2b26fd`.
- `pjmedia_txt_stream_send_text()` is the PJMEDIA native text-send API.
- PJSUA2 `Call::sendText()` exposes that path at the call API.
- The PJSUA2 sample requests one text stream and sends text using `Call::sendText()`.
- PJPROJECT #4984 was merged after 2.17 and was targeted toward release 2.18.
- PJPROJECT #5117 was also merged after 2.17 and was targeted toward release 2.18.
- RFC 4103 §4.2 requires redundant T140blocks to be placed in age order, most recent redundant block last.
- The upstream source tree includes GPLv2 terms in `COPYING`.

These observations motivate and delimit the external qualification boundary. Upstream issue or PR titles are not themselves interoperability or conformance findings; Baudot's preserved wire evidence and independent reducers control Baudot's claims.
