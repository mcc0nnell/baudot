from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from baudot_reference.federation_lab import reduce_sip_webrtc_boundary
from scripts.run_federation_boundary import live_sip_facts
from scripts.validate_fed002_browser import validate_browser_evidence

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "testkit" / "federation" / "BAUDOT-FED-002-sip-interpreter-webrtc-boundary.json"


class SipWebRtcFederationBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))

    def reduce(self, arm_id: str):
        return reduce_sip_webrtc_boundary(self.scenario, arm_id)

    @staticmethod
    def browser_evidence() -> dict:
        peer = {
            "connectionState": "connected",
            "iceConnectionState": "connected",
            "iceGatheringState": "complete",
            "signalingState": "stable",
            "sctpState": "connected",
            "dtlsState": "connected",
            "succeededCandidatePairs": [{"id": "pair-1", "state": "succeeded", "nominated": True}],
        }
        channel = {
            "label": "baudot-t140",
            "protocol": "t140",
            "ordered": True,
            "maxPacketLifeTime": None,
            "maxRetransmits": None,
            "negotiated": False,
            "readyState": "open",
        }
        return {
            "implementation": {"userAgent": "Mozilla/5.0 HeadlessChrome/fixture", "platform": "Linux"},
            "offerer": dict(peer),
            "answerer": dict(peer),
            "localDataChannel": dict(channel),
            "remoteDataChannel": dict(channel),
            "receivedText": "Hi",
            "receivedUtf8Hex": "48 69",
        }

    def test_control_is_ready_and_decodes_t140(self) -> None:
        result = self.reduce("control")
        self.assertEqual(result.terminal_verdict, "ready")
        self.assertEqual(result.failed_facts, ())
        self.assertEqual(result.decoded_text, "Hi")
        self.assertTrue(result.browser_boundary_profile_valid)
        self.assertTrue(result.browser_boundary_t140_valid)

    def test_sip_success_does_not_imply_browser_boundary_readiness(self) -> None:
        result = self.reduce("sip-only")
        self.assertTrue(result.sip_dialog_established)
        self.assertTrue(result.interpreter_ready)
        self.assertEqual(result.terminal_verdict, "not-ready")
        self.assertIn("browserBoundaryNegotiated", result.failed_facts)
        self.assertIn("browserBoundaryT140Observed", result.failed_facts)

    def test_browser_boundary_success_does_not_hide_interpreter_failure(self) -> None:
        result = self.reduce("interpreter-not-ready")
        self.assertTrue(result.browser_boundary_t140_valid)
        self.assertFalse(result.interpreter_ready)
        self.assertEqual(result.terminal_verdict, "not-ready")
        self.assertIn("interpreterReady", result.failed_facts)

    def test_wrong_datachannel_profile_is_separate_failure(self) -> None:
        result = self.reduce("wrong-datachannel-profile")
        self.assertTrue(result.sip_dialog_established)
        self.assertTrue(result.browser_boundary_t140_valid)
        self.assertFalse(result.browser_boundary_profile_valid)
        self.assertEqual(result.terminal_verdict, "not-ready")
        self.assertEqual(result.failed_facts, ("browserBoundaryProfileValid",))

    def test_invalid_t140_is_not_promoted_by_transport_success(self) -> None:
        result = self.reduce("invalid-t140")
        self.assertTrue(result.browser_boundary_negotiated)
        self.assertTrue(result.browser_boundary_t140_observed)
        self.assertFalse(result.browser_boundary_t140_valid)
        self.assertIsNone(result.decoded_text)
        self.assertEqual(result.terminal_verdict, "not-ready")
        self.assertEqual(result.failed_facts, ("browserBoundaryT140Valid",))

    def test_live_sip_evidence_is_joined_from_both_roles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "BAUDOT-FED-002" / "corr"
            (base / "caller").mkdir(parents=True)
            (base / "callee").mkdir(parents=True)
            (base / "caller" / "result.properties").write_text(
                "signaling.dialog.established=true\nmedia.probe.sent=true\n",
                encoding="utf-8",
            )
            (base / "callee" / "result.properties").write_text(
                "signaling.invite.received=true\n"
                "signaling.ack.received=true\n"
                "media.probe.received=true\n",
                encoding="utf-8",
            )
            facts = live_sip_facts(root, "BAUDOT-FED-002", "corr")
            self.assertTrue(all(facts.values()))
            self.assertEqual(
                set(facts),
                {
                    "callerDialogEstablished",
                    "callerMediaProbeSent",
                    "interpreterInviteReceived",
                    "interpreterAckReceived",
                    "interpreterMediaProbeReceived",
                },
            )

    def test_browser_evidence_requires_transport_and_t140_facts(self) -> None:
        result = validate_browser_evidence(self.browser_evidence())
        self.assertEqual(result.terminal_verdict, "ready")
        self.assertEqual(result.decoded_text, "Hi")
        self.assertEqual(result.failed_facts, ())

    def test_browser_evidence_does_not_infer_dtls_from_message_delivery(self) -> None:
        evidence = self.browser_evidence()
        evidence["answerer"]["dtlsState"] = "connecting"
        result = validate_browser_evidence(evidence)
        self.assertEqual(result.terminal_verdict, "not-ready")
        self.assertEqual(result.failed_facts, ("dtlsReady",))

    def test_browser_evidence_rejects_wrong_t140_channel(self) -> None:
        evidence = self.browser_evidence()
        evidence["remoteDataChannel"]["protocol"] = "chat"
        result = validate_browser_evidence(evidence)
        self.assertEqual(result.terminal_verdict, "not-ready")
        self.assertEqual(result.failed_facts, ("remoteChannelValid",))

    def test_scenario_preserves_real_browser_claim_gate(self) -> None:
        gates = set(self.scenario["requiredBeforeProven"])
        self.assertIn("one repeatable run with a real browser RTCPeerConnection", gates)
        self.assertIn("SCTP data-channel establishment observed in the browser implementation", gates)
        self.assertIn("DTLS and ICE state preserved as evidence rather than inferred from application success", gates)
        self.assertIn("that the reference right boundary is a browser", set(self.scenario["claimBoundary"]["doesNotEstablish"]))


if __name__ == "__main__":
    unittest.main()
