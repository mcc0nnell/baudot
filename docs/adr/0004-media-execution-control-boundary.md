# ADR-0004: Separate media execution from orchestration and verdict authority

- Status: Proposed
- Date: 2026-09-14
- Decision owners: Baudot maintainers

## Context

Baudot already separates signaling observations, native media behavior, and terminal accessibility verdicts. The next class of experiments will need to exercise richer media systems: audio, video, WebRTC, RTP/RTCP, real-time text, media relays, transcoding, speech recognition, translation, synthesis, and other transform workers.

A tempting design is to put raw media into the same adapter that owns orchestration. That would make the control layer convenient at first, but it would collapse three boundaries that Baudot depends on:

1. the component that keeps a real-time media session alive;
2. the component that asks for work and correlates lifecycle state; and
3. the independent component that decides what the observed media means.

Those roles must remain distinct.

## Decision

### 1. A media engine owns the real-time media plane

A media engine may own or participate in:

- RTP/RTCP sockets;
- WebRTC transports;
- codec state;
- jitter buffers;
- packet pacing;
- transcoding;
- media forking;
- audio/video frame delivery; and
- implementation-specific media worker attachment.

FreeSWITCH, PJMEDIA, a browser/WebRTC implementation, or another engine may fill this role in an experiment. No engine is privileged by this ADR.

Baudot does not require a media engine to expose raw media through its orchestration adapter.

### 2. The control adapter is metadata-only

The Baudot-facing adapter is a control-plane boundary. It may expose:

- stable Baudot correlation IDs;
- implementation session/channel IDs;
- lifecycle events;
- capability and readiness *claims* made by the implementation;
- commands such as attach, detach, start, stop, bridge, or select;
- bounded implementation metadata; and
- references or hashes that identify separately preserved evidence.

It must not transport raw RTP packets, decoded PCM/audio frames, video frames, T.140 payloads, or other media bytes as its normal command/event API.

The first Java contract for this boundary lives in `org.mcc0nnell.baudot.media.control`.

### 3. Correlation is the join key, not media ownership

Every control command and event carries a Baudot `correlationId`. An adapter may also carry an implementation-specific session identifier, but that identifier is evidence about the implementation, not Baudot's canonical identity.

The expected shape is:

```text
                +-------------------------+
                |   Baudot orchestration  |
                | correlation / commands  |
                +------------+------------+
                             |
                       metadata only
                             |
                +------------v------------+
                |   media control adapter  |
                +------------+------------+
                             |
                    engine-native control
                             |
                +------------v------------+
                |      media engine        |
                | RTP / WebRTC / codecs    |
                +------------+------------+
                             |
                  actual media execution
                             |
          +------------------+------------------+
          |                                     |
 +--------v---------+                  +---------v--------+
 | transform worker |                  | evidence observer |
 | ASR/TTS/etc.     |                  | wire/media facts  |
 +------------------+                  +---------+---------+
                                             |
                                    +--------v--------+
                                    | independent     |
                                    | Baudot reducer  |
                                    +-----------------+
```

The control adapter does not become the owner of the media merely because it can tell the engine what to do.

### 4. Implementation readiness is never terminal verdict authority

A media engine may report facts such as:

```text
channelCreated=true
mediaEstablished=true
workerAttached=true
codecSelected=opus
textStreamActive=true
```

Those facts may be preserved and correlated. They do not, by themselves, establish an accessibility or interoperability verdict.

For example:

```text
implementation says text stream active
!=
independently observed valid T.140
```

and:

```text
transform worker says synthesis complete
!=
independently observed usable output media
```

Baudot reducers retain terminal verdict authority inside the declared claim boundary.

### 5. Media observation remains a separate seam

Raw media may still be captured, forked, preserved, hashed, replayed, or reduced. It simply occurs through an observation/evidence seam rather than by widening the control adapter into a media bus.

This preserves a clean distinction between:

- **command** — what Baudot asked the implementation to do;
- **implementation event** — what the implementation says happened;
- **observation** — what was independently seen on the media/wire boundary; and
- **verdict** — what the reducer concludes from admissible evidence.

### 6. Transform workers are replaceable capabilities

ASR, translation, TTS, voice conversion, captioning, computer vision, or other media transforms must be attachable behind the media engine or an engine-owned media fork without becoming part of the Baudot control contract.

A scenario may therefore compare multiple implementations while preserving the same orchestration vocabulary:

```text
same Baudot command
-> FreeSWITCH-backed adapter
-> WebRTC-backed adapter
-> PJMEDIA-backed adapter
```

The implementation path can differ while the evidence and verdict boundaries remain stable.

## Initial contract

The initial Java contract deliberately contains only:

- `MediaSessionRef` — Baudot correlation plus optional implementation session ID;
- `MediaControlCommand` — bounded control intent;
- `MediaControlEvent` — bounded implementation lifecycle/capability event; and
- `MediaControlAdapter` — command dispatch plus event subscription.

No byte array, `ByteBuffer`, RTP packet, PCM frame, video frame, or T.140 payload type appears in this API.

That absence is intentional, not an unfinished feature.

## Evidence model

A future end-to-end transform experiment should preserve at least these facts separately:

```text
control command issued
-> engine acknowledges/creates session
-> transform capability attaches
-> independent observer records input media fact
-> transform executes
-> independent observer records output media fact
-> evidence hashes/references bind the observations
-> reducer evaluates the scenario
```

A missing observation must remain missing. Control-plane success must never synthesize media-plane success.

## Consequences

### Positive

- Baudot can experiment with sophisticated real-time media without becoming a media server.
- Media engines remain replaceable.
- AI/model workers remain replaceable.
- Existing evidence-first semantics survive richer media experiments.
- Vivisection-style observation can inspect seams without acquiring control authority.
- Failures become easier to localize: signaling, control, execution, observation, or reduction.

### Tradeoffs

- Experiments need at least one additional evidence/observation path.
- Correlation IDs must be propagated carefully across engine and worker boundaries.
- Engine-reported readiness and independently observed readiness must both be retained, even when they agree.
- A control adapter cannot be used as a shortcut for moving media payloads between workers.

## Non-goals

This ADR does not:

- select FreeSWITCH, PJMEDIA, or any other engine as Baudot's canonical media server;
- define an AI dubbing product;
- make model output authoritative;
- replace SIP, SDP, WebRTC, RFC 4103, or T.140 semantics;
- require JAIN SLEE or Apache Celix; or
- claim conformance for any implementation.

## Promotion threshold

Promote this ADR from Proposed to Accepted after one runnable scenario demonstrates all four layers independently:

```text
control command
implementation lifecycle event
independent media observation
terminal reducer verdict
```

The first useful specimen should be deliberately small: attach a transform or observation capability to a live media session, prove that the control adapter never receives media bytes, and bind the resulting independent observation into Baudot evidence.