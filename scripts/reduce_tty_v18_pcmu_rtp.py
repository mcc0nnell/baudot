#!/usr/bin/env python3
"""Independently reduce BAUDOT-TTY-002 PCMU/RTP evidence."""

from __future__ import annotations

import hashlib
import json
import struct
import sys
import wave
from pathlib import Path

EXPECTED_RATE = 8000
EXPECTED_CHANNELS = 1
EXPECTED_WIDTH = 2
EXPECTED_PT = 0
EXPECTED_PAYLOAD_BYTES = 160


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_wav(path: Path) -> dict[str, object]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        rate = wav.getframerate()
        frames = wav.getnframes()
    return {
        "sha256": sha256(path),
        "channels": channels,
        "sampleWidthBytes": width,
        "sampleRateHz": rate,
        "frames": frames,
        "profileMatches": (
            channels == EXPECTED_CHANNELS
            and width == EXPECTED_WIDTH
            and rate == EXPECTED_RATE
        ),
    }


def parse_rtp_sequence(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    packets: list[dict[str, int]] = []
    offset = 0

    while offset < len(raw):
        if offset + 2 > len(raw):
            raise ValueError("truncated RTP sequence length prefix")
        length = struct.unpack_from("!H", raw, offset)[0]
        offset += 2
        if offset + length > len(raw):
            raise ValueError("truncated RTP datagram")

        packet = raw[offset : offset + length]
        offset += length
        if len(packet) < 12:
            raise ValueError("RTP datagram shorter than fixed header")

        first, second, sequence, timestamp, ssrc = struct.unpack("!BBHII", packet[:12])
        version = first >> 6
        csrc_count = first & 0x0F
        extension = (first >> 4) & 0x01
        payload_type = second & 0x7F
        payload_length = len(packet) - 12

        if csrc_count != 0 or extension:
            raise ValueError("BAUDOT-TTY-002 supports only fixed 12-byte RTP headers")

        packets.append(
            {
                "version": version,
                "payloadType": payload_type,
                "sequence": sequence,
                "timestamp": timestamp,
                "ssrc": ssrc,
                "payloadBytes": payload_length,
            }
        )

    if not packets:
        raise ValueError("RTP sequence contains no packets")

    header_profile_matches = all(
        packet["version"] == 2
        and packet["payloadType"] == EXPECTED_PT
        and packet["payloadBytes"] == EXPECTED_PAYLOAD_BYTES
        for packet in packets
    )
    sequence_progression = all(
        packets[index]["sequence"] == ((packets[index - 1]["sequence"] + 1) & 0xFFFF)
        for index in range(1, len(packets))
    )
    timestamp_progression = all(
        packets[index]["timestamp"]
        == ((packets[index - 1]["timestamp"] + EXPECTED_PAYLOAD_BYTES) & 0xFFFFFFFF)
        for index in range(1, len(packets))
    )
    one_ssrc = len({packet["ssrc"] for packet in packets}) == 1

    return {
        "sha256": sha256(path),
        "packetCount": len(packets),
        "firstSequence": packets[0]["sequence"],
        "lastSequence": packets[-1]["sequence"],
        "firstTimestamp": packets[0]["timestamp"],
        "lastTimestamp": packets[-1]["timestamp"],
        "ssrc": packets[0]["ssrc"],
        "headerProfileMatches": header_profile_matches,
        "sequenceProgression": sequence_progression,
        "timestampProgression": timestamp_progression,
        "singleSsrc": one_ssrc,
    }


def read_ascii(path: Path) -> str:
    return path.read_bytes().decode("ascii")


def main(argv: list[str]) -> int:
    evidence = Path(argv[1]) if len(argv) > 1 else Path("target/evidence/tty-v18-pcmu-rtp")

    source = read_ascii(evidence / "source.txt")
    minimodem_to_spandsp = read_ascii(evidence / "decoded-by-spandsp.txt")
    spandsp_to_minimodem = read_ascii(evidence / "decoded-by-minimodem.txt")

    min_rtp = parse_rtp_sequence(evidence / "minimodem-to-spandsp.rtpseq")
    span_rtp = parse_rtp_sequence(evidence / "spandsp-to-minimodem.rtpseq")
    min_wav = inspect_wav(evidence / "minimodem-after-pcmu.wav")
    span_wav = inspect_wav(evidence / "spandsp-after-pcmu.wav")

    checks = {
        "minimodemRtpHeaderProfileMatches": min_rtp["headerProfileMatches"],
        "minimodemRtpSequenceProgression": min_rtp["sequenceProgression"],
        "minimodemRtpTimestampProgression": min_rtp["timestampProgression"],
        "minimodemRtpSingleSsrc": min_rtp["singleSsrc"],
        "spandspRtpHeaderProfileMatches": span_rtp["headerProfileMatches"],
        "spandspRtpSequenceProgression": span_rtp["sequenceProgression"],
        "spandspRtpTimestampProgression": span_rtp["timestampProgression"],
        "spandspRtpSingleSsrc": span_rtp["singleSsrc"],
        "minimodemPostPcmuWavProfileMatches": min_wav["profileMatches"],
        "spandspPostPcmuWavProfileMatches": span_wav["profileMatches"],
        "minimodemToSpanDspTextMatches": minimodem_to_spandsp == source,
        "spanDspToMinimodemTextMatches": spandsp_to_minimodem == source,
        "independentOracleAgreement": (
            minimodem_to_spandsp == spandsp_to_minimodem == source
        ),
    }
    passed = all(checks.values())

    result = {
        "scenario": "BAUDOT-TTY-002",
        "mediaPath": "PCM16 -> PCMU -> RTP datagrams -> PCMU -> PCM16",
        "rtpProfile": {
            "version": 2,
            "payloadType": 0,
            "encoding": "PCMU",
            "clockRateHz": 8000,
            "samplesPerPacket": 160,
            "packetizationMs": 20,
        },
        "sourceText": source,
        "decoded": {
            "minimodemToSpanDsp": minimodem_to_spandsp,
            "spanDspToMinimodem": spandsp_to_minimodem,
        },
        "rtp": {
            "minimodemToSpanDsp": min_rtp,
            "spandspToMinimodem": span_rtp,
        },
        "postPcmuAudio": {
            "minimodemToSpanDsp": min_wav,
            "spandspToMinimodem": span_wav,
        },
        "checks": checks,
        "terminalVerdict": "pass" if passed else "fail",
        "claimBoundary": (
            "TTY text survivability through a deterministic local PCMU/RTP datagram "
            "transform; not live UDP, packet-loss, jitter, SBC, PSTN, or gateway conformance."
        ),
    }

    (evidence / "verdict.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
