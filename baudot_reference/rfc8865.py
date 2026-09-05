"""RFC 8865 T.140-over-WebRTC data-channel reference boundary.

The transport contract is reliable and in-order with subprotocol ``t140``.
T140blocks remain the content unit; an SCTP user message may carry one or more
blocks, but no RFC 2198 redundancy is added.
"""

from __future__ import annotations

from dataclasses import dataclass

from .t140block import T140Block

T140_SUBPROTOCOL = "t140"
RELIABLE = True
ORDERED = True
DEFAULT_TRANSMISSION_INTERVAL_MS = 300
DEFAULT_CPS = 30


class InvalidT140DataChannelMessage(ValueError):
    """Raised when a data-channel user message is not valid T.140 UTF-8 data."""


@dataclass(frozen=True, slots=True)
class T140DataChannelProfile:
    """RFC 8865 generic transport properties, independent of browser API shape."""

    subprotocol: str = T140_SUBPROTOCOL
    reliable: bool = RELIABLE
    ordered: bool = ORDERED
    transmission_interval_ms: int = DEFAULT_TRANSMISSION_INTERVAL_MS
    cps: int = DEFAULT_CPS

    def __post_init__(self) -> None:
        if self.subprotocol != T140_SUBPROTOCOL:
            raise ValueError("RFC 8865 T.140 data channel subprotocol must be 't140'")
        if self.reliable is not True:
            raise ValueError("RFC 8865 T.140 data channel must be reliable")
        if self.ordered is not True:
            raise ValueError("RFC 8865 T.140 data channel must be in-order")
        if not isinstance(self.transmission_interval_ms, int) or self.transmission_interval_ms <= 0:
            raise ValueError("transmission_interval_ms must be a positive integer")
        if not isinstance(self.cps, int) or self.cps <= 0:
            raise ValueError("cps must be a positive integer")


@dataclass(frozen=True, slots=True)
class T140DataChannelMessage:
    """One SCTP user-message payload carrying one or more T140blocks.

    RFC 8865 adds no delimiter between T140blocks at this layer. Consequently,
    parsing a received SCTP user message recovers the T.140 content, not the
    sender's original block boundaries.
    """

    payload: bytes

    def __post_init__(self) -> None:
        try:
            T140Block(self.payload)
        except ValueError as exc:
            raise InvalidT140DataChannelMessage(
                "T.140 data-channel message must contain valid complete UTF-8 T.140 data"
            ) from exc

    @classmethod
    def from_blocks(
        cls,
        blocks: list[T140Block] | tuple[T140Block, ...],
    ) -> "T140DataChannelMessage":
        if not blocks:
            raise ValueError("a T.140 data-channel message must carry at least one T140block")
        if not all(isinstance(block, T140Block) for block in blocks):
            raise TypeError("blocks must contain only T140Block values")
        return cls(b"".join(block.payload for block in blocks))

    @classmethod
    def from_bytes(cls, payload: bytes) -> "T140DataChannelMessage":
        return cls(payload)

    @property
    def aggregate_block(self) -> T140Block:
        return T140Block(self.payload)

    @property
    def text(self) -> str:
        return self.aggregate_block.text

    @property
    def utf8_hex(self) -> str:
        return self.aggregate_block.utf8_hex


def replacement_marker_for_possible_loss() -> T140Block:
    """Return the T.140 missing-text marker used when loss is suspected.

    RFC 8865 permits this indication after data-channel reestablishment. This
    helper does not decide *when* loss occurred; recovery policy owns that.
    """

    return T140Block.from_text("\uFFFD")
