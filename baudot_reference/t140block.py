"""Transport-neutral T140block primitive.

RFC 4103 defines a T140block as one block of UTF-8-coded T.140 data with no
additional T.140 framing. This module intentionally stops at that boundary.
"""

from __future__ import annotations

from dataclasses import dataclass


class InvalidT140Block(ValueError):
    """Raised when bytes cannot represent a complete UTF-8 T140block."""


@dataclass(frozen=True, slots=True)
class T140Block:
    """A validated, transport-neutral T140block.

    Empty blocks are valid. Non-empty blocks must contain complete UTF-8
    characters; no RTP, SCTP, redundancy, timing, or signaling metadata is
    represented here.
    """

    payload: bytes

    def __post_init__(self) -> None:
        try:
            self.payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise InvalidT140Block("T140block must contain complete valid UTF-8 characters") from exc

    @classmethod
    def from_text(cls, text: str) -> "T140Block":
        return cls(text.encode("utf-8"))

    @classmethod
    def from_code_points(cls, code_points: list[int] | tuple[int, ...]) -> "T140Block":
        chars: list[str] = []
        for code_point in code_points:
            if not isinstance(code_point, int):
                raise TypeError("code points must be integers")
            if code_point < 0 or code_point > 0x10FFFF or 0xD800 <= code_point <= 0xDFFF:
                raise ValueError(f"invalid Unicode scalar value: U+{code_point:04X}")
            chars.append(chr(code_point))
        return cls.from_text("".join(chars))

    @classmethod
    def from_hex(cls, value: str) -> "T140Block":
        compact = "".join(value.split())
        if len(compact) % 2:
            raise InvalidT140Block("hex payload must contain whole octets")
        try:
            payload = bytes.fromhex(compact)
        except ValueError as exc:
            raise InvalidT140Block("hex payload is invalid") from exc
        return cls(payload)

    @property
    def text(self) -> str:
        return self.payload.decode("utf-8")

    @property
    def utf8_hex(self) -> str:
        return " ".join(f"{byte:02x}" for byte in self.payload)

    @property
    def code_points(self) -> tuple[int, ...]:
        return tuple(ord(char) for char in self.text)

    @property
    def is_empty(self) -> bool:
        return len(self.payload) == 0


def concatenate_blocks(blocks: list[T140Block] | tuple[T140Block, ...]) -> T140Block:
    """Concatenate T140blocks without adding framing.

    This models content preservation only. It does not imply that a transport
    may collapse block boundaries; RFC-specific adapters own that decision.
    """

    return T140Block(b"".join(block.payload for block in blocks))
