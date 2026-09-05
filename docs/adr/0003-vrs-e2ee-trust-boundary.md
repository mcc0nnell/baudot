# ADR 0003: Define VRS E2EE as a decryption-authorization boundary

- Status: Accepted
- Date: 2026-09-05

## Context

Video Relay Service is an interpreted communications service. A communications assistant (CA) must be able to perceive the conversation in order to relay it. For that reason, an E2EE design for VRS cannot honestly define the caller and callee as the only decrypting endpoints while treating the CA as infrastructure.

At the same time, the systems that route, relay, observe, or troubleshoot the session do not inherently need access to the media content. Baudot needs a portable way to distinguish an authorized participant from infrastructure that merely carries or observes encrypted traffic.

## Decision

Define VRS E2EE in Baudot as an explicit, evidence-bearing decryption-authorization boundary.

For the current media epoch, the authorized decrypting roles are:

- caller;
- callee;
- the active CA set required to relay the conversation.

Infrastructure roles are outside the decrypting set, including:

- SFU or equivalent media-forwarding infrastructure;
- TURN or relay services;
- SIP proxies and signaling infrastructure;
- Wiretap or another network-path witness;
- logging, observability, and evidence-collection infrastructure.

The trust boundary is semantic rather than topological. A service does not become an authorized decryptor merely because media traverses it.

## CA handoff

A CA handoff creates a privacy epoch boundary. After the transition is established:

- the newly active CA must be able to decrypt the current epoch;
- a former CA must not retain the ability to decrypt future media solely because it participated in an earlier epoch.

The eventual key-management design must make that property testable. This ADR does not select a key-management protocol.

## Candidate protection layer

SFrame, standardized in RFC 9605, is a candidate media-protection layer because it is designed to provide end-to-end media encryption while allowing an SFU to access the metadata needed for forwarding without access to the media content. SFrame is transport independent and deliberately separates media protection from key management.

Selecting SFrame as a candidate does not establish a complete VRS E2EE design. Key distribution, participant authentication, CA authorization, handoff, recovery, device trust, downgrade resistance, and operational controls remain separate design decisions.

## Evidence semantics

The first executable contract records whether:

- the caller can decrypt the current epoch;
- the callee can decrypt the current epoch;
- at least one active CA can decrypt the current epoch;
- any former CA can decrypt the current epoch;
- any infrastructure actor can decrypt the current epoch;
- the authorized decryptor set matches the VRS trust policy.

A fixture may pass because it correctly detects an unauthorized decryptor. That diagnostic success must not be represented as successful E2EE.

## Non-claims

This ADR and its test fixture do not prove:

- cryptographic confidentiality or integrity;
- participant identity or device authenticity;
- SFrame conformance;
- secure key distribution;
- resistance to endpoint compromise;
- lawful or regulatory compliance;
- media transport, decoding, or presentation.

Those claims require their own evidence boundaries.
