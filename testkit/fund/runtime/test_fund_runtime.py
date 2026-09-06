from decimal import Decimal

import pytest

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


def test_end_to_end_assessment_receipt_claim_and_disbursement_fold():
    events = configured() + [
        event(2, "CONTRIBUTOR_ASSESSED", "assessment-1", entity_id="contributor-a", amount=Decimal("1000")),
        event(3, "CONTRIBUTOR_RECEIPT_RECORDED", "receipt-1", entity_id="contributor-a", amount=Decimal("1000")),
        event(4, "PROVIDER_CLAIM_APPROVED", "claim-1", entity_id="provider-a", amount=Decimal("600")),
        event(5, "PROVIDER_DISBURSEMENT_POSTED", "payment-1", entity_id="provider-a", amount=Decimal("600")),
    ]

    state = fold_events(events)

    assert state.program_year == "2026-27"
    assert state.cash == Decimal("400")
    assert state.contributor_receivable == Decimal("0")
    assert state.provider_payable == Decimal("0")
    assert state.contribution_revenue == Decimal("1000")
    assert state.provider_compensation_expense == Decimal("600")
    assert state.last_seq == 5


def test_duplicate_transaction_is_idempotent_on_append():
    events = configured()
    payment = event(2, "PROVIDER_CLAIM_APPROVED", "claim-1", entity_id="provider-a", amount=Decimal("600"))

    events, state, applied = append_event(events, payment)
    replayed_events, replayed_state, replayed = append_event(events, payment)

    assert applied is True
    assert replayed is False
    assert len(replayed_events) == 2
    assert replayed_state == state
    assert replayed_state.provider_payable == Decimal("600")


def test_fold_defensively_ignores_duplicate_transaction_id():
    events = configured() + [
        event(2, "CONTRIBUTOR_ASSESSED", "assessment-1", entity_id="contributor-a", amount=Decimal("100")),
        event(3, "CONTRIBUTOR_ASSESSED", "assessment-1", entity_id="contributor-a", amount=Decimal("100")),
    ]

    state = fold_events(events)

    assert state.contributor_receivable == Decimal("100")
    assert state.contribution_revenue == Decimal("100")


def test_reversal_preserves_original_transaction_and_negates_effect():
    events = configured() + [
        event(2, "PROVIDER_CLAIM_APPROVED", "claim-1", entity_id="provider-a", amount=Decimal("600")),
        event(3, "TRANSACTION_REVERSED", "reversal-1", target_transaction_id="claim-1"),
    ]

    state = fold_events(events)

    assert state.provider_payable == Decimal("0")
    assert state.provider_compensation_expense == Decimal("0")
    assert "claim-1" in state.transaction_effects
    assert "reversal-1" in state.transaction_effects
    assert "claim-1" in state.reversed_transactions


def test_same_transaction_cannot_be_reversed_twice():
    events = configured() + [
        event(2, "PROVIDER_CLAIM_APPROVED", "claim-1", entity_id="provider-a", amount=Decimal("600")),
        event(3, "TRANSACTION_REVERSED", "reversal-1", target_transaction_id="claim-1"),
    ]

    with pytest.raises(ValueError, match="already reversed"):
        append_event(events, event(4, "TRANSACTION_REVERSED", "reversal-2", target_transaction_id="claim-1"))


def test_policy_hash_mismatch_is_rejected():
    events = configured()

    with pytest.raises(ValueError, match="policy_hash"):
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


def test_closed_period_rejects_new_business_event():
    events = configured() + [
        event(2, "ACCOUNTING_PERIOD_CLOSED", "close-2026-07", entity_id="2026-07-31"),
    ]

    with pytest.raises(ValueError, match="closed accounting period"):
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


def test_program_year_advance_changes_policy_binding_without_erasing_balances():
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

    assert state.program_year == "2027-28"
    assert state.policy_hash == "sha256:policy-2027-28"
    assert state.contributor_receivable == Decimal("100")
