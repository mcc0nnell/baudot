# ADR 0002: Keep RTP observability outside the SIP kernel

- Status: Accepted
- Date: 2026-09-05

## Context

A successful SIP dialog and a compatible SDP answer do not prove that media packets arrive. Baudot needs to make that boundary directly observable so production symptoms such as a video black screen can be reduced to reproducible protocol facts instead of being inferred from UI behavior.

JAIN SIP should continue to own SIP signaling and carriage of SDP. Pulling RTP receive/send behavior into the SIP adapter would collapse two independently useful failure domains.

## Decision

Introduce a minimal RTP transport probe outside `JainSipEndpoint`.

The probe may establish a UDP socket, send or receive a syntactically valid RTP packet, extract stable RTP header facts, and compare an observed payload type with the payload type selected by the negotiated SDP.

The SIP endpoint now exposes dialog establishment and explicit hangup as separate states. This gives transport probes a media window between ACK and BYE without making JAIN SIP responsible for media.

## Evidence semantics

Baudot records RTP evidence separately from signaling and SDP evidence.

A positive transport fixture may prove:

- the RTP socket was ready;
- at least one RTP v2 packet arrived;
- the observed payload type matched the negotiated SDP payload type.

It does not prove:

- that the RTP payload bytes are valid H.264, VP8, audio, or T.140 media;
- successful depacketization or decoder input;
- decoded frames;
- rendering or presentation;
- ICE, DTLS, SRTP, NAT traversal, or WebRTC behavior.

A negative fixture is first-class evidence. If SIP succeeds, SDP succeeds, and the expected observation is that no RTP packet arrives, the diagnostic test itself may pass while `mediaTransportProven` remains `false`. A matched expectation is not the same thing as a successful media path.

## Consequence

The first canonical black-screen class can now be represented without a browser:

```text
SIP dialog established       yes
SDP video negotiated         yes
RTP socket ready             yes
first RTP packet observed    no
media transport proven       no
```

Later work can add SRTP/ICE/WebRTC, codec depacketization, decoder input, and presentation as additional evidence boundaries rather than folding them into this one.
