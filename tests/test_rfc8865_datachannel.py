from __future__ import annotations

import unittest

from baudot_reference.rfc8865 import (
    DEFAULT_CPS,
    DEFAULT_TRANSMISSION_INTERVAL_MS,
    InvalidT140DataChannelMessage,
    T140DataChannelMessage,
    T140DataChannelProfile,
    replacement_marker_for_possible_loss,
)
from baudot_reference.t140block import T140Block


class Rfc8865DataChannelTests(unittest.TestCase):
    def test_default_profile_is_t140_reliable_and_ordered(self) -> None:
        profile = T140DataChannelProfile()
        self.assertEqual(profile.subprotocol, "t140")
        self.assertTrue(profile.reliable)
        self.assertTrue(profile.ordered)
        self.assertEqual(profile.transmission_interval_ms, DEFAULT_TRANSMISSION_INTERVAL_MS)
        self.assertEqual(profile.cps, DEFAULT_CPS)
        self.assertEqual(DEFAULT_TRANSMISSION_INTERVAL_MS, 300)
        self.assertEqual(DEFAULT_CPS, 30)

    def test_unreliable_or_unordered_profile_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            T140DataChannelProfile(reliable=False)
        with self.assertRaises(ValueError):
            T140DataChannelProfile(ordered=False)

    def test_one_message_can_carry_multiple_blocks(self) -> None:
        message = T140DataChannelMessage.from_blocks(
            [T140Block.from_text("A"), T140Block.from_text("é")]
        )
        self.assertEqual(message.utf8_hex, "41 c3 a9")
        self.assertEqual(message.text, "Aé")

    def test_empty_block_can_be_present_without_extra_framing(self) -> None:
        message = T140DataChannelMessage.from_blocks(
            [T140Block.from_text("A"), T140Block(b""), T140Block.from_text("B")]
        )
        self.assertEqual(message.utf8_hex, "41 42")

    def test_received_message_recovers_content_not_sender_block_boundaries(self) -> None:
        message = T140DataChannelMessage.from_bytes(bytes.fromhex("41 c3 a9"))
        self.assertEqual(message.aggregate_block, T140Block.from_text("Aé"))

    def test_invalid_utf8_message_is_rejected(self) -> None:
        with self.assertRaises(InvalidT140DataChannelMessage):
            T140DataChannelMessage.from_bytes(bytes.fromhex("e2 80"))

    def test_missing_text_marker_is_t140_replacement_character(self) -> None:
        self.assertEqual(replacement_marker_for_possible_loss().utf8_hex, "ef bf bd")


if __name__ == "__main__":
    unittest.main()
