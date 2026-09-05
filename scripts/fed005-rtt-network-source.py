#!/usr/bin/env python3
"""Emit deterministic RFC 4103/RFC 2198 packets for BAUDOT-FED-005."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import socket
import struct
import time

T140_PT = 98
RED_PT = 99
SSRC = 0x42415544


def direct_packet(sequence: int, timestamp: int, text: str, *, marker: bool = False) -> bytes:
    payload = text.encode("utf-8")
    return struct.pack(
        "!BBHII",
        0x80,
        (0x80 if marker else 0) | T140_PT,
        sequence,
        timestamp,
        SSRC,
    ) + payload


def red_packet(sequence: int, timestamp: int, redundant: str, primary: str) -> bytes:
    redundant_bytes = redundant.encode("utf-8")
    primary_bytes = primary.encode("utf-8")
    if len(redundant_bytes) > 0x3FF:
        raise ValueError("redundant T.140 block is too large")
    timestamp_offset = 300
    packed = (timestamp_offset << 10) | len(redundant_bytes)
    red_header = bytes(
        [
            0x80 | T140_PT,
            (packed >> 16) & 0xFF,
            (packed >> 8) & 0xFF,
            packed & 0xFF,
            T140_PT,
        ]
    )
    return struct.pack("!BBHII", 0x80, RED_PT, sequence, timestamp, SSRC) + red_header + redundant_bytes + primary_bytes


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-host", required=True)
    parser.add_argument("--target-port", type=int, required=True)
    parser.add_argument("--source-port", type=int, default=49201)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--spacing-ms", type=int, default=80)
    args = parser.parse_args()

    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    packets = [
        (0, "A", direct_packet(0, 700, "A", marker=True)),
        (1, "B", direct_packet(1, 1000, "B")),
        (2, "C", red_packet(2, 1300, "B", "C")),
    ]

    emitted: list[dict[str, object]] = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("0.0.0.0", args.source_port))
        for index, (sequence, semantic_text, packet) in enumerate(packets, start=1):
            path = args.evidence_dir / f"rtt-seq-{sequence}-sent.bin"
            path.write_bytes(packet)
            sock.sendto(packet, (args.target_host, args.target_port))
            emitted.append(
                {
                    "index": index,
                    "sequenceNumber": sequence,
                    "semanticText": semantic_text,
                    "bytes": len(packet),
                    "sha256": sha256(packet),
                    "artifact": path.name,
                }
            )
            if index < len(packets):
                time.sleep(args.spacing_ms / 1000.0)

    result = {
        "scenario": "BAUDOT-FED-005",
        "injection": "network-path-drop-after-source-emission",
        "target": f"{args.target_host}:{args.target_port}",
        "sourcePort": args.source_port,
        "emittedSequenceNumbers": [0, 1, 2],
        "intendedSemanticText": "ABC",
        "packets": emitted,
    }
    (args.evidence_dir / "source-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
