"""Deterministic reference runtime for synthetic TRS Fund event replay.

This module intentionally models Baudot-owned Fund semantics only. External
systems such as Apache Fineract, Kafka, dashboards, or OSCAL exporters are
adapters around this authority boundary; they do not mutate canonical Fund
state directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from typing import Iterable, Mapping


CENT = Decimal("0.01")


class FundInvariantViolation(ValueError):
    """Raised when an event would violate a canonical Fund invariant."""


def _money(value: Decimal | str | int) -> Decimal:
    amount = value if isinstance(value, Decimal) else Decimal(str(value))
    if amount != amount.quantize(CENT):
        raise FundInvariantViolation(f"money amount must be exact cents: {amount}")
    return amount


def _money_string(value: Decimal) -> str:
    return format(value.quantize(CENT), ".2f")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FundEvent:
    """One admitted event offered to the deterministic Fund runtime."""

    event_id: str
    event_type: str
    amount: Decimal
    subject_id: str
    policy_version: str
    causes: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()

    def canonical(self) -> dict[str, object]:
        return {
            "eventId": self.event_id,
            "eventType": self.event_type,
            "amount": _money_string(_money(self.amount)),
            "subjectId": self.subject_id,
            "policyVersion": self.policy_version,
            "causes": list(self.causes),
            "sourceRefs": list(self.source_refs),
        }


@dataclass(frozen=True)
class FundReceipt:
    """Immutable semantic receipt emitted after one accepted event."""

    event_id: str
    event_type: str
    event_digest: str
    pre_state_hash: str
    post_state_hash: str
    causes: tuple[str, ...]
    policy_version: str


@dataclass(frozen=True)
class ReplayResult:
    state: Mapping[str, object]
    state_hash: str
    receipts: tuple[FundReceipt, ...]


class FundRuntime:
    """Pure replay engine for the first synthetic Fund event vocabulary."""

    ASSESSMENT_ISSUED = "ASSESSMENT_ISSUED"
    CONTRIBUTION_RECEIVED = "CONTRIBUTION_RECEIVED"
    CLAIM_APPROVED = "CLAIM_APPROVED"
    PAYMENT_POSTED = "PAYMENT_POSTED"

    _SUPPORTED_TYPES = {
        ASSESSMENT_ISSUED,
        CONTRIBUTION_RECEIVED,
        CLAIM_APPROVED,
        PAYMENT_POSTED,
    }

    @classmethod
    def replay(cls, events: Iterable[FundEvent]) -> ReplayResult:
        state = cls._empty_state()
        receipts: list[FundReceipt] = []
        seen: dict[str, FundEvent] = {}

        for event in events:
            event = cls._normalize_event(event)
            if event.event_id in seen:
                raise FundInvariantViolation(f"duplicate event id: {event.event_id}")
            if event.event_type not in cls._SUPPORTED_TYPES:
                raise FundInvariantViolation(f"unsupported event type: {event.event_type}")

            pre_hash = _digest(state)
            cls._apply(state, event, seen)
            event_digest = _digest(event.canonical())
            state["events"].append(
                {
                    "eventId": event.event_id,
                    "eventType": event.event_type,
                    "eventDigest": event_digest,
                    "causes": list(event.causes),
                    "policyVersion": event.policy_version,
                }
            )
            seen[event.event_id] = event
            post_hash = _digest(state)
            receipts.append(
                FundReceipt(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    event_digest=event_digest,
                    pre_state_hash=pre_hash,
                    post_state_hash=post_hash,
                    causes=event.causes,
                    policy_version=event.policy_version,
                )
            )

        cls._refresh_totals(state)
        final_hash = _digest(state)
        return ReplayResult(state=state, state_hash=final_hash, receipts=tuple(receipts))

    @classmethod
    def trace_to_roots(
        cls, event_id: str, events: Iterable[FundEvent]
    ) -> tuple[str, ...]:
        by_id = {event.event_id: cls._normalize_event(event) for event in events}
        if event_id not in by_id:
            raise FundInvariantViolation(f"unknown event id: {event_id}")

        ordered: list[str] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(current_id: str) -> None:
            if current_id in visiting:
                raise FundInvariantViolation(f"causation cycle at: {current_id}")
            if current_id in visited:
                return
            event = by_id.get(current_id)
            if event is None:
                raise FundInvariantViolation(f"missing causation event: {current_id}")
            visiting.add(current_id)
            for cause in event.causes:
                visit(cause)
            visiting.remove(current_id)
            visited.add(current_id)
            ordered.append(current_id)

        visit(event_id)
        return tuple(ordered)

    @classmethod
    def _normalize_event(cls, event: FundEvent) -> FundEvent:
        return FundEvent(
            event_id=event.event_id,
            event_type=event.event_type,
            amount=_money(event.amount),
            subject_id=event.subject_id,
            policy_version=event.policy_version,
            causes=tuple(event.causes),
            source_refs=tuple(event.source_refs),
        )

    @staticmethod
    def _empty_state() -> dict[str, object]:
        return {
            "schema": "baudot.synthetic-trs-fund-state@1",
            "assessments": {},
            "receiptsByAssessment": {},
            "claims": {},
            "paymentsByClaim": {},
            "events": [],
            "totals": {
                "assessed": "0.00",
                "received": "0.00",
                "approvedClaims": "0.00",
                "paid": "0.00",
                "receivablesOutstanding": "0.00",
                "providerPayablesOutstanding": "0.00",
                "syntheticCashDelta": "0.00",
            },
        }

    @classmethod
    def _apply(
        cls,
        state: dict[str, object],
        event: FundEvent,
        seen: Mapping[str, FundEvent],
    ) -> None:
        if not event.event_id or not event.subject_id or not event.policy_version:
            raise FundInvariantViolation("event id, subject id, and policy version are required")

        if event.event_type == cls.ASSESSMENT_ISSUED:
            cls._require_positive(event)
            cls._require_root_source(event)
            if event.causes:
                raise FundInvariantViolation("assessment root must not have internal causes")
            state["assessments"][event.event_id] = {
                "contributorId": event.subject_id,
                "amount": _money_string(event.amount),
                "policyVersion": event.policy_version,
                "sourceRefs": list(event.source_refs),
            }

        elif event.event_type == cls.CONTRIBUTION_RECEIVED:
            cls._require_positive(event)
            assessment = cls._require_single_cause(event, seen, cls.ASSESSMENT_ISSUED)
            if assessment.subject_id != event.subject_id:
                raise FundInvariantViolation("receipt contributor does not match assessment")
            already = cls._sum_bucket(state["receiptsByAssessment"], assessment.event_id)
            if already + event.amount > assessment.amount:
                raise FundInvariantViolation("receipt exceeds outstanding assessment")
            state["receiptsByAssessment"].setdefault(assessment.event_id, []).append(
                {
                    "eventId": event.event_id,
                    "amount": _money_string(event.amount),
                }
            )

        elif event.event_type == cls.CLAIM_APPROVED:
            cls._require_positive(event)
            cls._require_root_source(event)
            if event.causes:
                raise FundInvariantViolation("approved claim root must not have internal causes")
            state["claims"][event.event_id] = {
                "providerId": event.subject_id,
                "amount": _money_string(event.amount),
                "policyVersion": event.policy_version,
                "sourceRefs": list(event.source_refs),
            }

        elif event.event_type == cls.PAYMENT_POSTED:
            cls._require_positive(event)
            claim = cls._require_single_cause(event, seen, cls.CLAIM_APPROVED)
            if claim.subject_id != event.subject_id:
                raise FundInvariantViolation("payment provider does not match approved claim")
            already = cls._sum_bucket(state["paymentsByClaim"], claim.event_id)
            if already + event.amount > claim.amount:
                raise FundInvariantViolation("payment exceeds approved claim")
            state["paymentsByClaim"].setdefault(claim.event_id, []).append(
                {
                    "eventId": event.event_id,
                    "amount": _money_string(event.amount),
                }
            )

        cls._refresh_totals(state)

    @staticmethod
    def _require_positive(event: FundEvent) -> None:
        if event.amount <= 0:
            raise FundInvariantViolation(f"{event.event_type} amount must be positive")

    @staticmethod
    def _require_root_source(event: FundEvent) -> None:
        if not event.source_refs:
            raise FundInvariantViolation(f"{event.event_type} requires at least one source reference")

    @staticmethod
    def _require_single_cause(
        event: FundEvent,
        seen: Mapping[str, FundEvent],
        required_type: str,
    ) -> FundEvent:
        if len(event.causes) != 1:
            raise FundInvariantViolation(f"{event.event_type} requires exactly one internal cause")
        cause_id = event.causes[0]
        cause = seen.get(cause_id)
        if cause is None:
            raise FundInvariantViolation(f"missing causation event: {cause_id}")
        if cause.event_type != required_type:
            raise FundInvariantViolation(
                f"{event.event_type} requires cause type {required_type}, got {cause.event_type}"
            )
        return cause

    @staticmethod
    def _sum_bucket(bucket_map: Mapping[str, list[dict[str, str]]], key: str) -> Decimal:
        return sum((Decimal(row["amount"]) for row in bucket_map.get(key, [])), Decimal("0.00"))

    @classmethod
    def _refresh_totals(cls, state: dict[str, object]) -> None:
        assessed = sum(
            (Decimal(row["amount"]) for row in state["assessments"].values()),
            Decimal("0.00"),
        )
        received = sum(
            (
                Decimal(row["amount"])
                for rows in state["receiptsByAssessment"].values()
                for row in rows
            ),
            Decimal("0.00"),
        )
        approved = sum(
            (Decimal(row["amount"]) for row in state["claims"].values()),
            Decimal("0.00"),
        )
        paid = sum(
            (
                Decimal(row["amount"])
                for rows in state["paymentsByClaim"].values()
                for row in rows
            ),
            Decimal("0.00"),
        )
        state["totals"] = {
            "assessed": _money_string(assessed),
            "received": _money_string(received),
            "approvedClaims": _money_string(approved),
            "paid": _money_string(paid),
            "receivablesOutstanding": _money_string(assessed - received),
            "providerPayablesOutstanding": _money_string(approved - paid),
            "syntheticCashDelta": _money_string(received - paid),
        }
