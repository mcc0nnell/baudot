#!/usr/bin/env python3
"""Deterministic PCMU/RTP media transform for legacy TTY evidence.

The output .rtpseq file stores each complete RTP datagram as:
    uint16_be packet_length
    packet bytes

It is intentionally a preserved datagram sequence, not a PCAP and not a live
network transport.
"""

from __future__ import annotations

import argparse
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 8000
SAMPLES_PER_PACKET = 160
RTP_PAYLOAD_TYPE_PCMU = 0
RTP_SSRC = 0x42415544
RTP_INITIAL_SEQUENCE = 1000
RTP_INITIAL_TIMESTAMP = 0
ULAW_BIAS = 0x84


def linear16_to_ulaw(sample: int) -> int:
    """Encode one signed 16-bit PCM sample as G.711 mu-law."""

    sample = max(-32768, min(32767, sample))
    if sample >= 0:
        magnitude = ULAW_BIAS + sample
        mask = 0xFF
    else:
        magnitude = ULAW_BIAS - sample
        mask = 0x7F

    segment = max(0, (magnitude | 0xFF).bit_length() - 8)
    if segment >= 8:
        return 0x7F ^ mask

    quantization = (magnitude >> (segment + 3)) & 0x0F
    return ((segment << 4) | quantization) ^ mask


def ulaw_to_linear16(code: int) -> int:
    """Decode one G.711 mu-law byte to signed 16-bit PCM."""

    value = (~code) & 0xFF
    magnitude = (((value & 0x0F) << 3) + ULAW_BIAS) << ((value & 0x70) >> 4)
    sample = ULAW_BIAS - magnitude if value & 0x80 else magnitude - ULAW_BIAS
    return max(-32768, min(32767, sample))


def read_pcm16_wav(path: Path) -> list[int]:
    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 1:
            raise ValueError("TTY PCMU bridge requires mono WAV input")
        if wav.getsampwidth() != 2:
            raise ValueError("TTY PCMU bridge requires 16-bit PCM WAV input")
        if wav.getframerate() != SAMPLE_RATE:
            raise ValueError(f"TTY PCMU bridge requires {SAMPLE_RATE} Hz WAV input")
        raw = wav.readframes(wav.getnframes())

    return [sample[0] for sample in struct.iter_unpack("<h", raw)]


def write_pcm16_wav(path: Path, samples: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))


def build_rtp_packet(sequence: int, timestamp: int, payload: bytes) -> bytes:
    header = struct.pack(
        "!BBHII",
        0x80,
        RTP_PAYLOAD_TYPE_PCMU,
        sequence & 0xFFFF,
        timestamp & 0xFFFFFFFF,
        RTP_SSRC,
    )
    return header + payload


def write_rtp_sequence(path: Path, packets: list[bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        for packet in packets:
            if len(packet) > 0xFFFF:
                raise ValueError("RTP packet is too large for evidence container")
            handle.write(struct.pack("!H", len(packet)))
            handle.write(packet)


def read_rtp_sequence(path: Path) -> list[bytes]:
    packets: list[bytes] = []
    raw = path.read_bytes()
    offset = 0
    while offset < len(raw):
        if offset + 2 > len(raw):
            raise ValueError("truncated RTP sequence length prefix")
        length = struct.unpack_from("!H", raw, offset)[0]
        offset += 2
        if offset + length > len(raw):
            raise ValueError("truncated RTP datagram")
        packets.append(raw[offset : offset + length])
        offset += length
    return packets


def bridge(input_wav: Path, rtp_sequence: Path, output_wav: Path) -> None:
    samples = read_pcm16_wav(input_wav)
    packets: list[bytes] = []

    sequence = RTP_INITIAL_SEQUENCE
    timestamp = RTP_INITIAL_TIMESTAMP
    for offset in range(0, len(samples), SAMPLES_PER_PACKET):
        chunk = samples[offset : offset + SAMPLES_PER_PACKET]
        if len(chunk) < SAMPLES_PER_PACKET:
            chunk.extend([0] * (SAMPLES_PER_PACKET - len(chunk)))
        payload = bytes(linear16_to_ulaw(sample) for sample in chunk)
        packets.append(build_rtp_packet(sequence, timestamp, payload))
        sequence = (sequence + 1) & 0xFFFF
        timestamp = (timestamp + SAMPLES_PER_PACKET) & 0xFFFFFFFF

    write_rtp_sequence(rtp_sequence, packets)

    reconstructed: list[int] = []
    for packet in read_rtp_sequence(rtp_sequence):
        if len(packet) < 12:
            raise ValueError("RTP datagram shorter than fixed header")
        reconstructed.extend(ulaw_to_linear16(byte) for byte in packet[12:])
    write_pcm16_wav(output_wav, reconstructed)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_wav", type=Path)
    parser.add_argument("rtp_sequence", type=Path)
    parser.add_argument("output_wav", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bridge(args.input_wav, args.rtp_sequence, args.output_wav)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
