from decimal import Decimal
import unittest

from fund_runtime import FundEvent, append_event, fold_events


def event(seq: int, event_type: str, tx: str, **kwargs) -> FundEvent:
    return FundEvent(
        seq=seq,
        event_type=event_type,  # type: ignore[arg-type]
        transaction_id=tx,
        actor_id=kwargs.pop("actor_id", "synthetic-operator"),
        effective_date=kwargs.pop("effective_date", "2026-07-01"),
        **kwargs,
    )


def configured() -> list[FundEvent]:
    return [
        event(
            1,
            "RUN_CONFIGURED",
            "run-2026-27",
            entity_id="2026-27",
            policy_hash="sha256:policy-2026-27",
        )
    ]


class FundRuntimeTests(unittest.TestCase):
    def test_end_to_end_assessment_receipt_claim_and_disbursement_fold(self):
        events = configured() + [
            event(2, "CONTRIBUTOR_ASSESSED", "assessment-1", entity_id="contributor-a", amount=Decimal("1000")),
            event(3, "CONTRIBUTOR_RECEIPT_RECORDED", "receipt-1", entity_id="contributor-a", amount=Decimal("1000")),
            event(4, "PROVIDER_CLAIM_APPROVED", "claim-1", entity_id="provider-a", amount=Decimal("600")),
            event(5, "PROVIDER_DISBURSEMENT_POSTED", "payment-1", entity_id="provider-a", amount=Decimal("600")),
        ]

        state = fold_events(events)

        self.assertEqual(state.program_year, "2026-27")
        self.assertEqual(state.cash, Decimal("400"))
        self.assertEqual(state.contributor_receivable, Decimal("0"))
        self.assertEqual(state.provider_payable, Decimal("0"))
        self.assertEqual(state.contribution_revenue, Decimal("1000"))
        self.assertEqual(state.provider_compensation_expense, Decimal("600"))
        self.assertEqual(state.last_seq, 5)

    def test_duplicate_transaction_is_idempotent_on_append(self):
        events = configured()
        claim = event(2, "PROVIDER_CLAIM_APPROVED", "claim-1", entity_id="provider-a", amount=Decimal("600"))

        events, state, applied = append_event(events, claim)
        replayed_events, replayed_state, replayed = append_event(events, claim)

        self.assertTrue(applied)
        self.assertFalse(replayed)
        self.assertEqual(len(replayed_events), 2)
        self.assertEqual(replayed_state, state)
        self.assertEqual(replayed_state.provider_payable, Decimal("600"))

    def test_fold_defensively_ignores_duplicate_transaction_id(self):
        events = configured() + [
            event(2, "CONTRIBUTOR_ASSESSED", "assessment-1", entity_id="contributor-a", amount=Decimal("100")),
            event(3, "CONTRIBUTOR_ASSESSED", "assessment-1", entity_id="contributor-a", amount=Decimal("100")),
        ]

        state = fold_events(events)

        self.assertEqual(state.contributor_receivable, Decimal("100"))
        self.assertEqual(state.contribution_revenue, Decimal("100"))

    def test_reversal_preserves_original_transaction_and_negates_effect(self):
        events = configured() + [
            event(2, "PROVIDER_CLAIM_APPROVED", "claim-1", entity_id="provider-a", amount=Decimal("600")),
            event(3, "TRANSACTION_REVERSED", "reversal-1", target_transaction_id="claim-1"),
        ]

        state = fold_events(events)

        self.assertEqual(state.provider_payable, Decimal("0"))
        self.assertEqual(state.provider_compensation_expense, Decimal("0"))
        self.assertIn("claim-1", state.transaction_effects)
        self.assertIn("reversal-1", state.transaction_effects)
        self.assertIn("claim-1", state.reversed_transactions)

    def test_same_transaction_cannot_be_reversed_twice(self):
        events = configured() + [
            event(2, "PROVIDER_CLAIM_APPROVED", "claim-1", entity_id="provider-a", amount=Decimal("600")),
            event(3, "TRANSACTION_REVERSED", "reversal-1", target_transaction_id="claim-1"),
        ]

        with self.assertRaisesRegex(ValueError, "already reversed"):
            append_event(events, event(4, "TRANSACTION_REVERSED", "reversal-2", target_transaction_id="claim-1"))

    def test_policy_hash_mismatch_is_rejected(self):
        events = configured()

        with self.assertRaisesRegex(ValueError, "policy_hash"):
            append_event(
                events,
                event(
                    2,
                    "CONTRIBUTOR_ASSESSED",
                    "assessment-1",
                    entity_id="contributor-a",
                    amount=Decimal("100"),
                    policy_hash="sha256:wrong-policy",
                ),
            )

    def test_closed_period_rejects_new_business_event(self):
        events = configured() + [
            event(2, "ACCOUNTING_PERIOD_CLOSED", "close-2026-07", entity_id="2026-07-31"),
        ]

        with self.assertRaisesRegex(ValueError, "closed accounting period"):
            append_event(
                events,
                event(
                    3,
                    "CONTRIBUTOR_ASSESSED",
                    "late-assessment",
                    entity_id="contributor-a",
                    amount=Decimal("100"),
                    effective_date="2026-07-15",
                ),
            )

    def test_program_year_advance_changes_policy_binding_without_erasing_balances(self):
        events = configured() + [
            event(2, "CONTRIBUTOR_ASSESSED", "assessment-1", entity_id="contributor-a", amount=Decimal("100")),
            event(
                3,
                "PROGRAM_YEAR_ADVANCED",
                "advance-2027-28",
                entity_id="2027-28",
                policy_hash="sha256:policy-2027-28",
                effective_date="2027-07-01",
            ),
        ]

        state = fold_events(events)

        self.assertEqual(state.program_year, "2027-28")
        self.assertEqual(state.policy_hash, "sha256:policy-2027-28")
        self.assertEqual(state.contributor_receivable, Decimal("100"))


if __name__ == "__main__":
    unittest.main()
