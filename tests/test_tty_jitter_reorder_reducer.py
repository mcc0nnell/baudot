from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.reduce_tty_v18_jitter_reorder import reduce_run
from scripts.tty_pcmu_rtp import build_rtp_packet, write_rtp_sequence


class TtyJitterReorderReducerTests(unittest.TestCase):
    def make_run(self) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "source.txt").write_text("HELLO GA", encoding="ascii")
        case = root / "jitter-reorder-recovery"
        case.mkdir()

        packets = [
            build_rtp_packet(1000 + index, index * 160, bytes([0xFF - index]) * 160)
            for index in range(4)
        ]
        reordered = [packets[0], packets[2], packets[1], packets[3]]
        write_rtp_sequence(case / "pre-route.rtpseq", packets)
        write_rtp_sequence(case / "post-route.rtpseq", reordered)
        write_rtp_sequence(case / "resequenced.rtpseq", packets)
        (case / "delayed-index.txt").write_text("1\n", encoding="ascii")
        (case / "delay-ms.txt").write_text("35\n", encoding="ascii")
        (case / "raw-reconstruct.exit-code.txt").write_text("1\n", encoding="ascii")
        (case / "decoded.txt").write_text("HELLO GA", encoding="ascii")
        (case / "sender.json").write_text(
            json.dumps(
                {
                    "sentSequenceNumbers": [1000, 1002, 1001, 1003],
                    "delayByIndexMs": {"1": 35.0},
                }
            ),
            encoding="utf-8",
        )
        (case / "receiver.json").write_text(
            json.dumps(
                {
                    "sequenceNumbers": [1000, 1002, 1001, 1003],
                    "arrivalOffsetsMs": [0.0, 20.0, 35.0, 40.0],
                    "interarrivalMs": [20.0, 15.0, 5.0],
                }
            ),
            encoding="utf-8",
        )
        (case / "resequence.json").write_text(
            json.dumps({"changedOrder": True}),
            encoding="utf-8",
        )
        return root

    def test_declared_reorder_and_recovery_pass(self) -> None:
        result = reduce_run(self.make_run())
        self.assertEqual(result["terminalVerdict"], "pass")
        self.assertTrue(result["checks"]["receiverObservedFollowingPacketFirst"])
        self.assertTrue(result["checks"]["resequencedStreamRestoredExactly"])

    def test_wrong_resequence_fails(self) -> None:
        root = self.make_run()
        case = root / "jitter-reorder-recovery"
        packets = [
            build_rtp_packet(1000 + index, index * 160, bytes([0xFF - index]) * 160)
            for index in range(4)
        ]
        write_rtp_sequence(case / "resequenced.rtpseq", [packets[0], packets[2], packets[1], packets[3]])
        result = reduce_run(root)
        self.assertEqual(result["terminalVerdict"], "fail")
        self.assertFalse(result["checks"]["resequencedStreamRestoredExactly"])


if __name__ == "__main__":
    unittest.main()
