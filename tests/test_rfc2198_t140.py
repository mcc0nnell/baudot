from __future__ import annotations

import unittest

from baudot_reference.rfc2198 import (
    InvalidRedT140Packet,
    RedundantT140Generation,
    Rfc2198T140Packet,
)
from baudot_reference.t140block import T140Block


class Rfc2198T140Tests(unittest.TestCase):
    def test_serializes_one_redundant_generation(self) -> None:
        packet = Rfc2198T140Packet(
            red_payload_type=100,
            t140_payload_type=98,
            sequence_number=10,
            timestamp=1600,
            ssrc=1,
            marker=False,
            redundant=(RedundantT140Generation(300, T140Block.from_text("A")),),
            primary=T140Block.from_text("B"),
        )
        self.assertEqual(
            packet.to_bytes().hex(" "),
            "80 64 00 0a 00 00 06 40 00 00 00 01 e2 04 b0 01 62 41 42",
        )

    def test_serializes_two_generations_oldest_first(self) -> None:
        packet = Rfc2198T140Packet(
            red_payload_type=100,
            t140_payload_type=98,
            sequence_number=11,
            timestamp=1900,
            ssrc=1,
            marker=False,
            redundant=(
                RedundantT140Generation(600, T140Block.from_text("A")),
                RedundantT140Generation(300, T140Block.from_text("B")),
            ),
            primary=T140Block.from_text("C"),
        )
        self.assertEqual(
            packet.to_bytes().hex(" "),
            "80 64 00 0b 00 00 07 6c 00 00 00 01 e2 09 60 01 e2 04 b0 01 62 41 42 43",
        )

    def test_empty_redundant_generation_is_encoded_with_zero_length(self) -> None:
        packet = Rfc2198T140Packet(
            red_payload_type=100,
            t140_payload_type=98,
            sequence_number=12,
            timestamp=2200,
            ssrc=1,
            marker=False,
            redundant=(RedundantT140Generation(300, T140Block(b"")),),
            primary=T140Block.from_text("A"),
        )
        self.assertIn(bytes.fromhex("e2 04 b0 00"), packet.to_bytes())

    def test_round_trip_preserves_generations(self) -> None:
        original = Rfc2198T140Packet(
            red_payload_type=100,
            t140_payload_type=98,
            sequence_number=13,
            timestamp=2500,
            ssrc=0xAABBCCDD,
            marker=True,
            redundant=(
                RedundantT140Generation(600, T140Block.from_text("é")),
                RedundantT140Generation(300, T140Block(b"")),
            ),
            primary=T140Block.from_text("Z"),
        )
        parsed = Rfc2198T140Packet.from_bytes(
            original.to_bytes(),
            expected_red_payload_type=100,
            expected_t140_payload_type=98,
        )
        self.assertEqual(parsed, original)

    def test_age_order_is_required(self) -> None:
        with self.assertRaises(ValueError):
            Rfc2198T140Packet(
                red_payload_type=100,
                t140_payload_type=98,
                sequence_number=1,
                timestamp=1,
                ssrc=1,
                marker=False,
                redundant=(
                    RedundantT140Generation(300, T140Block.from_text("A")),
                    RedundantT140Generation(600, T140Block.from_text("B")),
                ),
                primary=T140Block.from_text("C"),
            )

    def test_t140_and_red_payload_types_must_differ(self) -> None:
        with self.assertRaises(ValueError):
            Rfc2198T140Packet(
                red_payload_type=98,
                t140_payload_type=98,
                sequence_number=1,
                timestamp=1,
                ssrc=1,
                marker=False,
                redundant=(RedundantT140Generation(300, T140Block.from_text("A")),),
                primary=T140Block.from_text("B"),
            )

    def test_parser_rejects_mixed_inner_payload_types(self) -> None:
        raw = bytes.fromhex(
            "80 64 00 0a 00 00 06 40 00 00 00 01 e1 04 b0 01 62 41 42"
        )
        with self.assertRaises(InvalidRedT140Packet):
            Rfc2198T140Packet.from_bytes(raw)


if __name__ == "__main__":
    unittest.main()
