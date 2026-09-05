from __future__ import annotations

import json
from pathlib import Path
import unittest

from baudot_reference.gateway import run_gateway_contract

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "testkit" / "gateways" / "rfc4103-rfc8865-equivalence-v2.json"


class GatewayEquivalenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.results = {result.trial_id: result for result in run_gateway_contract(cls.contract)}

    def test_contract_is_runnable_not_proven(self) -> None:
        self.assertEqual(self.contract["version"], 2)
        self.assertEqual(self.contract["status"], "runnable")
        self.assertEqual(self.contract["execution"]["kind"], "deterministic-reference-harness")

    def test_all_declared_trials_execute_and_pass(self) -> None:
        declared = {trial["id"] for trial in self.contract["trials"]}
        self.assertEqual(set(self.results), declared)
        self.assertTrue(all(result.verdict == "pass" for result in self.results.values()))

    def test_normal_paths_preserve_presentation(self) -> None:
        self.assertEqual(self.results["normal-rtp-to-datachannel"].presentation, "Hi\né")
        self.assertEqual(self.results["normal-datachannel-to-rtp"].presentation, "AC")

    def test_recovered_rtp_loss_does_not_leak_marker(self) -> None:
        result = self.results["recovered-rtp-loss-does-not-leak-marker"]
        self.assertEqual(result.presentation, "ABC")
        self.assertEqual(result.missing_text_markers, 0)
        self.assertTrue(any(item["source"] == "redundant" for item in result.normalized_trace))
        self.assertFalse(any(item["source"] == "missing-marker" for item in result.normalized_trace))

    def test_unrecovered_rtp_loss_becomes_exactly_one_marker(self) -> None:
        result = self.results["unrecovered-rtp-loss-becomes-marker"]
        self.assertEqual(result.presentation, "A�C")
        self.assertEqual(result.missing_text_markers, 1)
        self.assertEqual(
            sum(item["source"] == "missing-marker" for item in result.normalized_trace),
            1,
        )

    def test_datachannel_reestablishment_preserves_possible_loss_marker(self) -> None:
        result = self.results["datachannel-reestablishment-suspected-loss"]
        self.assertEqual(result.presentation, "A�C")
        self.assertEqual(result.missing_text_markers, 1)
        self.assertEqual(result.source_trace[0]["event"], "RFC8865_REESTABLISHED_MESSAGE")

    def test_empty_rtp_block_is_not_loss(self) -> None:
        result = self.results["empty-block-is-not-loss"]
        self.assertEqual(result.presentation, "AB")
        self.assertEqual(result.missing_text_markers, 0)
        self.assertTrue(any(item["t140Hex"] == "" for item in result.normalized_trace))


if __name__ == "__main__":
    unittest.main()
