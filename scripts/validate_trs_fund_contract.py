#!/usr/bin/env python3
"""Validate the bounded synthetic TRS fund accounting contract."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "testkit" / "fund" / "trs-fund-contract-v1.json"
EXPECTED_SCENARIOS = {f"FUND-{number:03d}" for number in range(1, 6)}
VALID_ACCOUNT_TYPES = {"asset", "liability", "expense", "income", "equity"}


def money(value: object) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def balanced(entries: list[dict]) -> bool:
    debits = sum((money(entry["amount"]) for entry in entries if entry["side"] == "debit"), Decimal("0.00"))
    credits = sum((money(entry["amount"]) for entry in entries if entry["side"] == "credit"), Decimal("0.00"))
    return debits == credits


def account_delta(entries: list[dict], code: str) -> Decimal:
    """Return debit-positive / credit-negative movement for one synthetic account."""
    result = Decimal("0.00")
    for entry in entries:
        if entry["account"] != code:
            continue
        amount = money(entry["amount"])
        result += amount if entry["side"] == "debit" else -amount
    return result


def inverse_entries(original: list[dict], reversal: list[dict]) -> bool:
    normalized_original = sorted(
        (entry["account"], entry["side"], money(entry["amount"])) for entry in original
    )
    normalized_reversal = sorted(
        (
            entry["account"],
            "credit" if entry["side"] == "debit" else "debit",
            money(entry["amount"]),
        )
        for entry in reversal
    )
    return normalized_original == normalized_reversal


def main() -> int:
    document = json.loads(CONTRACT.read_text(encoding="utf-8"))

    require(document.get("schema") == "baudot.trs-fund-contract@1", "unexpected contract schema")
    require(document.get("status") == "experimental", "fund contract must remain experimental")

    authority = document["authority"]
    require(authority.get("financialState") == "apache-fineract-reference-ledger", "Fineract role drifted")
    require(authority.get("fineractMayDecideCompensability") is False, "Fineract cannot own compensability")
    require(authority.get("fineractMaySelectRates") is False, "Fineract cannot own rate selection")
    require(authority.get("fineractMayAuthorizeProductionPayment") is False, "Fineract cannot authorize production payment")

    profile = document["fineractProfile"]
    require(profile.get("implementation") == "Apache Fineract", "unexpected reference ledger implementation")
    require(profile.get("targetVersion") == "1.15.0", "Fineract test profile must remain exactly pinned")
    require(profile.get("liveRuntimeRequiredByThisContract") is False, "static contract must not imply live Fineract execution")
    require(set(profile.get("operations", [])) == {
        "create-journal-entry",
        "reverse-journal-entry",
        "read-journal-entry",
    }, "unexpected Fineract adapter operation surface")

    accounts = document["accounts"]
    account_codes = [account["code"] for account in accounts]
    require(len(account_codes) == len(set(account_codes)), "duplicate synthetic account code")
    require(all(account["type"] in VALID_ACCOUNT_TYPES for account in accounts), "invalid account type")
    known_accounts = set(account_codes)

    rate_profiles = document["rateProfiles"]
    require(rate_profiles, "at least one synthetic rate profile is required")
    for rate in rate_profiles:
        require(rate.get("synthetic") is True, f"rate {rate.get('id')} must be explicitly synthetic")
        require(rate.get("productionRateClaim") is False, f"rate {rate.get('id')} must not claim a production rate")
        require(str(rate.get("id", "")).startswith("synthetic-"), "synthetic rate profile id must be visibly synthetic")
        require(money(rate["rate"]) > Decimal("0.00"), "synthetic rate must be positive")

    scenarios = document["scenarios"]
    scenario_ids = {scenario["id"] for scenario in scenarios}
    require(scenario_ids == EXPECTED_SCENARIOS, f"scenario set drift: {sorted(scenario_ids)}")
    require(len(scenario_ids) == len(scenarios), "duplicate scenario id")

    for scenario in scenarios:
        entries = scenario.get("expectedEntries", [])
        require(balanced(entries), f"{scenario['id']}: expected journal entries are not balanced")
        for entry in entries:
            require(entry["account"] in known_accounts, f"{scenario['id']}: unknown account {entry['account']}")
            require(entry["side"] in {"debit", "credit"}, f"{scenario['id']}: invalid side")
            require(money(entry["amount"]) > Decimal("0.00"), f"{scenario['id']}: posting amount must be positive")

    approved = next(s for s in scenarios if s["id"] == "FUND-001")
    claim = approved["claim"]
    rate = next(r for r in rate_profiles if r["id"] == claim["rateProfile"])
    computed = money(claim["minutes"]) * money(rate["rate"])
    require(computed == money(claim["approvedAmount"]), "FUND-001 synthetic rate arithmetic drift")
    require(claim.get("decision") == "approved", "FUND-001 must begin from an explicit approved claim")
    require(account_delta(approved["expectedEntries"], "6100") == Decimal("60.00"), "FUND-001 expense posting drift")
    require(account_delta(approved["expectedEntries"], "2100") == Decimal("-60.00"), "FUND-001 payable posting drift")

    settlement = next(s for s in scenarios if s["id"] == "FUND-002")
    require(settlement["claimId"] == claim["claimId"], "FUND-002 must settle the approved claim")
    require(settlement["payment"].get("synthetic") is True, "settlement rail must remain synthetic")
    require(settlement["payment"].get("status") == "settled", "FUND-002 must exercise settled payment")
    require(account_delta(settlement["expectedEntries"], "2100") == Decimal("60.00"), "FUND-002 must debit payable")
    require(account_delta(settlement["expectedEntries"], "1000") == Decimal("-60.00"), "FUND-002 must credit fund cash")

    duplicate = next(s for s in scenarios if s["id"] == "FUND-003")
    require(duplicate["claim"]["claimId"] == claim["claimId"], "FUND-003 must replay FUND-001 claim")
    require(duplicate["claim"]["idempotencyKey"] == claim["idempotencyKey"], "FUND-003 must reuse the same idempotency key")
    require(duplicate.get("replay") is True, "FUND-003 must be explicitly marked as replay")
    require(duplicate["expectedEntries"] == [], "duplicate replay must create zero journal entries")
    require(money(duplicate["expectedAdditionalFinancialEffect"]) == Decimal("0.00"), "duplicate replay must have zero financial effect")

    adjustment = next(s for s in scenarios if s["id"] == "FUND-004")
    delta = money(adjustment["originalApprovedAmount"]) - money(adjustment["adjustedApprovedAmount"])
    require(delta == Decimal("6.00"), "FUND-004 expected synthetic adjustment changed")
    require(account_delta(adjustment["expectedEntries"], "2100") == delta, "FUND-004 must reduce provider payable")
    require(account_delta(adjustment["expectedEntries"], "6100") == -delta, "FUND-004 must reduce reimbursement expense")

    reversal = next(s for s in scenarios if s["id"] == "FUND-005")
    require(reversal["reversalOf"] == reversal["originalTransactionId"], "FUND-005 reversal must reference original transaction")
    require(reversal["reversalTransactionId"] != reversal["originalTransactionId"], "FUND-005 reversal must have distinct identity")
    require(reversal.get("originalTransactionMustRemainAddressable") is True, "FUND-005 must preserve original transaction history")
    require(balanced(reversal["originalEntries"]), "FUND-005 original transaction is not balanced")
    require(inverse_entries(reversal["originalEntries"], reversal["expectedEntries"]), "FUND-005 reversal is not equal-and-opposite")

    boundary = document["claimBoundary"]
    require(boundary.get("syntheticLifecycleEvidenceOnly") is True, "claim boundary must remain synthetic-only")
    for key in (
        "productionTrsFundAccounting",
        "productionAdministratorCompatibility",
        "productionProviderReimbursement",
        "fccPaymentAuthorization",
        "fineractConformance",
    ):
        require(boundary.get(key) is False, f"forbidden positive claim: {key}")

    print(f"validated {len(scenarios)} synthetic TRS fund scenarios")
    print("Fineract remains financial-state implementation, not compensability/rate/payment authority")
    print("duplicate replay has zero additional posting")
    print("settlement, adjustment, and reversal accounting invariants: PASS")
    print("TRS fund contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
