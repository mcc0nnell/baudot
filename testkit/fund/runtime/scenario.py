from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from fund_runtime import FundEvent, FundState, fold_events


SCHEMA = "baudot.synthetic-fund-event-scenario@1"


def event_from_record(record: dict[str, Any]) -> FundEvent:
    return FundEvent(
        seq=int(record["seq"]),
        event_type=record["eventType"],
        transaction_id=str(record["transactionId"]),
        actor_id=str(record.get("actorId", "synthetic-scenario")),
        effective_date=str(record["effectiveDate"]),
        amount=Decimal(str(record.get("amount", "0"))),
        entity_id=record.get("entityId"),
        policy_hash=record.get("policyHash"),
        target_transaction_id=record.get("targetTransactionId"),
        adjustment_direction=record.get("adjustmentDirection"),
        note=record.get("note"),
    )


def load_scenario(path: str | Path) -> tuple[dict[str, Any], list[FundEvent]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA:
        raise ValueError(f"scenario schema must be {SCHEMA}")
    raw_events = payload.get("events")
    if not isinstance(raw_events, list) or not raw_events:
        raise ValueError("scenario requires a non-empty events array")
    return payload, [event_from_record(record) for record in raw_events]


def replay_scenario(path: str | Path) -> tuple[dict[str, Any], FundState]:
    payload, events = load_scenario(path)
    return payload, fold_events(events)
