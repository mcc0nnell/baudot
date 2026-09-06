from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from typing import Iterable, Literal, Mapping

AdjustmentDirection = Literal["increase", "decrease"]
EventType = Literal[
    "RUN_CONFIGURED",
    "CONTRIBUTOR_ASSESSED",
    "CONTRIBUTOR_RECEIPT_RECORDED",
    "PROVIDER_CLAIM_APPROVED",
    "PROVIDER_DISBURSEMENT_POSTED",
    "TRANSACTION_REVERSED",
    "PROVIDER_CLAIM_ADJUSTED",
    "CONTRIBUTOR_ASSESSMENT_ADJUSTED",
    "ACCOUNTING_PERIOD_CLOSED",
    "PROGRAM_YEAR_ADVANCED",
]

MONETARY_EVENT_TYPES = {
    "CONTRIBUTOR_ASSESSED",
    "CONTRIBUTOR_RECEIPT_RECORDED",
    "PROVIDER_CLAIM_APPROVED",
    "PROVIDER_DISBURSEMENT_POSTED",
    "PROVIDER_CLAIM_ADJUSTED",
    "CONTRIBUTOR_ASSESSMENT_ADJUSTED",
}
ADJUSTMENT_EVENT_TYPES = {
    "PROVIDER_CLAIM_ADJUSTED",
    "CONTRIBUTOR_ASSESSMENT_ADJUSTED",
}


@dataclass(frozen=True)
class FundEvent:
    seq: int
    event_type: EventType
    transaction_id: str
    actor_id: str
    effective_date: str
    amount: Decimal = Decimal("0")
    entity_id: str | None = None
    policy_hash: str | None = None
    target_transaction_id: str | None = None
    adjustment_direction: AdjustmentDirection | None = None
    note: str | None = None


@dataclass(frozen=True)
class FundEffect:
    cash: Decimal = Decimal("0")
    contributor_receivable: Decimal = Decimal("0")
    provider_payable: Decimal = Decimal("0")
    contribution_revenue: Decimal = Decimal("0")
    provider_compensation_expense: Decimal = Decimal("0")

    def negate(self) -> "FundEffect":
        return FundEffect(
            cash=-self.cash,
            contributor_receivable=-self.contributor_receivable,
            provider_payable=-self.provider_payable,
            contribution_revenue=-self.contribution_revenue,
            provider_compensation_expense=-self.provider_compensation_expense,
        )


@dataclass(frozen=True)
class FundState:
    program_year: str | None = None
    policy_hash: str | None = None
    cash: Decimal = Decimal("0")
    contributor_receivable: Decimal = Decimal("0")
    provider_payable: Decimal = Decimal("0")
    contribution_revenue: Decimal = Decimal("0")
    provider_compensation_expense: Decimal = Decimal("0")
    closed_through: str | None = None
    last_seq: int = 0
    transaction_effects: Mapping[str, FundEffect] = field(default_factory=dict)
    transaction_types: Mapping[str, EventType] = field(default_factory=dict)
    transaction_dates: Mapping[str, str] = field(default_factory=dict)
    reversed_transactions: frozenset[str] = frozenset()


def initial_fund_state() -> FundState:
    return FundState()


def _parse_iso_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date (YYYY-MM-DD)") from exc


def _validate_common(event: FundEvent) -> None:
    if event.seq < 1:
        raise ValueError("seq must be positive")
    if not event.transaction_id.strip():
        raise ValueError("transaction_id is required")
    if not event.actor_id.strip():
        raise ValueError("actor_id is required")
    if not event.effective_date.strip():
        raise ValueError("effective_date is required")
    _parse_iso_date(event.effective_date, "effective_date")
    if event.amount < 0:
        raise ValueError("amount must be non-negative; use an explicit adjustment or reversal event")


