#!/usr/bin/env python3
"""Validate the TRS Fund runtime lifecycle against the canonical journal contract."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "testkit" / "fund" / "trs-fund-runtime-contract-v1.json"
JOURNAL = ROOT / "interop" / "fineract" / "journal-contract-v1.json"
EXPECTED_SCENARIOS = {f"FUND-{number:03d}" for number in range(1, 6)}


def money(value: object) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def balanced(entries: list[dict]) -> bool:
    debits = sum((money(entry["amount"]) for entry in entries if entry["side"] == "debit"), Decimal("0.00"))
    credits = sum((money(entry["amount"]) for entry in entries if entry["side"] == "credit"), Decimal("0.00"))
    return debits == credits


def normalized(entries: list[dict]) -> list[tuple[str, str, Decimal]]:
    return sorted((entry["account"], entry["side"], money(entry["amount"])) for entry in entries)


def expected_for_event(event: dict, amount: Decimal) -> list[tuple[str, str, Decimal]]:
    return sorted([
        (event["debit"], "debit", amount),
        (event["credit"], "credit", amount),
    ])


def expected_inverse(event: dict, amount: Decimal) -> list[tuple[str, str, Decimal]]:
    return sorted([
        (event["credit"], "debit", amount),
        (event["debit"], "credit", amount),
    ])


def main() -> int:
    runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
    journal = json.loads(JOURNAL.read_text(encoding="utf-8"))

    require(runtime.get("schema") == "baudot.trs-fund-runtime-contract@1", "unexpected runtime contract schema")
    require(runtime.get("status") == "experimental", "runtime contract must remain experimental")
    require(journal.get("schema") == "baudot.fineract-trs-journal-contract@1", "unexpected journal contract schema")

    depends = runtime["dependsOn"]
    require(depends.get("publicCalibration") == "baudot.trs-fund-public-calibration@1", "public calibration dependency drift")
    require(depends.get("journalContract") == journal["schema"], "runtime must depend on canonical journal contract")

    # The runtime layer is forbidden from redefining Fund policy inputs or the chart of accounts.
    require("accounts" not in runtime, "runtime contract must not define its own account catalog")
    require("rateProfiles" not in runtime, "runtime contract must not define rate profiles")

    authority = runtime["authority"]
    require(authority.get("financialState") == "apache-fineract-reference-ledger", "Fineract role drifted")
    require(authority.get("fineractMayDecideCompensability") is False, "Fineract cannot own compensability")
    require(authority.get("fineractMaySelectRates") is False, "Fineract cannot own rate selection")
    require(authority.get("fineractMayAuthorizeProductionPayment") is False, "Fineract cannot authorize production payment")

    profile = runtime["fineractProfile"]
    require(profile.get("implementation") == "Apache Fineract", "unexpected ledger implementation")
    require(profile.get("targetVersion") == "1.15.0", "runtime test profile version drift")
    require(profile.get("liveRuntimeRequiredByThisContract") is False, "static lifecycle contract must not imply live execution")
    require(set(profile.get("operations", [])) == {
        "create-journal-entry",
        "read-journal-entry",
        "reverse-journal-entry",
    }, "unexpected Fineract operation surface")

    accounts = journal["accounts"]
    events = journal["events"]
    scenarios = runtime["scenarios"]
    scenario_ids = {scenario["id"] for scenario in scenarios}
    require(scenario_ids == EXPECTED_SCENARIOS, f"scenario set drift: {sorted(scenario_ids)}")
    require(len(scenarios) == len(scenario_ids), "duplicate scenario id")

    for scenario in scenarios:
        entries = scenario.get("expectedEntries", [])
        require(balanced(entries), f"{scenario['id']}: entries are not balanced")
        for entry in entries:
            require(entry["account"] in accounts, f"{scenario['id']}: unknown canonical account {entry['account']}")
            require(entry["side"] in {"debit", "credit"}, f"{scenario['id']}: invalid entry side")
            require(money(entry["amount"]) > Decimal("0.00"), f"{scenario['id']}: posting amount must be positive")

        if "journalEvent" in scenario:
            event_name = scenario["journalEvent"]
            require(event_name in events, f"{scenario['id']}: unknown canonical journal event {event_name}")
            amount = money(scenario.get("approvedAmount", scenario.get("amount")))
            require(normalized(entries) == expected_for_event(events[event_name], amount),
                    f"{scenario['id']}: entries drifted from canonical event {event_name}")

        if "inverseOfJournalEvent" in scenario:
            event_name = scenario["inverseOfJournalEvent"]
            require(event_name in events, f"{scenario['id']}: unknown inverse event {event_name}")
            amount = money(scenario["amount"])
            require(normalized(entries) == expected_inverse(events[event_name], amount),
                    f"{scenario['id']}: inverse entries drifted from canonical event {event_name}")

    approved = next(s for s in scenarios if s["id"] == "FUND-001")
    require(approved.get("upstreamDecision") == "approved", "FUND-001 must begin after explicit upstream approval")
    require(money(approved["approvedAmount"]) == Decimal("60.00"), "FUND-001 fixture amount drift")

    settlement = next(s for s in scenarios if s["id"] == "FUND-002")
    require(settlement["settles"] == approved["syntheticBusinessTransactionId"], "FUND-002 must settle FUND-001")
    require(money(settlement["amount"]) == money(approved["approvedAmount"]), "FUND-002 settlement amount mismatch")

    replay = next(s for s in scenarios if s["id"] == "FUND-003")
    require(replay["replays"] == approved["syntheticBusinessTransactionId"], "FUND-003 must replay FUND-001")
    require(replay["idempotencyKey"] == approved["idempotencyKey"], "FUND-003 must reuse FUND-001 idempotency key")
    require(replay["expectedEntries"] == [], "duplicate replay must produce no second posting")
    require(money(replay["expectedAdditionalFinancialEffect"]) == Decimal("0.00"), "duplicate replay must have zero financial effect")

    adjustment = next(s for s in scenarios if s["id"] == "FUND-004")
    delta = money(adjustment["originalApprovedAmount"]) - money(adjustment["adjustedApprovedAmount"])
    require(adjustment.get("entryKind") == "compensating-entry", "FUND-004 must be explicit compensating entry")
    require(delta == money(adjustment["amount"]), "FUND-004 adjustment amount mismatch")

    reversal = next(s for s in scenarios if s["id"] == "FUND-005")
    require(reversal["reversalOf"] == reversal["originalTransactionId"], "FUND-005 must reference original transaction")
    require(reversal["reversalTransactionId"] != reversal["originalTransactionId"], "FUND-005 reversal needs distinct identity")
    require(reversal.get("originalTransactionMustRemainAddressable") is True, "FUND-005 must preserve original transaction")
    require(balanced(reversal["originalEntries"]), "FUND-005 original entries are not balanced")
    require(normalized(reversal["expectedEntries"]) == expected_inverse(events["providerClaimApproved"], money(reversal["amount"])),
            "FUND-005 reversal does not invert canonical provider claim event")

    boundary = runtime["claimBoundary"]
    require(boundary.get("syntheticLifecycleEvidenceOnly") is True, "runtime claim boundary must remain synthetic-only")
    for key in (
        "publicFundArithmeticOwnedHere",
        "rateSelectionOwnedHere",
        "accountCatalogOwnedHere",
        "productionTrsFundAccounting",
        "productionAdministratorCompatibility",
        "productionProviderReimbursement",
        "fccPaymentAuthorization",
        "fineractConformance",
    ):
        require(boundary.get(key) is False, f"forbidden positive claim: {key}")

    print("canonical journal dependency: PASS")
    print("approved claim, settlement, idempotent replay, adjustment, reversal: PASS")
    print("runtime defines no rates and no account catalog: PASS")
    print("TRS Fund runtime lifecycle contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
