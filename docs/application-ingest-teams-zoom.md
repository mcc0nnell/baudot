# Teams and Zoom application-ingest boundary

Baudot can ingest Microsoft Teams and Zoom without redefining its semantic core around either platform.

The design rule is:

> **Ingest observations; do not import verdict authority.**

## Two application-facing adapters

### Zoom RTMS

Zoom Realtime Media Streams can expose live meeting media and transcript observations over WebSocket connections. Baudot treats those as source facts such as:

- `media.audio.observed`
- `media.video.observed`
- `media.screenshare.observed`
- `text.transcript.observed`

The first executable fixtures cover audio and transcript observations.

A Zoom transcript is not T.140 real-time text. It cannot, by itself, establish RFC 4103 media, RTT readiness, caption readiness, or end-to-end accessibility.

Public source: <https://developers.zoom.us/docs/rtms/meetings/media/>

### Microsoft Teams application-hosted media

Microsoft documents application-hosted media bots for access to real-time Teams call/meeting media through the Microsoft Graph communications media stack. Baudot keeps the SDK-specific callback surface outside the core and converts only bounded adapter observations into canonical events.

The first executable fixtures cover:

- `signaling.connected`
- `media.audio.observed`

This repo does not copy a proprietary Teams wire payload. `teams-graph-media` fixtures use a Baudot-owned synthetic adapter envelope so the test is about the normalization boundary, not an invented Microsoft protocol.

Public source: <https://learn.microsoft.com/en-us/microsoftteams/platform/bots/calls-and-meetings/requirements-considerations-application-hosted-media-bots>

## Teams Direct Routing is a separate transport lane

Microsoft Teams Direct Routing connects Teams Phone to customer telephony infrastructure through a supported Session Border Controller and SIP signaling. That is useful to Baudot, but it should compose with the existing SIP proving ground rather than fork the core into a Teams-specific signaling model.

```text
Teams Phone
    |
certified / supported SBC boundary
    |
   SIP
    |
Baudot SIP harness
```

Public source: <https://learn.microsoft.com/en-us/microsoftteams/direct-routing-plan>

This application-ingest slice does not claim that Baudot is a Microsoft-certified SBC or that a direct unsupported connection to Teams is production-supported.

## Canonical observation envelope

The testkit emits `baudot.session-observation@1` with:

- a deterministic `eventId`;
- source family and source session identifier;
- event type;
- source participant identifier where applicable;
- occurrence time;
- the bounded observation;
- explicit `source-observation-only` authority.

The initial event vocabulary intentionally stays small:

```text
signaling.connected
media.audio.observed
media.video.observed
media.screenshare.observed
text.transcript.observed
participant.joined
participant.left
session.ended
```

Provider-specific identifiers remain source metadata. They are not promoted into global identity claims.

## Executable negative boundary

Every normalized event carries the same explicit exclusions:

```text
accessibility.caption.ready
rttReady
t140Semantics
rfc4103Media
endToEndAccessibility
```

The validator fails if those exclusions disappear. Unknown Zoom message types or unknown Teams adapter observations fail closed instead of being guessed into the nearest canonical event.

## Next thresholds

After this contract is stable, live adapters can be qualified independently:

1. live Zoom RTMS source -> preserved raw source observation -> canonical event;
2. live Teams application-hosted media callback -> canonical event;
3. application-source media composed with Baudot's existing independent reducers;
4. Teams Direct Routing through an external supported SBC into the existing SIP evidence lane.

Each threshold should preserve source evidence and keep the existing rule that connected is not usable.