def validate_event(state: FundState, event: FundEvent) -> None:
    _validate_common(event)

    if event.event_type == "RUN_CONFIGURED":
        if state.program_year is not None:
            raise ValueError("fund run is already configured; use PROGRAM_YEAR_ADVANCED")
        if not event.entity_id:
            raise ValueError("RUN_CONFIGURED requires entity_id as the program year")
        if not event.policy_hash:
            raise ValueError("RUN_CONFIGURED requires policy_hash")
        return

    if state.program_year is None:
        raise ValueError("fund run is not configured")

    if event.policy_hash and event.policy_hash != state.policy_hash:
        raise ValueError("event policy_hash does not match configured policy")

    if state.closed_through and event.effective_date <= state.closed_through and event.event_type != "ACCOUNTING_PERIOD_CLOSED":
        raise ValueError("event effective_date falls in a closed accounting period; use an authorized open date")

    if event.event_type in MONETARY_EVENT_TYPES:
        if event.amount <= 0:
            raise ValueError(f"{event.event_type} requires a positive amount")
        if not event.entity_id:
            raise ValueError(f"{event.event_type} requires entity_id")

    if event.event_type == "TRANSACTION_REVERSED":
        target = event.target_transaction_id
        if not target:
            raise ValueError("TRANSACTION_REVERSED requires target_transaction_id")
        if target in state.reversed_transactions:
            raise ValueError("target transaction is already reversed")
        if target not in state.transaction_effects:
            raise ValueError("target transaction does not exist or has no financial effect")
        if state.transaction_types.get(target) == "TRANSACTION_REVERSED":
            raise ValueError("a reversal cannot target another reversal")
        target_date = state.transaction_dates.get(target)
        if target_date is None:
            raise ValueError("target transaction has no accounting effective date")
        if state.closed_through and target_date <= state.closed_through:
            raise ValueError(
                "target transaction is in a closed accounting period; use a compensating adjustment on an authorized open date"
            )
        if event.effective_date != target_date:
            raise ValueError(
                "TRANSACTION_REVERSED effective_date must equal target transaction date because Fineract reverses on the original journal date"
            )

    if event.event_type in ADJUSTMENT_EVENT_TYPES:
        target = event.target_transaction_id
        if not target:
            raise ValueError(f"{event.event_type} requires target_transaction_id")
        if target in state.reversed_transactions:
            raise ValueError("cannot adjust a reversed target transaction")
        target_type = state.transaction_types.get(target)
        allowed_targets = (
            {"PROVIDER_CLAIM_APPROVED", "PROVIDER_CLAIM_ADJUSTED"}
            if event.event_type == "PROVIDER_CLAIM_ADJUSTED"
            else {"CONTRIBUTOR_ASSESSED", "CONTRIBUTOR_ASSESSMENT_ADJUSTED"}
        )
        if target_type not in allowed_targets:
            raise ValueError(f"{event.event_type} target is not a compatible transaction")
        if event.adjustment_direction not in {"increase", "decrease"}:
            raise ValueError(f"{event.event_type} requires adjustment_direction increase or decrease")

    if event.event_type == "ACCOUNTING_PERIOD_CLOSED":
        if not event.entity_id:
            raise ValueError("ACCOUNTING_PERIOD_CLOSED requires entity_id as YYYY-MM-DD close date")
        close_date = _parse_iso_date(event.entity_id, "ACCOUNTING_PERIOD_CLOSED entity_id")
        if close_date > _parse_iso_date(event.effective_date, "effective_date"):
            raise ValueError("accounting close date cannot be after the event effective_date")
        if state.closed_through and event.entity_id <= state.closed_through:
            raise ValueError("accounting closure must advance closed_through")

    if event.event_type == "PROGRAM_YEAR_ADVANCED":
        if not event.entity_id or not event.policy_hash:
            raise ValueError("PROGRAM_YEAR_ADVANCED requires new program year and policy_hash")
        if event.entity_id == state.program_year:
            raise ValueError("PROGRAM_YEAR_ADVANCED requires a different program year")


