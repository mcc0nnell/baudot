from __future__ import annotations

import unittest

from baudot_reference.tty import (
    InvalidTtyCode,
    US_WEITBRECHT_4545,
    frame_5bit_code,
    frame_5bit_codes,
)


class TtyReferenceTests(unittest.TestCase):
    def test_us_weibreitbrecht_profile_is_45_45_baud(self) -> None:
        self.assertEqual(US_WEITBRECHT_4545.baud, 45.45)
        self.assertEqual(US_WEITBRECHT_4545.mark_hz, 1400.0)
        self.assertEqual(US_WEITBRECHT_4545.space_hz, 1800.0)
        self.assertEqual(US_WEITBRECHT_4545.data_bits, 5)
        self.assertEqual(US_WEITBRECHT_4545.stop_bits, 2)
        self.assertEqual(US_WEITBRECHT_4545.bit_order, "lsb-first")

    def test_frame_is_start_five_lsb_first_data_and_two_stop_bits(self) -> None:
        self.assertEqual(frame_5bit_code(0b10101), (0, 1, 0, 1, 0, 1, 1, 1))

    def test_multiple_codes_are_concatenated_without_reinterpreting_symbols(self) -> None:
        self.assertEqual(
            frame_5bit_codes([0x00, 0x1F]),
            (0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1),
        )

    def test_code_outside_five_bits_is_rejected(self) -> None:
        with self.assertRaises(InvalidTtyCode):
            frame_5bit_code(0x20)

    def test_nominal_frame_duration_is_derived_from_profile(self) -> None:
        expected = 8 / 45.45
        self.assertAlmostEqual(US_WEITBRECHT_4545.nominal_code_seconds, expected)


if __name__ == "__main__":
    unittest.main()
