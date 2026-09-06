from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Iterable, Literal, Mapping

EventType = Literal[
    "RUN_CONFIGURED",
    "CONTRIBUTOR_ASSESSED",
    "CONTRIBUTOR_RECEIPT_RECORDED",
    "PROVIDER_CLAIM_APPROVED",
    "PROVIDER_DISBURSEMENT_POSTED",
    "TRANSACTION_REVERSED",
    "CLAIM_ADJUSTED",
    "ASSESSMENT_ADJUSTED",
    "ACCOUNTING_PERIOD_CLOSED",
    "PROGRAM_YEAR_ADVANCED",
]


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
    note: str | None = None


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
    transaction_effects: Mapping[str, "FundEffect"] = field(default_factory=dict)
    reversed_transactions: frozenset[str] = frozenset()


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


def initial_fund_state() -> FundState:
    return FundState()


def _validate_common(event: FundEvent) -> None:
    if event.seq < 1:
        raise ValueError("seq must be positive")
    if not event.transaction_id.strip():
        raise ValueError("transaction_id is required")
    if not event.actor_id.strip():
        raise ValueError("actor_id is required")
    if not event.effective_date.strip():
        raise ValueError("effective_date is required")
    if event.amount < 0:
        raise ValueError("amount must be non-negative; use an explicit adjustment or reversal event")


def validate_event(state: FundState, event: FundEvent) -> None:
    _validate_common(event)
    if event.event_type == "RUN_CONFIGURED":
        if not event.entity_id:
            raise ValueError("RUN_CONFIGURED requires entity_id as the program year")
        if not event.policy_hash:
            raise ValueError("RUN_CONFIGURED requires policy_hash")
        return

    if state.program_year is None:
        raise ValueError("fund run is not configured")

    if event.policy_hash and event.policy_hash != state.policy_hash:
        raise ValueError("event policy_hash does not match configured policy")

    if state.closed_through and event.effective_date <= state.closed_through and event.event_type not in {
        "TRANSACTION_REVERSED",
        "ACCOUNTING_PERIOD_CLOSED",
    }:
        raise ValueError("event effective_date falls in a closed accounting period")

    if event.event_type in {
        "CONTRIBUTOR_ASSESSED",
        "CONTRIBUTOR_RECEIPT_RECORDED",
        "PROVIDER_CLAIM_APPROVED",
        "PROVIDER_DISBURSEMENT_POSTED",
        "CLAIM_ADJUSTED",
        "ASSESSMENT_ADJUSTED",
    }:
        if event.amount <= 0:
            raise ValueError(f"{event.event_type} requires a positive amount")
        if not event.entity_id:
            raise ValueError(f"{event.event_type} requires entity_id")

    if event.event_type == "TRANSACTION_REVERSED":
        if not event.target_transaction_id:
            raise ValueError("TRANSACTION_REVERSED requires target_transaction_id")
        if event.target_transaction_id in state.reversed_transactions:
            raise ValueError("target transaction is already reversed")
        if event.target_transaction_id not in state.transaction_effects:
            raise ValueError("target transaction does not exist")

    if event.event_type == "ACCOUNTING_PERIOD_CLOSED" and not event.entity_id:
        raise ValueError("ACCOUNTING_PERIOD_CLOSED requires entity_id as YYYY-MM-DD close date")

    if event.event_type == "PROGRAM_YEAR_ADVANCED":
        if not event.entity_id or not event.policy_hash:
            raise ValueError("PROGRAM_YEAR_ADVANCED requires new program year and policy_hash")


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
    if event.event_type == "CLAIM_ADJUSTED":
        return FundEffect(provider_payable=amount, provider_compensation_expense=amount)
    if event.event_type == "ASSESSMENT_ADJUSTED":
        return FundEffect(contributor_receivable=amount, contribution_revenue=amount)
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
    next_state = replace(state, last_seq=max(state.last_seq, event.seq))

    if event.event_type == "RUN_CONFIGURED":
        return replace(next_state, program_year=event.entity_id, policy_hash=event.policy_hash)

    if event.event_type == "PROGRAM_YEAR_ADVANCED":
        return replace(next_state, program_year=event.entity_id, policy_hash=event.policy_hash)

    if event.event_type == "ACCOUNTING_PERIOD_CLOSED":
        close_date = event.entity_id
        if next_state.closed_through is None or close_date > next_state.closed_through:
            return replace(next_state, closed_through=close_date)
        return next_state

    effects = dict(next_state.transaction_effects)
    reversed_transactions = set(next_state.reversed_transactions)

    if event.event_type == "TRANSACTION_REVERSED":
        target = event.target_transaction_id
        assert target is not None
        original_effect = effects[target]
        next_state = _apply_effect(next_state, original_effect.negate())
        reversed_transactions.add(target)
        effects[event.transaction_id] = original_effect.negate()
        return replace(
            next_state,
            transaction_effects=effects,
            reversed_transactions=frozenset(reversed_transactions),
        )

    effect = effect_for_event(event)
    next_state = _apply_effect(next_state, effect)
    effects[event.transaction_id] = effect
    return replace(next_state, transaction_effects=effects)


def fold_events(events: Iterable[FundEvent]) -> FundState:
    state = initial_fund_state()
    seen_ids: set[str] = set()

    for event in sorted(events, key=lambda item: item.seq):
        if event.transaction_id in seen_ids:
            continue
        seen_ids.add(event.transaction_id)
        state = apply_event(state, event)

    return state


def append_event(events: list[FundEvent], event: FundEvent) -> tuple[list[FundEvent], FundState, bool]:
    """Append one business event with idempotent retry behavior.

    Returns (events, folded_state, applied). Replaying an existing transaction_id
    returns the current folded state with applied=False and does not append.
    """

    if any(existing.transaction_id == event.transaction_id for existing in events):
        return events, fold_events(events), False

    expected_seq = (max((existing.seq for existing in events), default=0) + 1)
    if event.seq != expected_seq:
        raise ValueError(f"event seq must be {expected_seq}")

    state = fold_events(events)
    validate_event(state, event)
    appended = [*events, event]
    return appended, fold_events(appended), True
