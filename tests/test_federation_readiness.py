from __future__ import annotations

import json
from pathlib import Path
import unittest

from baudot_reference.federation import reduce_federated_session

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "testkit" / "federation" / "BAUDOT-FED-001-three-party-accessibility-session.json"


class FederationReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))

    def reduce(self, arm_id: str):
        return reduce_federated_session(self.scenario, arm_id)

    def test_control_is_ready(self) -> None:
        result = self.reduce("control")
        self.assertTrue(result.session_connected)
        self.assertTrue(result.accessibility_ready)
        self.assertTrue(result.security_claim_valid)
        self.assertEqual(result.terminal_verdict, "ready")
        self.assertEqual(result.media_termination_points, ("interpreter",))

    def test_connected_does_not_imply_interpreter_readiness(self) -> None:
        result = self.reduce("connected-interpreter-not-ready")
        self.assertTrue(result.session_connected)
        self.assertFalse(result.accessibility_ready)
        self.assertEqual(result.unmet_readiness, ("interpreterReady",))
        self.assertEqual(result.terminal_verdict, "not-ready")

    def test_missing_interpreter_is_explicit_failure(self) -> None:
        result = self.reduce("missing-interpreter")
        self.assertTrue(result.session_connected)
        self.assertEqual(result.missing_participants, ("interpreter",))
        self.assertFalse(result.accessibility_ready)

    def test_required_capability_is_bound_to_participant(self) -> None:
        result = self.reduce("missing-destination-video")
        self.assertEqual(result.missing_capabilities, ("destination:video",))
        self.assertFalse(result.accessibility_ready)

    def test_media_termination_rejects_unqualified_e2ee_claim(self) -> None:
        result = self.reduce("false-unqualified-e2ee")
        self.assertTrue(result.accessibility_ready)
        self.assertFalse(result.security_claim_valid)
        self.assertEqual(result.media_termination_points, ("interpreter",))
        self.assertEqual(result.terminal_verdict, "not-ready")

    def test_provider_and_platform_labels_do_not_change_semantics(self) -> None:
        control = self.reduce("control")
        variant = self.reduce("provider-label-variant")
        self.assertEqual(control.accessibility_ready, variant.accessibility_ready)
        self.assertEqual(control.security_claim_valid, variant.security_claim_valid)
        self.assertEqual(control.terminal_verdict, variant.terminal_verdict)


if __name__ == "__main__":
    unittest.main()
