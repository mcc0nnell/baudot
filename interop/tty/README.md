# Legacy TTY / V.18 interoperability lane

This lane admits legacy acoustic TTY/TDD behavior into Baudot without making a DSP implementation part of Baudot's semantic authority.

## Boundary

Baudot owns the scenario, expected behavior, preserved evidence, and terminal reduction. External implementations generate or consume the legacy audio.

Initial implementations:

- **SpanDSP V.18** — primary external DSP oracle for ITU-T V.18 Annex A / US Weitbrecht TTY behavior.
- **minimodem `tdd` mode** — independent secondary generator/decoder for deterministic fixtures and disagreement testing.
- **hardware TTYs** — future black-box endpoints once an audio capture/injection fixture is available.

No SpanDSP or minimodem source is vendored into Baudot.

## Initial profile

The first admitted profile is US Weitbrecht TTY:

```text
45.45 baud
5 data bits
LSB first
no parity
2 stop bits
1400 Hz mark
1800 Hz space
half-duplex text telephone behavior
```

Baudot's small reference module owns only the deterministic framing facts. Character mapping, modem state, carrier behavior, automoding, DSP tolerance, and audio generation/detection remain implementation behavior until separately specified by a Baudot vector.

## SpanDSP qualification probe

`tty_v18_roundtrip.c` creates two SpanDSP V.18 contexts in explicit `V18_MODE_WEITBRECHT_5BIT_4545` mode, queues text with `v18_put`, generates PCM with `v18_tx`, feeds the PCM directly to `v18_rx`, and accepts text only from the receiver callback.

Compile against an installed SpanDSP 3.x/4.x development package:

```sh
cc -std=c11 -Wall -Wextra -Werror \
  $(pkg-config --cflags spandsp) \
  interop/tty/tty_v18_roundtrip.c \
  -o target/tty-v18-roundtrip \
  $(pkg-config --libs spandsp)

target/tty-v18-roundtrip "HELLO GA"
```

The first upstream pin used to qualify this lane is:

```text
freeswitch/spandsp
commit 8f1e1646bdec99eac5fd2cd92c35563f736b9b89
version 3.1.1
```

That pin is an implementation input, not a standards claim.

## minimodem cross-check

minimodem's `tdd` mode independently declares the same first profile: 45.45 baud, 5 data bits, 2 stop bits, 1400 Hz mark and 1800 Hz space. It should be used as a second implementation, not as an expected-value generator for Baudot's terminal verdict.

The next fixture should exercise both directions:

```text
minimodem tdd -> WAV/PCM -> SpanDSP V.18 -> text
SpanDSP V.18 -> WAV/PCM -> minimodem tdd -> text
```

Preserve the source text, tool commit/version, exact command line, PCM/WAV bytes or digest, decoded text, and terminal reducer output.

## Claim boundary

A passing in-memory SpanDSP loopback proves only that the pinned SpanDSP implementation can generate and recover the expected message under one lossless local profile. It does not prove PSTN survivability, SIP gateway interoperability, V.18 conformance, hardware TTY interoperability, or production readiness.

Promotion requires independent generation/decoding, impairment cases, gateway transport, and eventually hardware evidence.
