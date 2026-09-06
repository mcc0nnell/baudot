#!/usr/bin/env python3
"""Validate the static accounting-closure probe without requiring Fineract."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "testkit" / "fund" / "fineract-live-smoke-v1.json"
CONTRACT = ROOT / "interop" / "fineract" / "journal-contract-v1.json"
EXPECTED_ERROR = "error.msg.glJournalEntry.invalid.accounting.closed"


def require(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS {name}")


def parse_day(value: str) -> date:
    return date.fromisoformat(value)


def main() -> None:
    scenario = json.loads(SCENARIO.read_text())
    contract = json.loads(CONTRACT.read_text())
    probe = scenario["closureProbe"]
    event = probe["event"]

    closing = parse_day(probe["closingDate"])
    rejected = parse_day(probe["rejectedPostingDate"])
    opened = parse_day(probe["authorizedOpenDate"])

    require("closed-date probe is on or before closure", rejected <= closing)
    require("authorized correction date is after closure", opened > closing)
    require(
        "fixture pins Fineract accounting-closed error code",
        probe["expectedFineractErrorCode"] == EXPECTED_ERROR,
    )
    require(
        "closure probe event type exists in journal contract",
        event["type"] in contract["events"],
    )
    require("closure probe amount is positive", Decimal(event["amount"]) > 0)
    require(
        "closed and open correction IDs are distinct",
        probe["rejectedEventId"] != probe["authorizedEventId"],
    )
    require(
        "closure remains evidence-gated before live proof",
        "FUND-CLS-001" not in scenario["requiredInvariants"],
    )
    require(
        "journal contract declares closed-period invariant",
        any("accounting-closure" in row for row in contract["invariants"]),
    )

    print("Synthetic TRS Fund closure fixture: PASS")


if __name__ == "__main__":
    main()
