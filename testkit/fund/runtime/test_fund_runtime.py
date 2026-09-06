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

    def test_duplicate_delivery_is_idempotent_at_append_boundary(self):
        events = configured()
        claim = event(2, "PROVIDER_CLAIM_APPROVED", "claim-1", entity_id="provider-a", amount=Decimal("600"))

        events, state, applied = append_event(events, claim)
        replayed_events, replayed_state, replayed = append_event(events, claim)

        self.assertTrue(applied)
        self.assertFalse(replayed)
        self.assertEqual(len(replayed_events), 2)
        self.assertEqual(replayed_state, state)
        self.assertEqual(replayed_state.provider_payable, Decimal("600"))

    def test_duplicate_transaction_in_persisted_log_fails_closed(self):
        events = configured() + [
            event(2, "CONTRIBUTOR_ASSESSED", "assessment-1", entity_id="contributor-a", amount=Decimal("100")),
            event(3, "CONTRIBUTOR_ASSESSED", "assessment-1", entity_id="contributor-a", amount=Decimal("100")),
        ]

        with self.assertRaisesRegex(ValueError, "duplicate transaction_id"):
            fold_events(events)

    def test_sequence_gap_in_persisted_log_fails_closed(self):
        events = configured() + [
            event(3, "CONTRIBUTOR_ASSESSED", "assessment-1", entity_id="contributor-a", amount=Decimal("100")),
        ]

        with self.assertRaisesRegex(ValueError, "sequence must be contiguous"):
            fold_events(events)

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
        self.assertEqual(state.transaction_dates["reversal-1"], state.transaction_dates["claim-1"])

    def test_same_transaction_cannot_be_reversed_twice(self):
        events = configured() + [
            event(2, "PROVIDER_CLAIM_APPROVED", "claim-1", entity_id="provider-a", amount=Decimal("600")),
            event(3, "TRANSACTION_REVERSED", "reversal-1", target_transaction_id="claim-1"),
        ]

        with self.assertRaisesRegex(ValueError, "already reversed"):
            append_event(events, event(4, "TRANSACTION_REVERSED", "reversal-2", target_transaction_id="claim-1"))

    def test_closed_period_transaction_cannot_use_fineract_reversal(self):
        events = configured() + [
            event(
                2,
                "PROVIDER_CLAIM_APPROVED",
                "claim-1",
                entity_id="provider-a",
                amount=Decimal("600"),
                effective_date="2026-07-15",
            ),
            event(3, "ACCOUNTING_PERIOD_CLOSED", "close-2026-07", entity_id="2026-07-31", effective_date="2026-08-01"),
        ]

        with self.assertRaisesRegex(ValueError, "compensating adjustment"):
            append_event(
                events,
                event(
                    4,
                    "TRANSACTION_REVERSED",
                    "reversal-1",
                    target_transaction_id="claim-1",
                    effective_date="2026-08-01",
                ),
            )

    def test_reversal_effective_date_must_match_original_journal_date(self):
        events = configured() + [
            event(
                2,
                "PROVIDER_CLAIM_APPROVED",
                "claim-1",
                entity_id="provider-a",
                amount=Decimal("600"),
                effective_date="2026-07-15",
            ),
        ]

        with self.assertRaisesRegex(ValueError, "must equal target transaction date"):
            append_event(
                events,
                event(
                    3,
                    "TRANSACTION_REVERSED",
                    "reversal-1",
                    target_transaction_id="claim-1",
                    effective_date="2026-07-20",
                ),
            )

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
            event(2, "ACCOUNTING_PERIOD_CLOSED", "close-2026-07", entity_id="2026-07-31", effective_date="2026-08-01"),
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

    def test_accounting_closure_cannot_move_backward(self):
        events = configured() + [
            event(2, "ACCOUNTING_PERIOD_CLOSED", "close-2026-07", entity_id="2026-07-31", effective_date="2026-08-01"),
        ]

        with self.assertRaisesRegex(ValueError, "must advance"):
            append_event(
                events,
                event(3, "ACCOUNTING_PERIOD_CLOSED", "close-stale", entity_id="2026-07-15", effective_date="2026-08-02"),
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

    def test_run_configuration_is_immutable(self):
        events = configured()

        with self.assertRaisesRegex(ValueError, "already configured"):
            append_event(
                events,
                event(
                    2,
                    "RUN_CONFIGURED",
                    "run-reconfigure",
                    entity_id="2026-27",
                    policy_hash="sha256:other",
                ),
            )

    def test_provider_claim_adjustment_can_increase_or_decrease_preserved_claim(self):
        events = configured() + [
            event(2, "PROVIDER_CLAIM_APPROVED", "claim-1", entity_id="provider-a", amount=Decimal("600")),
            event(
                3,
                "PROVIDER_CLAIM_ADJUSTED",
                "claim-adj-up",
                entity_id="provider-a",
                target_transaction_id="claim-1",
                adjustment_direction="increase",
                amount=Decimal("50"),
            ),
            event(
                4,
                "PROVIDER_CLAIM_ADJUSTED",
                "claim-adj-down",
                entity_id="provider-a",
                target_transaction_id="claim-adj-up",
                adjustment_direction="decrease",
                amount=Decimal("20"),
            ),
        ]

        state = fold_events(events)

        self.assertEqual(state.provider_payable, Decimal("630"))
        self.assertEqual(state.provider_compensation_expense, Decimal("630"))

    def test_assessment_adjustment_requires_compatible_target(self):
        events = configured() + [
            event(2, "PROVIDER_CLAIM_APPROVED", "claim-1", entity_id="provider-a", amount=Decimal("600")),
        ]

        with self.assertRaisesRegex(ValueError, "not a compatible transaction"):
            append_event(
                events,
                event(
                    3,
                    "CONTRIBUTOR_ASSESSMENT_ADJUSTED",
                    "assessment-adjustment-1",
                    entity_id="contributor-a",
                    target_transaction_id="claim-1",
                    adjustment_direction="decrease",
                    amount=Decimal("20"),
                ),
            )


if __name__ == "__main__":
    unittest.main()
