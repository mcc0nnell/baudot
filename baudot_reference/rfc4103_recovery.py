"""Deterministic RFC 4103 gap recovery using RFC 2198 T140block redundancy.

This module recovers a forward sequence gap from redundancy already present in
a subsequently received packet. It intentionally does not implement the
optional out-of-order waiting timer from RFC 4103 section 5.4.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rfc2198 import Rfc2198T140Packet
from .t140block import T140Block

SEQUENCE_MODULUS = 1 << 16
MAX_FORWARD_DISTANCE = 1 << 15
MISSING_TEXT_MARKER = T140Block.from_text("\uFFFD")


class UnsupportedSequenceProgression(ValueError):
    """Raised when deterministic forward-only recovery cannot classify a packet."""


@dataclass(frozen=True, slots=True)
class RecoveredT140Block:
    sequence_number: int
    block: T140Block
    source: str  # "redundant", "missing-marker", or "primary"


def _forward_distance(previous: int, current: int) -> int:
    if not 0 <= previous < SEQUENCE_MODULUS or not 0 <= current < SEQUENCE_MODULUS:
        raise ValueError("RTP sequence numbers must fit in 16 bits")
    return (current - previous) % SEQUENCE_MODULUS


def infer_redundant_sequence_numbers(packet: Rfc2198T140Packet) -> tuple[int, ...]:
    """Infer sequence numbers for redundant generations by counting backward.

    RFC 4103 requires the redundancy area to contain contiguous generations in
    age order, so k redundant blocks in primary packet N map to N-k..N-1.
    """

    count = len(packet.redundant)
    return tuple((packet.sequence_number - count + index) % SEQUENCE_MODULUS for index in range(count))


def recover_forward_gap(
    previous_sequence_number: int | None,
    packet: Rfc2198T140Packet,
) -> tuple[RecoveredT140Block, ...]:
    """Recover text between a previously consumed primary and a new RED packet.

    When no previous sequence number is known, historical redundant generations
    are not replayed; only the new primary is emitted. For a forward gap, each
    missing sequence number is filled from matching redundancy when available,
    otherwise by exactly one T.140 missing-text marker (U+FFFD). The current
    primary is emitted last.

    Duplicate/backward packets and ambiguous jumps of half the 16-bit sequence
    space are outside this deterministic helper and should be handled by a
    separate reordering policy.
    """

    current = packet.sequence_number
    if previous_sequence_number is None:
        return (RecoveredT140Block(current, packet.primary, "primary"),)

    distance = _forward_distance(previous_sequence_number, current)
    if distance == 0:
        raise UnsupportedSequenceProgression("duplicate RTP sequence number")
    if distance >= MAX_FORWARD_DISTANCE:
        raise UnsupportedSequenceProgression(
            "packet is backward or too far ahead for deterministic forward-only recovery"
        )

    inferred = infer_redundant_sequence_numbers(packet)
    redundant_by_sequence = {
        sequence: generation.block
        for sequence, generation in zip(inferred, packet.redundant, strict=True)
    }

    recovered: list[RecoveredT140Block] = []
    for step in range(1, distance):
        sequence = (previous_sequence_number + step) % SEQUENCE_MODULUS
        block = redundant_by_sequence.get(sequence)
        if block is None:
            recovered.append(RecoveredT140Block(sequence, MISSING_TEXT_MARKER, "missing-marker"))
        else:
            recovered.append(RecoveredT140Block(sequence, block, "redundant"))

    recovered.append(RecoveredT140Block(current, packet.primary, "primary"))
    return tuple(recovered)
