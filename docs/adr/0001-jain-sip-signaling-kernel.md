# ADR 0001: Use JAIN SIP as the SIP signaling kernel

- Status: Accepted
- Date: 2026-09-05

## Context

Baudot needs a SIP implementation boundary for RFC 4103 and broader real-time communications interoperability work. The project also needs to keep T.140 semantics portable and independently testable rather than allowing one SIP library to define accessibility behavior.

## Decision

Use the JAIN SIP API with the NIST-derived reference implementation as the first SIP signaling kernel.

JAIN SIP owns:

- SIP transactions and dialogs;
- INVITE/ACK/BYE/CANCEL/REGISTER/OPTIONS mechanics;
- SIP headers, routing, and transport-facing signaling state;
- carriage of SDP bodies.

JAIN SIP does not own:

- T.140 semantic behavior;
- RFC 4103 redundancy policy above the adapter boundary;
- RTP, SRTP, ICE, DTLS, WebRTC, video, audio, or presentation;
- accessibility or interoperability conformance claims.

Baudot code should depend on the standard `javax.sip` API wherever possible and isolate implementation-specific configuration at the adapter edge.

## Evidence rule

The first slice records stable semantic observations rather than raw stack logs. Dynamic values such as Call-IDs, Via branches, ephemeral SIP ports, timestamps, and SDP media ports are excluded from the canonical evidence artifact. Raw packet capture may be added later as supplemental evidence, but it will not replace the semantic trace.

SDP is treated as a separately observable description boundary. The adapter may carry the raw SDP body, while Baudot extracts only the stable media/protocol/codec facts needed by a scenario. A successful SDP offer/answer proves that those descriptions were exchanged and that the selected facts intersect; it does not prove that RTP, SRTP, ICE, DTLS, decoding, rendering, or presentation succeeded.

A passing local dialog proves only that the exercised signaling path completed under the tested environment. It does not establish RFC 3261, RFC 4103, T.140, media, security, or accessibility conformance.

## Dependency posture

The published JAIN SIP RI is old, so Baudot treats it as a bounded protocol engine behind an adapter rather than a platform. The initial build explicitly supplies the API dependency and uses reload4j instead of reviving the original Log4j 1.x runtime dependency.

Java 17 and Java 21 are verification targets. Any incompatibility discovered there becomes evidence for either a narrow modernization patch or a replacement implementation behind the same boundary.
