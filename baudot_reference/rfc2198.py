"""RFC 2198 redundancy container specialized for RFC 4103 T140blocks.

This module constructs/parses RED packets whose encapsulated block payloads
are all `text/t140`. Loss detection and recovery policy remain separate.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct

from .rfc4103 import FIXED_HEADER_SIZE, RESERVED_PAYLOAD_TYPES, RTP_VERSION
from .t140block import T140Block


class InvalidRedT140Packet(ValueError):
    """Raised when a packet violates the supported RFC 2198/T.140 boundary."""


def _uint(value: int, bits: int, label: str) -> int:
    if not isinstance(value, int) or value < 0 or value >= (1 << bits):
        raise ValueError(f"{label} must fit in {bits} unsigned bits")
    return value


@dataclass(frozen=True, slots=True)
class RedundantT140Generation:
    """One previous T140block carried as RFC 2198 redundancy."""

    timestamp_offset: int
    block: T140Block

    def __post_init__(self) -> None:
        _uint(self.timestamp_offset, 14, "timestamp_offset")
        if len(self.block.payload) >= (1 << 10):
            raise ValueError("redundant T140block length must fit in 10 bits")


@dataclass(frozen=True, slots=True)
class Rfc2198T140Packet:
    """RTP RED packet containing previous T140blocks plus one primary block.

    The outer payload type identifies RFC 2198 RED. Every encapsulated block
    uses the same text/t140 payload type. Redundant generations are ordered
    oldest to newest, which for a common 1000 Hz clock means timestamp
    offsets strictly decrease toward the primary block.
    """

    red_payload_type: int
    t140_payload_type: int
    sequence_number: int
    timestamp: int
    ssrc: int
    marker: bool
    redundant: tuple[RedundantT140Generation, ...]
    primary: T140Block

    def __post_init__(self) -> None:
        for label, value in (
            ("red_payload_type", self.red_payload_type),
            ("t140_payload_type", self.t140_payload_type),
        ):
            _uint(value, 7, label)
            if value in RESERVED_PAYLOAD_TYPES:
                raise ValueError(f"{label} 72 and 73 are reserved by RTP/RTCP demultiplexing")
        if self.red_payload_type == self.t140_payload_type:
            raise ValueError("RED and text/t140 payload types must be distinct")
        _uint(self.sequence_number, 16, "sequence_number")
        _uint(self.timestamp, 32, "timestamp")
        _uint(self.ssrc, 32, "ssrc")
        if not isinstance(self.marker, bool):
            raise TypeError("marker must be boolean")
        if not isinstance(self.primary, T140Block):
            raise TypeError("primary must be a T140Block")
        if not isinstance(self.redundant, tuple) or not self.redundant:
            raise ValueError("RFC 2198 packet must contain at least one redundant generation")
        if not all(isinstance(item, RedundantT140Generation) for item in self.redundant):
            raise TypeError("redundant entries must be RedundantT140Generation values")

        offsets = [item.timestamp_offset for item in self.redundant]
        if any(left <= right for left, right in zip(offsets, offsets[1:])):
            raise ValueError(
                "redundant T140blocks must be in age order: oldest first, most recent last"
            )

    @staticmethod
    def _redundant_header(payload_type: int, generation: RedundantT140Generation) -> bytes:
        packed = (generation.timestamp_offset << 10) | len(generation.block.payload)
        return bytes((0x80 | payload_type,)) + packed.to_bytes(3, "big")

    def to_bytes(self) -> bytes:
        first_octet = 0x80  # V=2, P=0, X=0, CC=0
        second_octet = self.red_payload_type | (0x80 if self.marker else 0)
        rtp_header = struct.pack(
            "!BBHII",
            first_octet,
            second_octet,
            self.sequence_number,
            self.timestamp,
            self.ssrc,
        )
        red_headers = b"".join(
            self._redundant_header(self.t140_payload_type, generation)
            for generation in self.redundant
        )
        primary_header = bytes((self.t140_payload_type,))
        payloads = b"".join(item.block.payload for item in self.redundant) + self.primary.payload
        return rtp_header + red_headers + primary_header + payloads

    @classmethod
    def from_bytes(
        cls,
        packet: bytes,
        *,
        expected_red_payload_type: int | None = None,
        expected_t140_payload_type: int | None = None,
    ) -> "Rfc2198T140Packet":
        if len(packet) < FIXED_HEADER_SIZE + 5:
            raise InvalidRedT140Packet("RED packet is too short for one redundant header")

        first_octet, second_octet, sequence_number, timestamp, ssrc = struct.unpack(
            "!BBHII", packet[:FIXED_HEADER_SIZE]
        )
        version = first_octet >> 6
        if version != RTP_VERSION:
            raise InvalidRedT140Packet(f"unsupported RTP version {version}")
        if first_octet & 0x3F:
            raise InvalidRedT140Packet(
                "reference RED parser supports no padding, extension, or CSRC list"
            )

        marker = bool(second_octet & 0x80)
        red_payload_type = second_octet & 0x7F
        if expected_red_payload_type is not None and red_payload_type != expected_red_payload_type:
            raise InvalidRedT140Packet(
                f"unexpected RED payload type {red_payload_type}; expected {expected_red_payload_type}"
            )

        cursor = FIXED_HEADER_SIZE
        header_specs: list[tuple[int, int, int]] = []
        while True:
            if cursor >= len(packet):
                raise InvalidRedT140Packet("RED headers terminate unexpectedly")
            first = packet[cursor]
            follows = bool(first & 0x80)
            block_pt = first & 0x7F
            if follows:
                if cursor + 4 > len(packet):
                    raise InvalidRedT140Packet("truncated redundant block header")
                packed = int.from_bytes(packet[cursor + 1 : cursor + 4], "big")
                timestamp_offset = packed >> 10
                block_length = packed & 0x03FF
                header_specs.append((block_pt, timestamp_offset, block_length))
                cursor += 4
                continue

            primary_pt = block_pt
            cursor += 1
            break

        if not header_specs:
            raise InvalidRedT140Packet("RED packet contains no redundant generations")
        t140_payload_type = primary_pt
        if expected_t140_payload_type is not None and t140_payload_type != expected_t140_payload_type:
            raise InvalidRedT140Packet(
                f"unexpected text/t140 payload type {t140_payload_type}; expected {expected_t140_payload_type}"
            )
        if any(block_pt != t140_payload_type for block_pt, _, _ in header_specs):
            raise InvalidRedT140Packet("all RED blocks must use the same text/t140 payload type")

        generations: list[RedundantT140Generation] = []
        for _, timestamp_offset, block_length in header_specs:
            end = cursor + block_length
            if end > len(packet):
                raise InvalidRedT140Packet("redundant block length exceeds packet payload")
            try:
                block = T140Block(packet[cursor:end])
            except ValueError as exc:
                raise InvalidRedT140Packet("redundant block is not a valid T140block") from exc
            generations.append(RedundantT140Generation(timestamp_offset, block))
            cursor = end

        try:
            primary = T140Block(packet[cursor:])
        except ValueError as exc:
            raise InvalidRedT140Packet("primary block is not a valid T140block") from exc

        try:
            return cls(
                red_payload_type=red_payload_type,
                t140_payload_type=t140_payload_type,
                sequence_number=sequence_number,
                timestamp=timestamp,
                ssrc=ssrc,
                marker=marker,
                redundant=tuple(generations),
                primary=primary,
            )
        except (TypeError, ValueError) as exc:
            raise InvalidRedT140Packet(str(exc)) from exc
