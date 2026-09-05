from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
import wave
from pathlib import Path

from scripts.reduce_tty_v18_cross_oracle import main


def write_wav(path: Path, *, rate: int = 8000) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * 160)


class TtyCrossOracleReducerTests(unittest.TestCase):
    def make_bundle(self, root: Path, decoded_by_minimodem: str = "HELLO GA") -> None:
        (root / "source.txt").write_text("HELLO GA", encoding="ascii")
        (root / "decoded-by-spandsp.txt").write_text("HELLO GA", encoding="ascii")
        (root / "decoded-by-minimodem.txt").write_text(decoded_by_minimodem, encoding="ascii")
        write_wav(root / "minimodem-generated.wav")
        write_wav(root / "spandsp-generated.wav")

    def test_matching_cross_oracle_bundle_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root)
            with contextlib.redirect_stdout(io.StringIO()):
                rc = main(["reduce", str(root)])
            self.assertEqual(rc, 0)
            verdict = json.loads((root / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(verdict["terminalVerdict"], "pass")
            self.assertTrue(verdict["checks"]["independentOracleAgreement"])

    def test_decoder_disagreement_fails_terminal_reduction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root, decoded_by_minimodem="HELLO")
            with contextlib.redirect_stdout(io.StringIO()):
                rc = main(["reduce", str(root)])
            self.assertEqual(rc, 1)
            verdict = json.loads((root / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(verdict["terminalVerdict"], "fail")
            self.assertFalse(verdict["checks"]["independentOracleAgreement"])


if __name__ == "__main__":
    unittest.main()
