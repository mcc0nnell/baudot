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

The accepted minimodem source pin for the first cross-oracle lane is:

```text
kamalmostafa/minimodem
commit bb2f34cf5148f101563aa926e201d306edbacbd3
```

## BAUDOT-TTY-001: cross-oracle WAV proof

The first executable cross-implementation scenario runs both directions at an 8 kHz, mono, 16-bit PCM WAV boundary:

```text
"HELLO GA"
    │
    ├─ minimodem TDD ─> WAV ─> SpanDSP V.18 ─> decoded text
    │
    └─ SpanDSP V.18 ─> WAV ─> minimodem TDD ─> decoded text
```

Run it with installed SpanDSP, libsndfile, and minimodem development/runtime tooling:

```sh
bash scripts/run-tty-v18-cross-oracle.sh
```

The dedicated `tty-v18-oracle` workflow builds both external implementations from their exact pinned commits before running the scenario. The evidence bundle preserves source text, source commits and observed versions, command logs, generated WAV files and SHA-256 digests, decoder output, tool logs, and Baudot's independent `verdict.json`.

The terminal reducer requires both WAV files to remain 8 kHz mono 16-bit PCM and requires exact decoded-text equality in both directions. Agreement is evidence; it is not a conformance declaration.

## BAUDOT-TTY-002: PCMU/RTP survivability proof

The second scenario inserts deterministic G.711 mu-law companding and RTP packetization between each generator and the opposite decoder:

```text
minimodem TDD
    -> PCM16
    -> PCMU
    -> RTP v2 / PT 0 / 8 kHz / 160 samples per packet
    -> PCMU decode
    -> PCM16
    -> SpanDSP V.18

SpanDSP V.18
    -> PCM16
    -> PCMU
    -> RTP v2 / PT 0 / 8 kHz / 160 samples per packet
    -> PCMU decode
    -> PCM16
    -> minimodem TDD
```

Run it after or alongside `BAUDOT-TTY-001`:

```sh
bash scripts/run-tty-v18-pcmu-rtp.sh
```

`tty_pcmu_rtp.py` preserves complete RTP datagrams in a length-prefixed `.rtpseq` evidence container. This is intentionally not described as PCAP or live network evidence. `reduce_tty_v18_pcmu_rtp.py` independently parses the preserved RTP headers and requires:

- RTP version 2;
- static payload type 0 (PCMU);
- 160-byte payloads / 20 ms packetization at an 8 kHz clock;
- monotonic sequence numbers;
- timestamps advancing by 160;
- a stable SSRC;
- reconstructed 8 kHz mono PCM16 audio; and
- exact `HELLO GA` recovery in both implementation directions.

This proves a controlled codec-and-packetization survivability slice before live UDP or Wiretap is introduced.

## Claim boundary

A passing `BAUDOT-TTY-001` result means that the pinned SpanDSP and minimodem implementations cross-generate and cross-decode the expected text under one lossless local WAV profile, with Baudot independently reducing the preserved artifacts.

A passing `BAUDOT-TTY-002` result additionally means that the same text survives one deterministic local PCMU/RTP datagram transform with independently reduced RTP progression.

Neither result proves V.18 conformance, PSTN survivability, live RTP/UDP interoperability, SBC/transcoder tolerance, hardware TTY interoperability, or production readiness.

The next promotion step is to carry these exact PCMU RTP datagrams over live UDP through the existing controlled network/evidence substrate, then add loss, jitter, transcoding, and hardware endpoints.
