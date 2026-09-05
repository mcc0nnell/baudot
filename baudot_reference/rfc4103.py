"""Narrow RFC 4103 primary text/t140 RTP packet primitive.

This module models the direct text/t140 payload format without RFC 2198
redundancy. It is therefore a building block for RFC 4103 interop work, not a
complete RFC 4103 sender profile.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct

from .t140block import T140Block

RTP_VERSION = 2
T140_CLOCK_RATE_HZ = 1000
FIXED_HEADER_SIZE = 12
RESERVED_PAYLOAD_TYPES = {72, 73}


class InvalidRtpT140Packet(ValueError):
    """Raised when a packet is outside the narrow primary text/t140 profile."""


def _uint(value: int, bits: int, label: str) -> int:
    if not isinstance(value, int) or value < 0 or value >= (1 << bits):
        raise ValueError(f"{label} must fit in {bits} unsigned bits")
    return value


@dataclass(frozen=True, slots=True)
class PrimaryT140RtpPacket:
    """Direct RFC 4103 text/t140 payload carried in a minimal RTP v2 header.

    The reference primitive deliberately supports no padding, extensions, or
    CSRC list. Payload-type negotiation, redundancy, timers, RTCP, and socket
    transport live above this object.
    """

    payload_type: int
    sequence_number: int
    timestamp: int
    ssrc: int
    marker: bool
    block: T140Block

    def __post_init__(self) -> None:
        _uint(self.payload_type, 7, "payload_type")
        if self.payload_type in RESERVED_PAYLOAD_TYPES:
            raise ValueError("payload_type 72 and 73 are reserved by RTP/RTCP demultiplexing")
        _uint(self.sequence_number, 16, "sequence_number")
        _uint(self.timestamp, 32, "timestamp")
        _uint(self.ssrc, 32, "ssrc")
        if not isinstance(self.marker, bool):
            raise TypeError("marker must be boolean")
        if not isinstance(self.block, T140Block):
            raise TypeError("block must be a T140Block")

    def to_bytes(self) -> bytes:
        first_octet = 0x80  # V=2, P=0, X=0, CC=0
        second_octet = self.payload_type | (0x80 if self.marker else 0)
        header = struct.pack(
            "!BBHII",
            first_octet,
            second_octet,
            self.sequence_number,
            self.timestamp,
            self.ssrc,
        )
        return header + self.block.payload

    @classmethod
    def from_bytes(cls, packet: bytes, *, expected_payload_type: int | None = None) -> "PrimaryT140RtpPacket":
        if len(packet) < FIXED_HEADER_SIZE:
            raise InvalidRtpT140Packet("RTP packet is shorter than the 12-octet fixed header")

        first_octet, second_octet, sequence_number, timestamp, ssrc = struct.unpack(
            "!BBHII", packet[:FIXED_HEADER_SIZE]
        )
        version = first_octet >> 6
        padding = bool(first_octet & 0x20)
        extension = bool(first_octet & 0x10)
        csrc_count = first_octet & 0x0F
        if version != RTP_VERSION:
            raise InvalidRtpT140Packet(f"unsupported RTP version {version}")
        if padding or extension or csrc_count:
            raise InvalidRtpT140Packet(
                "reference primary text/t140 parser supports no padding, extension, or CSRC list"
            )

        marker = bool(second_octet & 0x80)
        payload_type = second_octet & 0x7F
        if payload_type in RESERVED_PAYLOAD_TYPES:
            raise InvalidRtpT140Packet("reserved RTP payload type")
        if expected_payload_type is not None and payload_type != expected_payload_type:
            raise InvalidRtpT140Packet(
                f"unexpected payload type {payload_type}; expected {expected_payload_type}"
            )

        try:
            block = T140Block(packet[FIXED_HEADER_SIZE:])
        except ValueError as exc:
            raise InvalidRtpT140Packet("RTP payload is not a valid T140block") from exc

        return cls(
            payload_type=payload_type,
            sequence_number=sequence_number,
            timestamp=timestamp,
            ssrc=ssrc,
            marker=marker,
            block=block,
        )
