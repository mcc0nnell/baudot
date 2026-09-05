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

This keeps the first native-media observation focused on direct T.140 rather than mixing the independent-implementation threshold with RFC 2198 recovery behavior. A later PJSIP RED qualification may be added as a separate evidence case.

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

This evidence accepts the architecture decision and the pinned native-media oracle profile. It does not promote the profile to SIP, RTP, RFC 4103, T.140, or production conformance.

## Next threshold

Replace the Baudot-owned positive media stimulus in a `BAUDOT-INTEROP-004` replacement leg with the qualified PJSIP native text endpoint.

That transfer experiment must preserve the same policy invariant:

```text
replacement ACK
-> native PJSIP text media active
-> native PJSIP RTT emission
-> independent Baudot T.140 observation
-> only then old-leg release
```

The transfer reducer does not change merely because the media producer changes.

## Source observations pinned for this decision

- PJSIP release 2.17 was published in April 2026 and resolves to commit `5a457451fa2712ba18e12b01738e8ff3af2b26fd`.
- `pjmedia_txt_stream_send_text()` is the PJMEDIA native text-send API.
- PJSUA2 `Call::sendText()` exposes that path at the call API.
- The PJSUA2 sample requests one text stream and sends text using `Call::sendText()`.
- The upstream source tree includes GPLv2 terms in `COPYING`.

These observations motivate the external qualification boundary. They are not themselves interoperability or conformance findings.
