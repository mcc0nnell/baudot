#!/usr/bin/env python3
"""Validate synthetic 47 CFR § 64.643 VRS compensation-rate contracts."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQ = ROOT / "testkit/part64/vrs-rate-requirements-v1.json"
RATES = ROOT / "testkit/part64/fixtures/vrs-rates-2026-27.json"
CASES = ROOT / "testkit/part64/fixtures/vrs-rate-cases.json"
FORMULAS = ROOT / "testkit/part64/fixtures/vrs-rate-formula-cases.json"

ONE_MILLION = 1_000_000


def load(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def money(value) -> Decimal:
    return Decimal(str(value))


def calculate_base(minutes: int, rates: dict) -> tuple[str, int, int, int, Decimal]:
    small = money(rates["smallProvider"])
    tier1 = money(rates["largeProviderTier1"])
    tier2 = money(rates["largeProviderTier2"])

    if minutes <= ONE_MILLION:
        return "small", minutes, 0, 0, Decimal(minutes) * small

    first = ONE_MILLION
    excess = minutes - ONE_MILLION
    return "large", 0, first, excess, Decimal(first) * tier1 + Decimal(excess) * tier2


def exogenous_rate(case: dict) -> Decimal:
    exogenous = case.get("exogenous")
    if not exogenous:
        return Decimal("0")

    required = (
        exogenous["commissionApprovedOnOrBeforeJune30"],
        exogenous["wellDocumented"],
        exogenous["allowableCategory"],
        exogenous["beyondProviderControlOrNewRequirement"],
        exogenous["notFactoredIntoFormula"],
        exogenous["unrecoveredCostConditionMet"],
    )
    if not all(required):
        return Decimal("0")

    projected = int(exogenous["projectedFundYearMinutes"])
    require(projected > 0, "approved exogenous adjustment has non-positive projected minutes")
    return money(exogenous["approvedClaimUsd"]) / Decimal(projected)


def main() -> None:
    requirements = load(REQ)
    rates_doc = load(RATES)
    cases_doc = load(CASES)
    formulas = load(FORMULAS)

    require(requirements["safety"], "safety declarations missing")
    require(all(value is False for value in requirements["safety"].values()),
            "public rate corpus enables production/payment authority")

    req_ids = {item["id"] for item in requirements["requirements"]}
    require(req_ids == {
        "PART64-643-SMALL",
        "PART64-643-LARGE-TIER1",
        "PART64-643-LARGE-TIER2",
        "PART64-643-VIDEO-TEXT",
        "PART64-643-INFLATION",
        "PART64-643-EXOGENOUS",
    }, "unexpected §64.643 requirement set")

    require(rates_doc["fundYear"] == "2026-27", "unexpected public rate Fund Year")
    require(rates_doc["periodStart"] == "2026-07-01" and rates_doc["periodEnd"] == "2027-06-30",
            "2026-27 VRS rate period mismatch")
    require(rates_doc["normativeBoundaryAuthority"] == "47 CFR 64.643",
            "CFR is not preserved as tier-boundary authority")
    require(rates_doc["publishedRateSource"]["authority"] ==
            "published-operational-rate-input-not-tier-semantics-authority",
            "published rate page was promoted into tier-semantics authority")

    rates = rates_doc["ratesUsdPerConversationMinute"]
    require(money(rates["smallProvider"]) == Decimal("8.61"), "2026-27 small-provider rate mismatch")
    require(money(rates["largeProviderTier1"]) == Decimal("6.96"), "2026-27 large Tier I rate mismatch")
    require(money(rates["largeProviderTier2"]) == Decimal("4.35"), "2026-27 large Tier II rate mismatch")
    require(money(rates["videoTextAdditive"]) == Decimal("0.22"), "2026-27 Video-Text additive mismatch")

    boundary = rates_doc["cfrTierBoundary"]
    require(boundary["smallProviderMaximumMonthlyConversationMinutes"] == ONE_MILLION,
            "CFR small-provider one-million-minute boundary changed")
    require(boundary["largeProviderThreshold"] == "more-than-1000000",
            "large-provider threshold must be strictly more than one million")
    require(boundary["largeProviderTier1MaximumMinutes"] == ONE_MILLION,
            "large-provider Tier I first-million boundary changed")
    require(rates_doc["actualPaymentInstruction"] is False,
            "rate fixture contains an actual payment instruction")

    cases = {item["scenario"]: item for item in cases_doc["cases"]}
    require(set(cases) == {
        "VRS-RATE-SMALL-1000000",
        "VRS-RATE-LARGE-1000001",
        "VRS-RATE-LARGE-1250000",
        "VRS-RATE-VIDEO-TEXT-1000",
        "VRS-RATE-VIDEO-TEXT-PARTIAL",
        "VRS-RATE-EXOGENOUS-APPROVED",
        "VRS-RATE-EXOGENOUS-NOT-APPROVED",
        "VRS-RATE-NO-COMPENSABILITY-001",
    }, "unexpected VRS rate scenario set")

    blocked = cases["VRS-RATE-NO-COMPENSABILITY-001"]
    require(blocked["externallyEstablishedCompensableMinutes"] is None,
            "no-compensability control unexpectedly has terminal minutes")
    require(blocked["expected"]["rateCalculationAllowed"] is False,
            "rate calculation allowed without terminal compensability input")
    require(blocked["expected"]["payableFundClaimCreated"] is False,
            "blocked rate case created a payable Fund claim")

    for scenario, case in cases.items():
        if scenario == "VRS-RATE-NO-COMPENSABILITY-001":
            continue

        classification_minutes = int(case["monthlyConversationMinutesForRateClassification"])
        compensable_minutes = int(case["externallyEstablishedCompensableMinutes"])
        require(classification_minutes > 0 and compensable_minutes > 0,
                f"{scenario}: rate minutes must be positive")
        # Current synthetic arms avoid inventing policy for divergent classification/payable minute counts.
        require(classification_minutes == compensable_minutes,
                f"{scenario}: classification/payable minutes diverge; add an explicit authority rule before supporting that case")

        provider_class, small_minutes, tier1_minutes, tier2_minutes, base = calculate_base(compensable_minutes, rates)
        expected = case["expected"]
        if "providerClass" in expected:
            require(expected["providerClass"] == provider_class,
                    f"{scenario}: provider-class boundary mismatch")
        if "smallRateMinutes" in expected:
            require(expected["smallRateMinutes"] == small_minutes,
                    f"{scenario}: small-rate minute allocation mismatch")
        if "largeTier1Minutes" in expected:
            require(expected["largeTier1Minutes"] == tier1_minutes,
                    f"{scenario}: Tier I minute allocation mismatch")
        if "largeTier2Minutes" in expected:
            require(expected["largeTier2Minutes"] == tier2_minutes,
                    f"{scenario}: Tier II minute allocation mismatch")
        if "baseCompensationUsd" in expected:
            require(base == money(expected["baseCompensationUsd"]),
                    f"{scenario}: base compensation mismatch")

        video_text_minutes = int(case.get("videoTextMinutes", 0))
        require(0 <= video_text_minutes <= compensable_minutes,
                f"{scenario}: Video-Text minutes exceed compensable minutes")
        video_additive = Decimal(video_text_minutes) * money(rates["videoTextAdditive"])
        if "videoTextAdditiveUsd" in expected:
            require(video_additive == money(expected["videoTextAdditiveUsd"]),
                    f"{scenario}: Video-Text additive mismatch")

        exog_per_minute = exogenous_rate(case)
        exog_total = exog_per_minute * Decimal(compensable_minutes)
        if "exogenousRateUsdPerMinute" in expected:
            require(exog_per_minute == money(expected["exogenousRateUsdPerMinute"]),
                    f"{scenario}: exogenous per-minute rate mismatch")
        if "exogenousAdjustmentUsd" in expected:
            require(exog_total == money(expected["exogenousAdjustmentUsd"]),
                    f"{scenario}: exogenous total adjustment mismatch")

        calculated = base + video_additive + exog_total
        require(calculated == money(expected["calculatedCompensationUsd"]),
                f"{scenario}: calculated compensation mismatch")
        require(expected["payableFundClaimCreated"] is False,
                f"{scenario}: rate calculation incorrectly created a payable claim")

    # Formula-only controls exercise §64.643(b)-(d) without asserting a real FCC factor or claim.
    inflation = formulas["inflation"]
    inflation_amount = money(inflation["previousFundYearAmountUsdPerMinute"]) * (
        Decimal("1") + money(inflation["inflationAdjustmentFactor"])
    )
    require(inflation_amount == money(inflation["expectedExactUnroundedAmountUsdPerMinute"]),
            "synthetic inflation formula mismatch")

    exog_formula = formulas["exogenous"]
    exog_amount = money(exog_formula["approvedClaimsUsd"]) / Decimal(exog_formula["projectedFundYearMinutes"])
    require(exog_amount == money(exog_formula["expectedExactAdjustmentUsdPerMinute"]),
            "synthetic exogenous-cost formula mismatch")
    require("do not assert" in formulas["claimBoundary"], "formula claim boundary missing")

    print("Part 64 VRS rate engine: PASS")


if __name__ == "__main__":
    main()
