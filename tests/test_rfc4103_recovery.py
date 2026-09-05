from __future__ import annotations

import unittest

from baudot_reference.rfc2198 import RedundantT140Generation, Rfc2198T140Packet
from baudot_reference.rfc4103_recovery import (
    UnsupportedSequenceProgression,
    infer_redundant_sequence_numbers,
    recover_forward_gap,
)
from baudot_reference.t140block import T140Block


def packet(sequence: int, redundant: list[tuple[int, str]], primary: str) -> Rfc2198T140Packet:
    return Rfc2198T140Packet(
        red_payload_type=100,
        t140_payload_type=98,
        sequence_number=sequence,
        timestamp=sequence * 300,
        ssrc=1,
        marker=False,
        redundant=tuple(
            RedundantT140Generation(offset, T140Block.from_text(text))
            for offset, text in redundant
        ),
        primary=T140Block.from_text(primary),
    )


class Rfc4103RecoveryTests(unittest.TestCase):
    def test_infers_contiguous_redundant_sequence_numbers(self) -> None:
        current = packet(13, [(600, "A"), (300, "B")], "C")
        self.assertEqual(infer_redundant_sequence_numbers(current), (11, 12))

    def test_no_gap_emits_only_primary(self) -> None:
        current = packet(11, [(300, "old")], "B")
        recovered = recover_forward_gap(10, current)
        self.assertEqual([(item.sequence_number, item.block.text, item.source) for item in recovered], [(11, "B", "primary")])

    def test_one_missing_primary_is_recovered_from_redundancy(self) -> None:
        current = packet(12, [(300, "B")], "C")
        recovered = recover_forward_gap(10, current)
        self.assertEqual(
            [(item.sequence_number, item.block.text, item.source) for item in recovered],
            [(11, "B", "redundant"), (12, "C", "primary")],
        )

    def test_gap_larger_than_available_redundancy_gets_one_marker_per_missing_block(self) -> None:
        current = packet(14, [(300, "D")], "E")
        recovered = recover_forward_gap(10, current)
        self.assertEqual(
            [(item.sequence_number, item.block.text, item.source) for item in recovered],
            [
                (11, "�", "missing-marker"),
                (12, "�", "missing-marker"),
                (13, "D", "redundant"),
                (14, "E", "primary"),
            ],
        )

    def test_empty_redundant_block_recovers_without_false_missing_marker(self) -> None:
        current = packet(12, [(300, "")], "C")
        recovered = recover_forward_gap(10, current)
        self.assertEqual(recovered[0].sequence_number, 11)
        self.assertEqual(recovered[0].block.text, "")
        self.assertEqual(recovered[0].source, "redundant")

    def test_sequence_wraparound_is_supported(self) -> None:
        current = packet(1, [(600, "A"), (300, "B")], "C")
        recovered = recover_forward_gap(65534, current)
        self.assertEqual(
            [(item.sequence_number, item.block.text, item.source) for item in recovered],
            [(65535, "A", "redundant"), (0, "B", "redundant"), (1, "C", "primary")],
        )

    def test_first_packet_does_not_replay_historical_redundancy(self) -> None:
        current = packet(10, [(300, "old")], "new")
        recovered = recover_forward_gap(None, current)
        self.assertEqual([(item.block.text, item.source) for item in recovered], [("new", "primary")])

    def test_duplicate_packet_is_left_to_reordering_policy(self) -> None:
        current = packet(10, [(300, "old")], "new")
        with self.assertRaises(UnsupportedSequenceProgression):
            recover_forward_gap(10, current)


if __name__ == "__main__":
    unittest.main()
