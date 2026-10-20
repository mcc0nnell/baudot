#!/usr/bin/env python3
"""Independently reduce the legacy TTY cross-oracle evidence bundle."""

from __future__ import annotations

import hashlib
import json
import sys
import wave
from pathlib import Path

EXPECTED_RATE = 8000
EXPECTED_CHANNELS = 1
EXPECTED_WIDTH = 2


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        "durationSeconds": frames / rate if rate else 0.0,
        "profileMatches": (
            channels == EXPECTED_CHANNELS
            and width == EXPECTED_WIDTH
            and rate == EXPECTED_RATE
        ),
    }


def read_text(path: Path) -> str:
    return path.read_bytes().decode("ascii")


def main(argv: list[str]) -> int:
    evidence = Path(argv[1]) if len(argv) > 1 else Path("target/evidence/tty-v18-cross-oracle")

    source = read_text(evidence / "source.txt")
    minimodem_to_spandsp = read_text(evidence / "decoded-by-spandsp.txt")
    spandsp_to_minimodem = read_text(evidence / "decoded-by-minimodem.txt")

    minimodem_wav = inspect_wav(evidence / "minimodem-generated.wav")
    spandsp_wav = inspect_wav(evidence / "spandsp-generated.wav")

    checks = {
        "minimodemAudioProfileMatches": minimodem_wav["profileMatches"],
        "spandspAudioProfileMatches": spandsp_wav["profileMatches"],
        "minimodemToSpanDspTextMatches": minimodem_to_spandsp == source,
        "spanDspToMinimodemTextMatches": spandsp_to_minimodem == source,
        "independentOracleAgreement": (
            minimodem_to_spandsp == spandsp_to_minimodem == source
        ),
    }
    passed = all(checks.values())

    result = {
        "scenario": "BAUDOT-TTY-001",
        "profile": {
            "name": "US_WEITBRECHT_4545",
            "baud": 45.45,
            "dataBits": 5,
            "bitOrder": "lsb-first",
            "parity": "none",
            "stopBits": 2,
            "markHz": 1400,
            "spaceHz": 1800,
            "sampleRateHz": EXPECTED_RATE,
        },
        "sourceText": source,
        "decoded": {
            "minimodemToSpanDsp": minimodem_to_spandsp,
            "spanDspToMinimodem": spandsp_to_minimodem,
        },
        "audio": {
            "minimodemGenerated": minimodem_wav,
            "spandspGenerated": spandsp_wav,
        },
        "checks": checks,
        "terminalVerdict": "pass" if passed else "fail",
        "claimBoundary": (
            "Cross-oracle agreement under one lossless local 8 kHz WAV profile; "
            "not V.18, PSTN, RTP/SIP gateway, hardware TTY, or production conformance."
        ),
    }

    output = evidence / "verdict.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
