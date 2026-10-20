from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
import wave
from pathlib import Path

from scripts.reduce_tty_v18_pcmu_rtp import main as reduce_rtp
from scripts.tty_pcmu_rtp import bridge, linear16_to_ulaw, ulaw_to_linear16


def write_wav(path: Path, samples: list[int]) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        frames = bytearray()
        for sample in samples:
            frames.extend(int(sample).to_bytes(2, "little", signed=True))
        wav.writeframes(bytes(frames))


class TtyPcmuRtpTests(unittest.TestCase):
    def test_known_mulaw_points(self) -> None:
        self.assertEqual(linear16_to_ulaw(0), 0xFF)
        self.assertEqual(linear16_to_ulaw(1000), 0xCE)
        self.assertEqual(linear16_to_ulaw(-1000), 0x4E)
        self.assertEqual(ulaw_to_linear16(0xCE), 988)
        self.assertEqual(ulaw_to_linear16(0x4E), -988)

    def test_bridge_writes_rtp_and_reconstructed_wav(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.wav"
            rtp = root / "media.rtpseq"
            reconstructed = root / "after.wav"
            write_wav(source, [0, 1000, -1000] * 80)
            bridge(source, rtp, reconstructed)
            self.assertGreater(rtp.stat().st_size, 0)
            with wave.open(str(reconstructed), "rb") as wav:
                self.assertEqual(wav.getframerate(), 8000)
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.getnframes(), 320)

    def test_terminal_reducer_accepts_valid_synthetic_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.txt").write_text("HELLO GA", encoding="ascii")
            (root / "decoded-by-spandsp.txt").write_text("HELLO GA", encoding="ascii")
            (root / "decoded-by-minimodem.txt").write_text("HELLO GA", encoding="ascii")

            source_a = root / "a-source.wav"
            source_b = root / "b-source.wav"
            write_wav(source_a, [0] * 240)
            write_wav(source_b, [0] * 320)
            bridge(source_a, root / "minimodem-to-spandsp.rtpseq", root / "minimodem-after-pcmu.wav")
            bridge(source_b, root / "spandsp-to-minimodem.rtpseq", root / "spandsp-after-pcmu.wav")

            with contextlib.redirect_stdout(io.StringIO()):
                rc = reduce_rtp(["reduce", str(root)])
            self.assertEqual(rc, 0)
            verdict = json.loads((root / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(verdict["terminalVerdict"], "pass")
            self.assertTrue(verdict["checks"]["minimodemRtpTimestampProgression"])


if __name__ == "__main__":
    unittest.main()
