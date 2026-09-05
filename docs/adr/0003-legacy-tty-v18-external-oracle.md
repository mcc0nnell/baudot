# ADR-0003: Admit legacy TTY/V.18 as an external media oracle lane

- Status: Accepted
- Date: 2026-09-05

## Context

Baudot already separates portable accessibility behavior from implementation stacks. Legacy US TTY/TDD adds a materially different media boundary: 5-bit asynchronous text is conveyed as narrowband FSK audio and may cross PSTN, RTP audio, gateways, SBCs, transcoders, and modern real-time-text systems.

Implementing a modem inside the semantic core would collapse the distinction between expected behavior and one DSP implementation. Ignoring legacy TTY would leave an important accessibility interop boundary untested.

SpanDSP provides a V.18 implementation with an explicit US Weitbrecht 45.45-baud mode. minimodem provides an independent `tdd` mode using the same first-line profile. Both are useful implementation oracles, but neither should become Baudot's verdict authority.

## Decision

Baudot will add a legacy TTY interoperability lane with these boundaries:

1. Baudot owns deterministic framing facts, scenarios, evidence requirements, and terminal reduction.
2. SpanDSP V.18 is admitted as the first external DSP oracle for US Weitbrecht TTY.
3. minimodem is admitted as an independent secondary generator/decoder for cross-implementation fixtures.
4. Neither implementation is vendored into Baudot or treated as normative.
5. Character mapping, modem state transitions, automoding, DSP tolerance, carrier behavior, and gateway survivability require explicit vectors before they can support stronger claims.
6. Initial success criteria are deliberately narrow: pinned implementation identity, exact profile, preserved input/output evidence, and independently stated terminal expectations.

The first profile is:

```text
V.18 Annex A / US Weitbrecht TTY
45.45 baud
5 data bits
LSB first
no parity
2 stop bits
1400 Hz mark
1800 Hz space
```

## Evidence model

The lane distinguishes at least these facts:

```text
ttyProfileSelected=true
sourceTextQueued=true
audioGenerated=true
audioObserved=true
textDecoded=true
decodedTextMatches=false|true
independentOracleAgreement=false|true
terminalVerdict=...
```

A DSP library reporting success is evidence about that implementation. It is not the terminal verdict.

## Initial proving sequence

1. Run an in-memory SpanDSP V.18 encode/decode smoke probe.
2. Add deterministic WAV/PCM preservation with SHA-256 digests.
3. Cross-generate and cross-decode with minimodem.
4. Introduce controlled audio impairment vectors.
5. Carry the audio through an RTP/SIP gateway while preserving pre- and post-gateway evidence.
6. Add hardware TTY endpoints as black-box oracles.
7. Define TTY ↔ T.140 gateway scenarios only after the legacy side can be independently reduced.

## Consequences

This keeps the core small and evidence-oriented while making a path available from legacy TTY audio to modern RTT. It also prevents a passing SpanDSP loopback from being overclaimed as V.18, PSTN, SIP, gateway, or hardware conformance.
