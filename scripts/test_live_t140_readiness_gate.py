from __future__ import annotations

import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest

from baudot_reference.rfc4103 import PrimaryT140RtpPacket
from baudot_reference.t140block import T140Block
from scripts.live_t140_readiness_gate import observe


def packet(text: bytes, *, payload_type: int = 98, sequence: int = 1) -> bytes:
    return PrimaryT140RtpPacket(
        payload_type=payload_type,
        sequence_number=sequence,
        timestamp=1000 + sequence,
        ssrc=0x42415544,
        marker=sequence == 1,
        block=T140Block(text),
    ).to_bytes()


class LiveT140ReadinessGateTests(unittest.TestCase):
    def run_gate(self, datagrams: list[bytes], *, expected_text: str = "H", timeout_ms: int = 500):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary)
            ready = evidence / "rtt-ready.json"
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
                receiver.bind(("127.0.0.1", 0))
                port = receiver.getsockname()[1]
                result: dict[str, int] = {}

                def target() -> None:
                    result["code"] = observe(
                        receiver,
                        evidence_dir=evidence,
                        ready_file=ready,
                        expected_text=expected_text,
                        timeout_ms=timeout_ms,
                    )

                thread = threading.Thread(target=target)
                thread.start()
                time.sleep(0.03)
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    for content in datagrams:
                        sender.sendto(content, ("127.0.0.1", port))
                        time.sleep(0.01)
                thread.join(2)
                self.assertFalse(thread.is_alive())

            files = {
                path.name: path.read_bytes()
                for path in evidence.iterdir()
                if path.is_file()
            }
            return result["code"], files

    def test_valid_h_publishes_atomic_readiness(self) -> None:
        code, files = self.run_gate([packet(b"H")])
        self.assertEqual(0, code)
        ready = json.loads(files["rtt-ready.json"])
        self.assertTrue(ready["rttReady"])
        self.assertEqual("baudot-reference", ready["semanticAuthority"])
        self.assertEqual("H", ready["firstT140Text"])
        self.assertEqual(98, ready["payloadType"])
        self.assertIn("manifest.sha256", files)

    def test_empty_block_waits_for_first_nonempty_text(self) -> None:
        code, files = self.run_gate([
            packet(b"", sequence=1),
            packet(b"H", sequence=2),
        ])
        self.assertEqual(0, code)
        result = json.loads(files["result.json"])
        self.assertEqual(2, result["packetCount"])
        self.assertEqual("rtt-datagram-002.bin", result["readiness"]["packet"])

    def test_wrong_text_never_publishes_readiness(self) -> None:
        code, files = self.run_gate([packet(b"X")])
        self.assertEqual(3, code)
        self.assertNotIn("rtt-ready.json", files)
        result = json.loads(files["result.json"])
        self.assertFalse(result["rttReady"])
        self.assertEqual("TEXT_MISMATCH", result["result"])

    def test_malformed_packet_is_preserved_but_not_authoritative(self) -> None:
        code, files = self.run_gate([b"not-rtp", packet(b"H", sequence=2)])
        self.assertEqual(0, code)
        self.assertEqual(b"not-rtp", files["rtt-datagram-001.bin"])
        events = files["events.jsonl"].decode("utf-8")
        self.assertIn("rtt.readiness.datagram_rejected", events)
        self.assertIn("rtt.readiness.established", events)

    def test_wrong_payload_is_preserved_then_valid_pt98_can_qualify(self) -> None:
        code, files = self.run_gate([
            packet(b"H", payload_type=97, sequence=1),
            packet(b"H", payload_type=98, sequence=2),
        ])
        self.assertEqual(0, code)
        events = files["events.jsonl"].decode("utf-8")
        self.assertIn("unexpected payload type 97", events)
        ready = json.loads(files["rtt-ready.json"])
        self.assertEqual(98, ready["payloadType"])

    def test_timeout_writes_no_readiness_token(self) -> None:
        code, files = self.run_gate([], timeout_ms=100)
        self.assertEqual(4, code)
        self.assertNotIn("rtt-ready.json", files)
        result = json.loads(files["result.json"])
        self.assertEqual("TIMEOUT", result["result"])
        self.assertFalse(result["rttReady"])


if __name__ == "__main__":
    unittest.main()
