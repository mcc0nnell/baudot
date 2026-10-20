# Legacy TTY / V.18 interoperability lane

This lane admits legacy acoustic TTY/TDD behavior into Baudot without making a DSP implementation part of Baudot's semantic authority.

## Boundary

Baudot owns the scenario, expected behavior, preserved evidence, and terminal reduction. External implementations generate or consume the legacy audio.

Initial implementations:

- **SpanDSP V.18** — primary external DSP oracle for ITU-T V.18 Annex A / US Weitbrecht TTY behavior.
- **minimodem `tdd` mode** — independent secondary generator/decoder for deterministic fixtures and disagreement testing.
- **hardware TTYs** — future black-box endpoints once an audio capture/injection fixture is available.

No SpanDSP or minimodem source is vendored into Baudot.

## Upstream provenance

The accepted oracle pins and their upstream-declared license provenance are recorded in [`upstream.json`](upstream.json).

| Implementation | Accepted source pin | Baudot role | Upstream-declared license | Integration boundary |
| --- | --- | --- | --- | --- |
| `freeswitch/spandsp` | `8f1e1646bdec99eac5fd2cd92c35563f736b9b89` / 3.1.1 | primary external V.18 DSP oracle | library: LGPL 2.1; test suite and some supporting code: GPL 2 | external pinned checkout, built ephemerally for qualification; not vendored |
| `kamalmostafa/minimodem` | `bb2f34cf5148f101563aa926e201d306edbacbd3` | independent secondary TDD generator/decoder | GPL 3 or later | external pinned checkout, built ephemerally for qualification; not vendored |

These fields record what the pinned upstream projects declare about their own source. They do not make either implementation normative, move external source into Baudot, or change Baudot's semantic-authority boundary. Any future distribution or packaging step that conveys external binaries or source should evaluate the applicable upstream license obligations separately.

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

## BAUDOT-TTY-003: live UDP through Wiretap

The third scenario carries those same deterministic PCMU RTP datagrams over actual UDP sockets from a caller network namespace through the pinned Sandia Wiretap v0.9.0 routed topology to a callee namespace. The far side reconstructs PCM and hands it to the opposite TTY implementation.

```text
minimodem -> PCMU/RTP -> UDP -> Wiretap -> UDP -> PCMU/PCM -> SpanDSP
SpanDSP   -> PCMU/RTP -> UDP -> Wiretap -> UDP -> PCMU/PCM -> minimodem
```

The first accepted run preserved the clean media byte-for-byte across the routed path:

- minimodem -> SpanDSP: 84 of 84 RTP datagrams, identical pre/post SHA-256 `2c2d7d99e07eaa660bfd396781b070f2e00f3a9bff9579844feecc74b3fd3fa4`, decoded `HELLO GA`;
- SpanDSP -> minimodem: 155 of 155 RTP datagrams, identical pre/post SHA-256 `8a4eededf9afd25a089e3b124514f506dfbacb39393c332b8cb462c3a80cb9d7`, decoded `HELLO GA`;
- RTP version, PT 0, 160-byte payload profile, sequence progression, timestamp progression, and SSRC stability all reduced true after the live route.

The dedicated `tty-wiretap-lab` workflow builds the exact external oracle pins, verifies the Wiretap release checksum, runs the routed topology, preserves pre/post packet sequences and reconstructed audio, and lets `reduce_tty_v18_wiretap_udp.py` own the terminal verdict.

## BAUDOT-TTY-004: one-packet loss negative control

A clean-route proof is not enough if the evidence system cannot detect failure. The fourth scenario intentionally omits one RTP datagram before the routed path while preserving the original pre-route sequence as evidence.

The first negative-control run dropped packet index 20, RTP sequence 1020, from the 84-packet minimodem-generated stream. The far side received 83 packets. The reducer observed the exact declared omission, a sequence step of 2, a timestamp step of 320, and rejected clean continuity. With one-packet zero concealment used only to make the damaged audio decodable, SpanDSP observed `HBLO GA` instead of `HELLO GA`.

That text corruption is observational evidence, not a general loss-tolerance threshold. The terminal requirement is that Baudot detect and attribute the declared transport discontinuity rather than silently treating the run as clean.

## Claim boundary

A passing `BAUDOT-TTY-001` result means that the pinned SpanDSP and minimodem implementations cross-generate and cross-decode the expected text under one lossless local WAV profile, with Baudot independently reducing the preserved artifacts.

A passing `BAUDOT-TTY-002` result additionally means that the same text survives one deterministic local PCMU/RTP datagram transform with independently reduced RTP progression.

A passing `BAUDOT-TTY-003` result means that, in the controlled routed lab topology, those PCMU RTP datagrams traversed live UDP through the pinned Wiretap implementation without modification and the opposite TTY implementations recovered the expected text.

A passing `BAUDOT-TTY-004` result means that a deliberately omitted RTP packet was independently visible in the preserved transport evidence and was not misclassified as a clean media run.

None of these results proves V.18 conformance, PSTN survivability, arbitrary packet-loss or jitter tolerance, SBC/transcoder behavior, hardware TTY interoperability, or production readiness.

The next promotion steps are controlled jitter and reordering, an independently implemented G.711/transcoding middlebox, and hardware TTY endpoints.
