#!/usr/bin/env python3
"""Send, receive, and reconstruct preserved RTP datagram sequences over UDP."""

from __future__ import annotations

import argparse
import json
import socket
import struct
import time
from pathlib import Path

try:
    from .tty_pcmu_rtp import (
        SAMPLES_PER_PACKET,
        read_rtp_sequence,
        ulaw_to_linear16,
        write_pcm16_wav,
        write_rtp_sequence,
    )
except ImportError:
    from tty_pcmu_rtp import (
        SAMPLES_PER_PACKET,
        read_rtp_sequence,
        ulaw_to_linear16,
        write_pcm16_wav,
        write_rtp_sequence,
    )


def rtp_sequence_number(packet: bytes) -> int:
    if len(packet) < 12:
        raise ValueError("RTP datagram shorter than fixed header")
    return struct.unpack_from("!H", packet, 2)[0]


def rtp_timestamp(packet: bytes) -> int:
    if len(packet) < 12:
        raise ValueError("RTP datagram shorter than fixed header")
    return struct.unpack_from("!I", packet, 4)[0]


def describe_packets(packets: list[bytes]) -> dict[str, object]:
    return {
        "packetCount": len(packets),
        "sequenceNumbers": [rtp_sequence_number(packet) for packet in packets],
        "timestamps": [rtp_timestamp(packet) for packet in packets],
        "packetLengths": [len(packet) for packet in packets],
    }


def send_sequence(
    input_path: Path,
    *,
    target: str,
    port: int,
    interval_ms: float,
    drop_indices: set[int],
    source_port: int | None,
) -> dict[str, object]:
    packets = read_rtp_sequence(input_path)
    invalid = sorted(index for index in drop_indices if index < 0 or index >= len(packets))
    if invalid:
        raise ValueError(f"drop indices outside packet sequence: {invalid}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if source_port is not None:
        sock.bind(("0.0.0.0", source_port))

    sent_packets: list[bytes] = []
    started = time.monotonic()
    try:
        for index, packet in enumerate(packets):
            if index not in drop_indices:
                sent = sock.sendto(packet, (target, port))
                if sent != len(packet):
                    raise OSError(f"short UDP send: {sent}/{len(packet)}")
                sent_packets.append(packet)

            if interval_ms > 0:
                deadline = started + ((index + 1) * interval_ms / 1000.0)
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)
    finally:
        sock.close()

    return {
        "target": f"{target}:{port}",
        "inputPacketCount": len(packets),
        "sentPacketCount": len(sent_packets),
        "dropIndices": sorted(drop_indices),
        "intervalMs": interval_ms,
        "sentSequenceNumbers": [rtp_sequence_number(packet) for packet in sent_packets],
    }


def receive_sequence(
    output_path: Path,
    *,
    bind: str,
    port: int,
    expected_count: int,
    timeout_seconds: float,
    ready_file: Path | None,
) -> dict[str, object]:
    if expected_count <= 0:
        raise ValueError("expected_count must be positive")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((bind, port))
    if ready_file is not None:
        ready_file.parent.mkdir(parents=True, exist_ok=True)
        ready_file.write_text(f"{bind}:{port}\n", encoding="utf-8")

    packets: list[bytes] = []
    sources: list[str] = []
    deadline = time.monotonic() + timeout_seconds
    try:
        while len(packets) < expected_count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"received {len(packets)} of {expected_count} expected UDP datagrams"
                )
            sock.settimeout(min(0.5, remaining))
            try:
                packet, source = sock.recvfrom(65535)
            except socket.timeout:
                continue
            packets.append(packet)
            sources.append(f"{source[0]}:{source[1]}")
    finally:
        sock.close()

    write_rtp_sequence(output_path, packets)
    return {
        "bind": f"{bind}:{port}",
        "receivedPacketCount": len(packets),
        "sourceAddresses": sorted(set(sources)),
        **describe_packets(packets),
    }


def reconstruct_sequence(
    input_path: Path,
    output_wav: Path,
    *,
    conceal_gaps: bool,
) -> dict[str, object]:
    packets = read_rtp_sequence(input_path)
    samples: list[int] = []
    concealed_packets = 0
    previous_sequence: int | None = None

    for packet in packets:
        if len(packet) != 12 + SAMPLES_PER_PACKET:
            raise ValueError(
                f"expected fixed PCMU RTP datagram length {12 + SAMPLES_PER_PACKET}, got {len(packet)}"
            )

        sequence = rtp_sequence_number(packet)
        if previous_sequence is not None:
            gap = (sequence - previous_sequence - 1) & 0xFFFF
            if gap:
                if gap > 1024:
                    raise ValueError(f"implausible RTP sequence gap: {gap}")
                if conceal_gaps:
                    samples.extend([0] * (gap * SAMPLES_PER_PACKET))
                    concealed_packets += gap
        previous_sequence = sequence
        samples.extend(ulaw_to_linear16(byte) for byte in packet[12:])

    write_pcm16_wav(output_wav, samples)
    return {
        "packetCount": len(packets),
        "concealGaps": conceal_gaps,
        "concealedPacketCount": concealed_packets,
        "outputSamples": len(samples),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    send = sub.add_parser("send")
    send.add_argument("input", type=Path)
    send.add_argument("--target", required=True)
    send.add_argument("--port", type=int, required=True)
    send.add_argument("--interval-ms", type=float, default=20.0)
    send.add_argument("--drop-index", type=int, action="append", default=[])
    send.add_argument("--source-port", type=int)

    receive = sub.add_parser("receive")
    receive.add_argument("output", type=Path)
    receive.add_argument("--bind", required=True)
    receive.add_argument("--port", type=int, required=True)
    receive.add_argument("--expected-count", type=int, required=True)
    receive.add_argument("--timeout-seconds", type=float, default=15.0)
    receive.add_argument("--ready-file", type=Path)

    reconstruct = sub.add_parser("reconstruct")
    reconstruct.add_argument("input", type=Path)
    reconstruct.add_argument("output_wav", type=Path)
    reconstruct.add_argument("--conceal-gaps", action="store_true")

    count = sub.add_parser("count")
    count.add_argument("input", type=Path)

    describe = sub.add_parser("describe")
    describe.add_argument("input", type=Path)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "send":
        result = send_sequence(
            args.input,
            target=args.target,
            port=args.port,
            interval_ms=args.interval_ms,
            drop_indices=set(args.drop_index),
            source_port=args.source_port,
        )
    elif args.command == "receive":
        result = receive_sequence(
            args.output,
            bind=args.bind,
            port=args.port,
            expected_count=args.expected_count,
            timeout_seconds=args.timeout_seconds,
            ready_file=args.ready_file,
        )
    elif args.command == "reconstruct":
        result = reconstruct_sequence(
            args.input,
            args.output_wav,
            conceal_gaps=args.conceal_gaps,
        )
    elif args.command == "count":
        print(len(read_rtp_sequence(args.input)))
        return 0
    else:
        result = describe_packets(read_rtp_sequence(args.input))

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
