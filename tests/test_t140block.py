from __future__ import annotations

import unittest

from baudot_reference.t140block import (
    InvalidT140Block,
    T140Block,
    concatenate_blocks,
)


class T140BlockTests(unittest.TestCase):
    def test_empty_block_is_valid(self) -> None:
        block = T140Block(b"")
        self.assertTrue(block.is_empty)
        self.assertEqual(block.text, "")
        self.assertEqual(block.utf8_hex, "")

    def test_multibyte_character_is_preserved(self) -> None:
        block = T140Block.from_text("café")
        self.assertEqual(block.utf8_hex, "63 61 66 c3 a9")
        self.assertEqual(block.code_points, (0x63, 0x61, 0x66, 0xE9))

    def test_incomplete_utf8_character_is_rejected(self) -> None:
        with self.assertRaises(InvalidT140Block):
            T140Block(bytes.fromhex("e2 80"))

    def test_invalid_utf8_is_rejected(self) -> None:
        with self.assertRaises(InvalidT140Block):
            T140Block(bytes.fromhex("ff"))

    def test_code_point_constructor_rejects_surrogate(self) -> None:
        with self.assertRaises(ValueError):
            T140Block.from_code_points([0xD800])

    def test_concatenation_preserves_content_without_framing(self) -> None:
        combined = concatenate_blocks(
            [T140Block.from_text("A"), T140Block(b""), T140Block.from_text("é")]
        )
        self.assertEqual(combined.text, "Aé")
        self.assertEqual(combined.utf8_hex, "41 c3 a9")


if __name__ == "__main__":
    unittest.main()
