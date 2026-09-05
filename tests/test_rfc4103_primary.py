from __future__ import annotations

import unittest

from baudot_reference.rfc4103 import (
    InvalidRtpT140Packet,
    PrimaryT140RtpPacket,
    T140_CLOCK_RATE_HZ,
)
from baudot_reference.t140block import T140Block


class PrimaryRfc4103PacketTests(unittest.TestCase):
    def test_clock_rate_is_1000_hz(self) -> None:
        self.assertEqual(T140_CLOCK_RATE_HZ, 1000)

    def test_serializes_minimal_primary_packet(self) -> None:
        packet = PrimaryT140RtpPacket(
            payload_type=98,
            sequence_number=1,
            timestamp=1000,
            ssrc=0x01020304,
            marker=False,
            block=T140Block.from_text("Hi"),
        )
        self.assertEqual(
            packet.to_bytes().hex(" "),
            "80 62 00 01 00 00 03 e8 01 02 03 04 48 69",
        )

    def test_marker_bit_is_serialized(self) -> None:
        packet = PrimaryT140RtpPacket(
            payload_type=98,
            sequence_number=2,
            timestamp=1300,
            ssrc=1,
            marker=True,
            block=T140Block.from_text("A"),
        )
        self.assertEqual(packet.to_bytes()[1], 0xE2)

    def test_empty_t140block_is_valid_payload(self) -> None:
        packet = PrimaryT140RtpPacket(
            payload_type=98,
            sequence_number=3,
            timestamp=1600,
            ssrc=1,
            marker=False,
            block=T140Block(b""),
        )
        parsed = PrimaryT140RtpPacket.from_bytes(packet.to_bytes(), expected_payload_type=98)
        self.assertTrue(parsed.block.is_empty)

    def test_round_trip_preserves_header_and_block(self) -> None:
        original = PrimaryT140RtpPacket(
            payload_type=98,
            sequence_number=65535,
            timestamp=0xFFFFFFFF,
            ssrc=0xAABBCCDD,
            marker=True,
            block=T140Block.from_text("café"),
        )
        parsed = PrimaryT140RtpPacket.from_bytes(original.to_bytes(), expected_payload_type=98)
        self.assertEqual(parsed, original)

    def test_wrong_payload_type_is_rejected_when_expected(self) -> None:
        packet = PrimaryT140RtpPacket(
            payload_type=98,
            sequence_number=1,
            timestamp=1,
            ssrc=1,
            marker=False,
            block=T140Block.from_text("A"),
        )
        with self.assertRaises(InvalidRtpT140Packet):
            PrimaryT140RtpPacket.from_bytes(packet.to_bytes(), expected_payload_type=99)

    def test_non_v2_packet_is_rejected(self) -> None:
        raw = bytes.fromhex("40 62 00 01 00 00 00 01 00 00 00 01 41")
        with self.assertRaises(InvalidRtpT140Packet):
            PrimaryT140RtpPacket.from_bytes(raw)

    def test_extension_profile_is_fail_closed(self) -> None:
        raw = bytes.fromhex("90 62 00 01 00 00 00 01 00 00 00 01 41")
        with self.assertRaises(InvalidRtpT140Packet):
            PrimaryT140RtpPacket.from_bytes(raw)


if __name__ == "__main__":
    unittest.main()
