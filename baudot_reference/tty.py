"""Reference framing primitives for legacy US Weitbrecht TTY/TDD.

This module intentionally stops below character-set mapping and above DSP.
It describes the deterministic asynchronous 5-bit framing used by the
Baudot testkit for legacy TTY evidence. SpanDSP, minimodem, hardware TTYs,
and future adapters remain external implementations/oracles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class WeitbrechtProfile:
    """Observable line/framing parameters for one Weitbrecht TTY profile."""

    baud: float
    mark_hz: float
    space_hz: float
    data_bits: int = 5
    stop_bits: int = 2
    bit_order: str = "lsb-first"

    @property
    def framed_bits_per_code(self) -> int:
        """Start bit + data bits + stop bits."""

        return 1 + self.data_bits + self.stop_bits

    @property
    def nominal_code_seconds(self) -> float:
        return self.framed_bits_per_code / self.baud


US_WEITBRECHT_4545 = WeitbrechtProfile(
    baud=45.45,
    mark_hz=1400.0,
    space_hz=1800.0,
)


class InvalidTtyCode(ValueError):
    """Raised when a value cannot be represented by the 5-bit TTY profile."""


def frame_5bit_code(code: int) -> tuple[int, ...]:
    """Return one asynchronous TTY frame as logical line bits.

    The frame is one start bit (0), five data bits least-significant-bit
    first, and two stop bits (1). The function deliberately does not map
    characters to 5-bit codes; that mapping is a separate semantic concern.
    """

    if not 0 <= code <= 0x1F:
        raise InvalidTtyCode(f"TTY code must fit in 5 bits: {code!r}")

    data = tuple((code >> bit) & 1 for bit in range(5))
    return (0, *data, 1, 1)


def frame_5bit_codes(codes: Iterable[int]) -> tuple[int, ...]:
    """Concatenate deterministic asynchronous frames for 5-bit codes."""

    framed: list[int] = []
    for code in codes:
        framed.extend(frame_5bit_code(code))
    return tuple(framed)
