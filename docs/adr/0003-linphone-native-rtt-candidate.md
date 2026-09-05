# ADR-0003: Linphone SDK as a second native RTT implementation candidate

- Status: Proposed
- Date: 2026-09-05
- Decision owners: Baudot maintainers

## Context

ADR-0002 admitted PJSIP/PJPROJECT 2.17 as Baudot's first external native RTT media oracle after a pinned implementation generated live text media that Baudot independently reduced to T.140 behavior.

That is an important implementation boundary, but one native media stack is not enough to establish implementation-independent interoperability. The next threshold is a second independently implemented RFC 4103/T.140 endpoint whose native wire behavior can be observed by the same independent Baudot reducer.

Linphone is a strong candidate because the current Linphone SDK contains an independent RFC 4103 text-media implementation across Liblinphone, Mediastreamer2, and oRTP. At the candidate commit pinned below, the tree contains:

- the Liblinphone call parameter API `linphone_call_params_enable_realtime_text()`;
- the call-associated real-time text path used by `linphone_chat_message_put_char()`;
- Mediastreamer2 RFC 4103 text stream, source, and sink implementations;
- explicit T.140 and RED payload handling; and
- upstream real-time text tests and examples.

The historical standalone `BelledonneCommunications/liblinphone` GitHub repository is no longer the live development repository. Its README states that the project was merged into `BelledonneCommunications/linphone-sdk`. Baudot therefore treats the SDK repository, not the retired standalone repository, as the candidate source identity.

The Linphone SDK is dual licensed, including GNU AGPLv3 for the open-source distribution. This ADR does not make a legal determination about every possible use. As with the initial PJSIP lane, the candidate qualification must remain external and ephemeral: no vendored Linphone SDK source, no committed Linphone SDK binary, and no distribution of a linked qualification executable as a Baudot release artifact without separate licensing review.

## Candidate profile

The initial source profile is exact:

```text
repository: BelledonneCommunications/linphone-sdk
commit:     10f0cb98eb5ae7dae973d6666894561ce5eea561
observed:   2026-09-05
role:       candidate second native RTT implementation
status:     not admitted as an oracle
```

This commit was the GitHub mirror's `master` HEAD observed for this decision. A moving branch, dirty checkout, fork, or different commit is not the same candidate profile.

## Decision

### 1. Admit the source profile for qualification, not the implementation as an oracle

Baudot may build and exercise the pinned Linphone SDK commit as an external candidate implementation.

This ADR is **Proposed**, not Accepted. Source inspection is sufficient to justify qualification work but is not wire evidence. Linphone becomes an admitted native RTT oracle only after the acceptance evidence below is produced and independently reduced.

### 2. The first qualification is direct T.140

The initial experiment mirrors the narrow PJSIP qualification boundary:

```text
Baudot-owned Linphone driver
  -> enables one real-time text stream
  -> disables unrelated media where the public API permits
  -> establishes a SIP dialog with the controlled JAIN SIP UAS
  -> native Linphone text media becomes active
  -> driver emits one deterministic character: "H"
  -> Linphone/Mediastreamer2 generates the wire traffic
  -> Baudot preserves the raw datagram(s)
  -> independent Python RFC 4103/T.140 reference reduces the first non-empty text
```

The controlled Baudot answer should initially select direct T.140 only:

```text
m=text <port> RTP/AVP 98
a=rtpmap:98 t140/1000
```

RFC 2198/RED behavior is intentionally a separate profile. The second-implementation threshold should not be mixed with redundancy recovery in the first experiment.

### 3. Baudot-owned code may invoke only the public application-facing API

The candidate driver may use the public Liblinphone call and chat APIs necessary to:

- create a call;
- enable real-time text;
- wait for a usable call state;
- obtain the call-associated real-time text chat room; and
- emit the deterministic character through the native real-time text path.

The driver must not construct canonical RTP/T.140 packets, call Mediastreamer2 internal source filters directly, or inject Baudot-owned packet bytes. The point of this lane is implementation-generated native media.

### 4. Implementation behavior and verdict authority remain separate

Linphone may report call state, stream state, and application observations. Those observations are preserved as implementation evidence.

Linphone does not declare `rttReady=true`. JAIN SIP does not classify the media packet. The independent Baudot reference parser remains the only component permitted to turn preserved wire traffic into the terminal T.140 readiness verdict.

Implementation agreement remains evidence, not correctness by majority vote.

### 5. The checkout and build are evidence-bound

A qualification run must preserve at least:

- exact repository and commit identity;
- clean checkout status;
- hashes of the upstream source files used to justify the RFC 4103 path;
- Baudot driver source hash;
- compiler and CMake versions;
- build configuration and exit status;
- linked executable hash;
- bounded process stdout/stderr and exit status;
- raw SIP offer/answer evidence;
- raw received text-media datagrams;
- independent reference reduction; and
- an outer SHA-256 manifest.

The linked Linphone qualification executable itself must not be uploaded as a Baudot evidence artifact.

### 6. Passing the first lane still does not establish conformance

A successful direct-T.140 observation would establish only that the pinned Linphone SDK implementation generated wire traffic through its native real-time text path that Baudot independently reduced to the expected first T.140 text under the controlled SDP profile.

It would not establish full Linphone, SIP, RTP, RFC 4103, RFC 2198, T.140, REFER, VRS, SBC/NAT, WebRTC, or production conformance.

## Source-admission evidence

Before native build execution, `scripts/linphone_candidate_admission.py` verifies the exact clean checkout and records hashes for the source surfaces that make the candidate worth testing:

```text
liblinphone/include/linphone/call_params.h
liblinphone/include/linphone/api/c-chat-message.h
liblinphone/coreapi/help/examples/C/realtimetext_sender.c
mediastreamer2/src/voip/rfc4103_textstream.c
mediastreamer2/src/otherfilters/rfc4103_source.c
mediastreamer2/src/otherfilters/rfc4103_sink.c
ortp/src/avprofile.c
```

The admission record proves only that the pinned source tree exposes the expected independent implementation path. It explicitly records `oracleAdmitted=false` and all conformance claims as false.

## Required acceptance evidence

ADR-0003 may move from Proposed to Accepted only after all of the following are preserved in one reproducible run:

```text
exact clean Linphone SDK checkout
-> Baudot-owned driver built against that checkout
-> RTT-enabled SIP offer observed
-> controlled direct PT 98 t140/1000 answer selected
-> dialog confirmed
-> native Linphone real-time text path active
-> deterministic "H" emitted through public Linphone RTT API
-> at least one implementation-generated RTP datagram preserved
-> first non-empty datagram independently reduced to T.140 "H"
-> terminal reducer publishes rttReady=true
```

The acceptance review must also demonstrate that no Baudot-owned canonical packet bytes were used as the positive stimulus and that the Java receiver did not perform terminal T.140 classification.

## After acceptance

If the direct native-media profile passes, the next useful compositions are:

1. qualify Linphone as an incoming native RTT endpoint;
2. place Linphone in the `BAUDOT-INTEROP-004` replacement-leg role;
3. run PJSIP -> controlled infrastructure -> Linphone and the reverse direction while preserving independent reduction;
4. qualify Linphone RFC 2198/RED behavior separately; and
5. introduce production-representative proxy, media-relay, NAT, and gateway paths without moving verdict authority out of the Baudot reducer.

That sequence is the point of adding Linphone: not another implementation badge, but a second independent native-media path against which the same accessibility semantics can be tested.
