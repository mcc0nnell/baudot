from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.reduce_tty_v18_wiretap_udp import reduce_run
from scripts.tty_pcmu_rtp import build_rtp_packet, write_rtp_sequence


class TtyWiretapReducerTests(unittest.TestCase):
    def make_run(self) -> Path:
        root = Path(tempfile.mkdtemp())
        (root / "source.txt").write_text("HELLO GA", encoding="ascii")

        packets = [
            build_rtp_packet(1000 + index, index * 160, bytes([0xFF]) * 160)
            for index in range(4)
        ]

        for name in ("minimodem-to-spandsp", "spandsp-to-minimodem"):
            case = root / name
            case.mkdir()
            write_rtp_sequence(case / "pre-route.rtpseq", packets)
            write_rtp_sequence(case / "post-route.rtpseq", packets)
            (case / "decoded.txt").write_text("HELLO GA", encoding="ascii")

        drop = root / "drop-one-negative-control"
        drop.mkdir()
        write_rtp_sequence(drop / "pre-route.rtpseq", packets)
        write_rtp_sequence(drop / "post-route.rtpseq", packets[:2] + packets[3:])
        (drop / "dropped-index.txt").write_text("2\n", encoding="ascii")
        (drop / "decoded.txt").write_text("HELLO GA", encoding="ascii")
        return root

    def test_clean_route_and_declared_drop_pass(self) -> None:
        result = reduce_run(self.make_run())
        self.assertEqual(result["terminalVerdict"], "pass")
        self.assertEqual(
            result["scenarios"]["BAUDOT-TTY-004"]["terminalVerdict"],
            "expected-impairment-detected",
        )

    def test_clean_route_mutation_fails(self) -> None:
        root = self.make_run()
        case = root / "minimodem-to-spandsp"
        packets = [
            build_rtp_packet(1000, 0, bytes([0xFF]) * 160),
            build_rtp_packet(1001, 160, bytes([0xFE]) * 160),
            build_rtp_packet(1002, 320, bytes([0xFF]) * 160),
            build_rtp_packet(1003, 480, bytes([0xFF]) * 160),
        ]
        write_rtp_sequence(case / "post-route.rtpseq", packets)
        result = reduce_run(root)
        self.assertEqual(result["terminalVerdict"], "fail")
        self.assertFalse(
            result["scenarios"]["BAUDOT-TTY-003"]["minimodemToSpanDsp"]["checks"][
                "datagramsPreservedExactly"
            ]
        )


if __name__ == "__main__":
    unittest.main()
