from decimal import Decimal
import unittest

from baudot_reference.fund_runtime import (
    FundEvent,
    FundInvariantViolation,
    FundRuntime,
)


D = Decimal


class FundRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events = (
            FundEvent(
                event_id="assessment-001",
                event_type=FundRuntime.ASSESSMENT_ISSUED,
                amount=D("1200.00"),
                subject_id="contributor-alpha",
                policy_version="fy2026-27",
                source_refs=("synthetic-form-499a:alpha",),
            ),
            FundEvent(
                event_id="receipt-001",
                event_type=FundRuntime.CONTRIBUTION_RECEIVED,
                amount=D("1200.00"),
                subject_id="contributor-alpha",
                policy_version="fy2026-27",
                causes=("assessment-001",),
            ),
            FundEvent(
                event_id="claim-001",
                event_type=FundRuntime.CLAIM_APPROVED,
                amount=D("875.25"),
                subject_id="provider-bravo",
                policy_version="fy2026-27-vrs-rate-1",
                source_refs=("synthetic-provider-claim:bravo:001",),
            ),
            FundEvent(
                event_id="payment-001",
                event_type=FundRuntime.PAYMENT_POSTED,
                amount=D("875.25"),
                subject_id="provider-bravo",
                policy_version="fy2026-27-vrs-rate-1",
                causes=("claim-001",),
            ),
        )

    def test_replay_is_byte_stable_at_hash_boundary(self) -> None:
        first = FundRuntime.replay(self.events)
        second = FundRuntime.replay(self.events)
        self.assertEqual(first.state_hash, second.state_hash)
        self.assertEqual(first.receipts, second.receipts)
        self.assertEqual(
            first.state["totals"],
            {
                "assessed": "1200.00",
                "received": "1200.00",
                "approvedClaims": "875.25",
                "paid": "875.25",
                "receivablesOutstanding": "0.00",
                "providerPayablesOutstanding": "0.00",
                "syntheticCashDelta": "324.75",
            },
        )

    def test_receipts_chain_pre_and_post_state_hashes(self) -> None:
        result = FundRuntime.replay(self.events)
        for previous, current in zip(result.receipts, result.receipts[1:]):
            self.assertEqual(previous.post_state_hash, current.pre_state_hash)
        self.assertEqual(result.receipts[-1].post_state_hash, result.state_hash)

    def test_payment_has_reachable_claim_provenance(self) -> None:
        lineage = FundRuntime.trace_to_roots("payment-001", self.events)
        self.assertEqual(lineage, ("claim-001", "payment-001"))

    def test_receipt_has_reachable_assessment_provenance(self) -> None:
        lineage = FundRuntime.trace_to_roots("receipt-001", self.events)
        self.assertEqual(lineage, ("assessment-001", "receipt-001"))

    def test_duplicate_event_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(FundInvariantViolation, "duplicate event id"):
            FundRuntime.replay((*self.events, self.events[-1]))

    def test_orphan_payment_is_rejected(self) -> None:
        orphan = FundEvent(
            event_id="payment-orphan",
            event_type=FundRuntime.PAYMENT_POSTED,
            amount=D("10.00"),
            subject_id="provider-bravo",
            policy_version="fy2026-27-vrs-rate-1",
            causes=("claim-missing",),
        )
        with self.assertRaisesRegex(FundInvariantViolation, "missing causation event"):
            FundRuntime.replay((orphan,))

    def test_payment_cannot_exceed_approved_claim(self) -> None:
        claim = self.events[2]
        excessive_payment = FundEvent(
            event_id="payment-too-large",
            event_type=FundRuntime.PAYMENT_POSTED,
            amount=D("875.26"),
            subject_id="provider-bravo",
            policy_version="fy2026-27-vrs-rate-1",
            causes=(claim.event_id,),
        )
        with self.assertRaisesRegex(FundInvariantViolation, "exceeds approved claim"):
            FundRuntime.replay((claim, excessive_payment))

    def test_receipt_cannot_exceed_assessment(self) -> None:
        assessment = self.events[0]
        excessive_receipt = FundEvent(
            event_id="receipt-too-large",
            event_type=FundRuntime.CONTRIBUTION_RECEIVED,
            amount=D("1200.01"),
            subject_id="contributor-alpha",
            policy_version="fy2026-27",
            causes=(assessment.event_id,),
        )
        with self.assertRaisesRegex(FundInvariantViolation, "exceeds outstanding assessment"):
            FundRuntime.replay((assessment, excessive_receipt))

    def test_root_events_require_source_evidence(self) -> None:
        claim = FundEvent(
            event_id="claim-no-source",
            event_type=FundRuntime.CLAIM_APPROVED,
            amount=D("10.00"),
            subject_id="provider-bravo",
            policy_version="fy2026-27-vrs-rate-1",
        )
        with self.assertRaisesRegex(FundInvariantViolation, "requires at least one source reference"):
            FundRuntime.replay((claim,))

    def test_sub_cent_money_is_rejected(self) -> None:
        assessment = FundEvent(
            event_id="assessment-sub-cent",
            event_type=FundRuntime.ASSESSMENT_ISSUED,
            amount=D("1.001"),
            subject_id="contributor-alpha",
            policy_version="fy2026-27",
            source_refs=("synthetic-form-499a:alpha",),
        )
        with self.assertRaisesRegex(FundInvariantViolation, "exact cents"):
            FundRuntime.replay((assessment,))


if __name__ == "__main__":
    unittest.main()
