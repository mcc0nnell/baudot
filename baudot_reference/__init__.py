"""Reference-only executable semantics for Baudot test vectors.

These helpers are deliberately small and non-authoritative. Standards-grounded
vectors remain the source of expected behavior; adapters may use this package
as a reference implementation but must not treat it as a substitute for the
underlying specifications.
"""

from .rfc2198 import InvalidRedT140Packet, RedundantT140Generation, Rfc2198T140Packet
from .rfc4103 import InvalidRtpT140Packet, PrimaryT140RtpPacket, T140_CLOCK_RATE_HZ
from .t140 import BaselineSemanticGap, PresentationResult, apply_t140_baseline, encode_utf8
from .t140block import InvalidT140Block, T140Block, concatenate_blocks

__all__ = [
    "BaselineSemanticGap",
    "PresentationResult",
    "apply_t140_baseline",
    "encode_utf8",
    "InvalidT140Block",
    "T140Block",
    "concatenate_blocks",
    "InvalidRtpT140Packet",
    "PrimaryT140RtpPacket",
    "T140_CLOCK_RATE_HZ",
    "InvalidRedT140Packet",
    "RedundantT140Generation",
    "Rfc2198T140Packet",
]
