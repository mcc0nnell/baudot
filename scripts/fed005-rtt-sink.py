#!/usr/bin/env python3
"""Capture gateway-forwarded degraded RTP evidence for BAUDOT-FED-005."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import socket


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sequence_number(data: bytes) -> int:
    if len(data) < 12 or data[0] >> 6 != 2:
        raise ValueError("not a minimal RTP v2 packet")
    return int.from_bytes(data[2:4], "big")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind-host", default="127.0.0.1")
    parser.add_argument("--bind-port", type=int, required=True)
    parser.add_argument("--expect", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    args = parser.parse_args()

    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    args.ready_file.parent.mkdir(parents=True, exist_ok=True)
    packets: list[dict[str, object]] = []

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((args.bind_host, args.bind_port))
        sock.settimeout(args.timeout)
        args.ready_file.write_text(
            json.dumps({"ready": True, "bind": f"{args.bind_host}:{args.bind_port}"}, indent=2) + "\n",
            encoding="utf-8",
        )
        for index in range(1, args.expect + 1):
            data, remote = sock.recvfrom(2048)
            seq = sequence_number(data)
            artifact = args.evidence_dir / f"rtt-datagram-{index}-received.bin"
            artifact.write_bytes(data)
            packets.append(
                {
                    "index": index,
                    "sequenceNumber": seq,
                    "source": f"{remote[0]}:{remote[1]}",
                    "bytes": len(data),
                    "sha256": sha256(data),
                    "artifact": artifact.name,
                }
            )

    result = {
        "scenario": "BAUDOT-FED-005",
        "datagramsReceived": len(packets),
        "receivedSequenceNumbers": [packet["sequenceNumber"] for packet in packets],
        "packets": packets,
    }
    (args.evidence_dir / "sink-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["receivedSequenceNumbers"] == [0, 2] else 4


if __name__ == "__main__":
    raise SystemExit(main())
