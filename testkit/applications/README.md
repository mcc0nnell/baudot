# Application ingest

This directory defines clean-room, deterministic fixtures for application-platform observations that Baudot can normalize without granting those platforms semantic or accessibility verdict authority.

The first source families are:

- `zoom-rtms` — synthetic observations shaped from Zoom Realtime Media Streams public documentation;
- `teams-graph-media` — a Baudot-owned adapter envelope for observations from Microsoft Teams application-hosted media callbacks.

The canonical output is `baudot.session-observation@1`.

```text
Zoom RTMS ---------------------\
                                \
                                 > source adapter
                                /       |
Teams Graph real-time media ---/        v
                           baudot.session-observation@1
                                      |
                                      v
                            Baudot evidence/reducers
```

The boundary is deliberate:

```text
source connected
!= media observed
!= transcript observed
!= caption ready
!= RFC 4103 media
!= T.140 semantics
!= rttReady
!= end-to-end accessibility
```

A source adapter may report what the external application surface actually exposed. It may not promote that observation into a Baudot terminal accessibility verdict.

## Teams has two distinct paths

This contract covers the application-media path (`teams-graph-media`).

Teams Phone Direct Routing belongs on the SIP side of Baudot and should enter through a supported/certified SBC boundary rather than creating a Teams-specific SIP core. The Direct Routing path is therefore documented here but intentionally not represented as a fake local Teams SIP fixture.

## Privacy boundary

Committed contract inputs are synthetic. The reference normalizer uses opaque source participant identifiers and deliberately drops display names from canonical observations. Production retention, consent, transcript handling, recording indications, and provider policy are deployment concerns outside this test contract.
