from __future__ import annotations

import unittest

from baudot_reference import BaselineSemanticGap, apply_t140_baseline, encode_utf8


class T140ReferenceTests(unittest.TestCase):
    def test_utf8_encoding_preserves_latin1_supplement(self) -> None:
        self.assertEqual(encode_utf8([0x63, 0x61, 0x66, 0x00E9]), b"caf\xc3\xa9")

    def test_backspace_erases_preceding_baseline_character(self) -> None:
        result = apply_t140_baseline([0x41, 0x42, 0x0008, 0x43])
        self.assertEqual(result.display_text, "AC")

    def test_line_separator_and_crlf_have_same_baseline_presentation(self) -> None:
        preferred = apply_t140_baseline([0x41, 0x2028, 0x42])
        supported = apply_t140_baseline([0x41, 0x000D, 0x000A, 0x42])
        self.assertEqual(preferred.as_dict(), supported.as_dict())
        self.assertEqual(preferred.line_breaks, 1)

    def test_bell_alerts_without_adding_visible_text(self) -> None:
        result = apply_t140_baseline([0x41, 0x0007, 0x42])
        self.assertEqual(result.display_text, "AB")
        self.assertEqual(result.alerts, 1)

    def test_missing_text_marker_is_preserved(self) -> None:
        result = apply_t140_baseline([0x41, 0xFFFD, 0x42])
        self.assertEqual(result.display_text, "A\uFFFDB")
        self.assertEqual(result.missing_text_markers, 1)

    def test_isolated_cr_is_a_declared_semantic_gap(self) -> None:
        with self.assertRaises(BaselineSemanticGap):
            apply_t140_baseline([0x41, 0x000D, 0x42])

    def test_isolated_lf_is_a_declared_semantic_gap(self) -> None:
        with self.assertRaises(BaselineSemanticGap):
            apply_t140_baseline([0x41, 0x000A, 0x42])

    def test_backspace_without_preceding_baseline_text_is_a_gap(self) -> None:
        with self.assertRaises(BaselineSemanticGap):
            apply_t140_baseline([0x0008])


if __name__ == "__main__":
    unittest.main()