def effect_for_event(event: FundEvent) -> FundEffect:
    amount = event.amount
    if event.event_type == "CONTRIBUTOR_ASSESSED":
        return FundEffect(contributor_receivable=amount, contribution_revenue=amount)
    if event.event_type == "CONTRIBUTOR_RECEIPT_RECORDED":
        return FundEffect(cash=amount, contributor_receivable=-amount)
    if event.event_type == "PROVIDER_CLAIM_APPROVED":
        return FundEffect(provider_payable=amount, provider_compensation_expense=amount)
    if event.event_type == "PROVIDER_DISBURSEMENT_POSTED":
        return FundEffect(cash=-amount, provider_payable=-amount)
    if event.event_type == "PROVIDER_CLAIM_ADJUSTED":
        sign = Decimal("1") if event.adjustment_direction == "increase" else Decimal("-1")
        return FundEffect(provider_payable=sign * amount, provider_compensation_expense=sign * amount)
    if event.event_type == "CONTRIBUTOR_ASSESSMENT_ADJUSTED":
        sign = Decimal("1") if event.adjustment_direction == "increase" else Decimal("-1")
        return FundEffect(contributor_receivable=sign * amount, contribution_revenue=sign * amount)
    return FundEffect()


def _apply_effect(state: FundState, effect: FundEffect) -> FundState:
    return replace(
        state,
        cash=state.cash + effect.cash,
        contributor_receivable=state.contributor_receivable + effect.contributor_receivable,
        provider_payable=state.provider_payable + effect.provider_payable,
        contribution_revenue=state.contribution_revenue + effect.contribution_revenue,
        provider_compensation_expense=state.provider_compensation_expense + effect.provider_compensation_expense,
    )


def apply_event(state: FundState, event: FundEvent) -> FundState:
    validate_event(state, event)
    next_state = replace(state, last_seq=event.seq)

    if event.event_type == "RUN_CONFIGURED":
        return replace(next_state, program_year=event.entity_id, policy_hash=event.policy_hash)

    if event.event_type == "PROGRAM_YEAR_ADVANCED":
        return replace(next_state, program_year=event.entity_id, policy_hash=event.policy_hash)

    if event.event_type == "ACCOUNTING_PERIOD_CLOSED":
        return replace(next_state, closed_through=event.entity_id)

    effects = dict(next_state.transaction_effects)
    types = dict(next_state.transaction_types)
    dates = dict(next_state.transaction_dates)
    reversed_transactions = set(next_state.reversed_transactions)

    if event.event_type == "TRANSACTION_REVERSED":
        target = event.target_transaction_id
        assert target is not None
        original_effect = effects[target]
        reversal_effect = original_effect.negate()
        next_state = _apply_effect(next_state, reversal_effect)
        reversed_transactions.add(target)
        effects[event.transaction_id] = reversal_effect
        types[event.transaction_id] = event.event_type
        dates[event.transaction_id] = event.effective_date
        return replace(
            next_state,
            transaction_effects=effects,
            transaction_types=types,
            transaction_dates=dates,
            reversed_transactions=frozenset(reversed_transactions),
        )

    effect = effect_for_event(event)
    if event.event_type in MONETARY_EVENT_TYPES:
        next_state = _apply_effect(next_state, effect)
        effects[event.transaction_id] = effect
        types[event.transaction_id] = event.event_type
        dates[event.transaction_id] = event.effective_date
        return replace(next_state, transaction_effects=effects, transaction_types=types, transaction_dates=dates)

    return next_state


def fold_events(events: Iterable[FundEvent]) -> FundState:
    ordered = sorted(events, key=lambda item: item.seq)
    state = initial_fund_state()
    seen_ids: set[str] = set()

    for expected_seq, event in enumerate(ordered, start=1):
        if event.seq != expected_seq:
            raise ValueError(f"event log sequence must be contiguous; expected {expected_seq}, got {event.seq}")
        if event.transaction_id in seen_ids:
            raise ValueError(f"duplicate transaction_id in persisted event log: {event.transaction_id}")
        seen_ids.add(event.transaction_id)
        state = apply_event(state, event)

    return state


def append_event(events: list[FundEvent], event: FundEvent) -> tuple[list[FundEvent], FundState, bool]:
    """Append one business event with idempotent retry behavior.

    Returns ``(events, folded_state, applied)``. Replaying an existing
    ``transaction_id`` is acknowledged with ``applied=False`` and is never
    appended, so a network retry cannot duplicate a financial effect.
    """

    state = fold_events(events)
    if any(existing.transaction_id == event.transaction_id for existing in events):
        return events, state, False

    expected_seq = state.last_seq + 1
    if event.seq != expected_seq:
        raise ValueError(f"event seq must be {expected_seq}")

    validate_event(state, event)
    appended = [*events, event]
    return appended, apply_event(state, event), True
