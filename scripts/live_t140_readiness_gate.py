#!/usr/bin/env python3
"""Live independent RTT readiness gate for replacement-leg handoff policy.

The gate owns a UDP observation socket, preserves every datagram, and delegates
semantic classification to Baudot's narrow RFC 4103/T.140 reference primitive.
It publishes an atomic readiness token only after a valid direct-T.140 packet
contains the expected first non-empty text. Implementation-reported media state
is not verdict authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import time
from typing import Any

from baudot_reference.rfc4103 import InvalidRtpT140Packet, PrimaryT140RtpPacket


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def append_event(path: Path, event_type: str, **fields: Any) -> None:
    event = {"atMonotonicNs": time.monotonic_ns(), "type": event_type, **fields}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")


def write_manifest(directory: Path, names: list[str]) -> None:
    lines = []
    for name in sorted(names):
        path = directory / name
        if path.exists():
            lines.append(f"{sha256_file(path)}  {name}\n")
    (directory / "manifest.sha256").write_text("".join(lines), encoding="utf-8")


def observe(
    udp_socket: socket.socket,
    *,
    evidence_dir: Path,
    ready_file: Path,
    expected_text: str,
    expected_payload_type: int = 98,
    timeout_ms: int = 2500,
) -> int:
    """Observe datagrams and publish readiness only after reference validation.

    Returns 0 on readiness, 3 if a valid T.140 block contains unexpected
    non-empty text, and 4 on bounded timeout without qualifying readiness.
    Malformed or wrong-payload datagrams are evidence but do not terminate the
    observation window.
    """

    if timeout_ms <= 0:
        raise ValueError("timeout_ms must be positive")
    if not expected_text:
        raise ValueError("expected_text must be non-empty")
    if ready_file.parent.resolve() != evidence_dir.resolve():
        raise ValueError("ready_file must be inside evidence_dir")

    evidence_dir.mkdir(parents=True, exist_ok=True)
    ready_file.unlink(missing_ok=True)
    events_path = evidence_dir / "events.jsonl"
    events_path.write_text("", encoding="utf-8")

    deadline = time.monotonic() + timeout_ms / 1000.0
    packet_names: list[str] = []
    ordinal = 0

    append_event(
        events_path,
        "rtt.readiness.observation_started",
        expectedPayloadType=expected_payload_type,
        expectedText=expected_text,
        timeoutMs=timeout_ms,
        semanticAuthority="baudot-reference",
    )

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            result = {
                "result": "TIMEOUT",
                "rttReady": False,
                "packetCount": ordinal,
                "expectedPayloadType": expected_payload_type,
                "expectedText": expected_text,
                "semanticAuthority": "baudot-reference",
            }
            write_json(evidence_dir / "result.json", result)
            append_event(events_path, "rtt.readiness.timeout", packetCount=ordinal)
            write_manifest(evidence_dir, ["events.jsonl", "result.json", *packet_names])
            return 4

        udp_socket.settimeout(remaining)
        try:
            content, source = udp_socket.recvfrom(4096)
        except socket.timeout:
            continue

        ordinal += 1
        packet_name = f"rtt-datagram-{ordinal:03d}.bin"
        packet_names.append(packet_name)
        (evidence_dir / packet_name).write_bytes(content)
        packet_hash = sha256_bytes(content)

        try:
            packet = PrimaryT140RtpPacket.from_bytes(
                content, expected_payload_type=expected_payload_type
            )
        except InvalidRtpT140Packet as exc:
            append_event(
                events_path,
                "rtt.readiness.datagram_rejected",
                ordinal=ordinal,
                bytes=len(content),
                sha256=packet_hash,
                source=f"{source[0]}:{source[1]}",
                reason=str(exc),
            )
            continue

        append_event(
            events_path,
            "rtt.readiness.datagram_parsed",
            ordinal=ordinal,
            bytes=len(content),
            sha256=packet_hash,
            source=f"{source[0]}:{source[1]}",
            payloadType=packet.payload_type,
            marker=packet.marker,
            sequenceNumber=packet.sequence_number,
            timestamp=packet.timestamp,
            ssrc=packet.ssrc,
            empty=packet.block.is_empty,
            text=packet.block.text,
        )

        if packet.block.is_empty:
            continue

        if packet.block.text != expected_text:
            result = {
                "result": "TEXT_MISMATCH",
                "rttReady": False,
                "packetCount": ordinal,
                "qualifyingPacket": packet_name,
                "qualifyingPacketSha256": packet_hash,
                "observedText": packet.block.text,
                "expectedText": expected_text,
                "expectedPayloadType": expected_payload_type,
                "semanticAuthority": "baudot-reference",
            }
            write_json(evidence_dir / "result.json", result)
            append_event(
                events_path,
                "rtt.readiness.text_mismatch",
                ordinal=ordinal,
                observedText=packet.block.text,
                expectedText=expected_text,
            )
            write_manifest(evidence_dir, ["events.jsonl", "result.json", *packet_names])
            return 3

        token = {
            "rttReady": True,
            "semanticAuthority": "baudot-reference",
            "payloadType": packet.payload_type,
            "clockRate": 1000,
            "firstT140Text": packet.block.text,
            "packet": packet_name,
            "packetSha256": packet_hash,
            "sequenceNumber": packet.sequence_number,
            "timestamp": packet.timestamp,
            "ssrc": packet.ssrc,
        }
        result = {
            "result": "PASS",
            "rttReady": True,
            "packetCount": ordinal,
            "expectedPayloadType": expected_payload_type,
            "expectedText": expected_text,
            "semanticAuthority": "baudot-reference",
            "readiness": token,
        }
        write_json(evidence_dir / "result.json", result)
        append_event(
            events_path,
            "rtt.readiness.established",
            ordinal=ordinal,
            text=packet.block.text,
            packetSha256=packet_hash,
        )
        write_json_atomic(ready_file, token)
        write_manifest(
            evidence_dir,
            ["events.jsonl", "result.json", ready_file.name, *packet_names],
        )
        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind-host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--ready-file", type=Path)
    parser.add_argument("--expected-text", default="H")
    parser.add_argument("--payload-type", type=int, default=98)
    parser.add_argument("--timeout-ms", type=int, default=2500)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    evidence_dir = args.evidence_dir.resolve()
    ready_file = (args.ready_file or evidence_dir / "rtt-ready.json").resolve()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        udp_socket.bind((args.bind_host, args.port))
        return observe(
            udp_socket,
            evidence_dir=evidence_dir,
            ready_file=ready_file,
            expected_text=args.expected_text,
            expected_payload_type=args.payload_type,
            timeout_ms=args.timeout_ms,
        )


if __name__ == "__main__":
    raise SystemExit(main())
