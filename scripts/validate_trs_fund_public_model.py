#!/usr/bin/env python3
"""Validate public TRS Fund calibration and synthetic Fund scenarios."""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "testkit" / "fund" / "rolka-loube-2025-26.json"
CONTRIBUTORS = ROOT / "testkit" / "fund" / "contributor-assessments-2026-27.json"
JOURNAL = ROOT / "interop" / "fineract" / "journal-contract-v1.json"
LIVE_SCENARIO = ROOT / "testkit" / "fund" / "fineract-live-smoke-v1.json"


def money(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def d(value: str | int) -> Decimal:
    return Decimal(str(value))


def require(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"PASS {name}: {actual}")


def validate_public_fund_model(fixture: dict) -> None:
    rates = fixture["rates"]
    demand = fixture["analogDemandMinutes"]
    published = fixture["publishedAnalog"]

    old_rates = rates["2024-07-01/2025-06-30"]
    new_rates = rates["2025-07-01/2026-06-30"]
    may_jun_2025 = demand["2025-05-01/2025-06-30"]
    jul_apr = demand["2025-07-01/2026-04-30"]
    may_jun_2026 = demand["2026-05-01/2026-06-30"]

    service_totals = {}
    for service in ("TTY", "STS", "CTS"):
        requirement = money(
            d(may_jun_2025[service]) * d(old_rates[service])
            + d(jul_apr[service]) * d(new_rates[service])
        )
        reserve = money(d(may_jun_2026[service]) * d(new_rates[service]))
        total = requirement + reserve

        require(
            f"{service} fund requirement",
            requirement,
            published[service]["fundRequirement"],
        )
        require(
            f"{service} two-month reserve",
            reserve,
            published[service]["twoMonthReserve"],
        )
        require(
            f"{service} total fund requirement",
            total,
            published[service]["totalFundRequirement"],
        )
        service_totals[service] = total

    require(
        "gross analog fund requirement",
        sum(service_totals.values()),
        published["grossAnalogFundRequirement"],
    )

    analog_net = (
        published["grossAnalogFundRequirement"]
        + published["allocatedNdbedp"]
        + published["allocatedAdministrativeCosts"]
        - published["lessAllocatedFundBalance"]
    )
    require("net analog fund requirement", analog_net, published["netAnalogFundRequirement"])

    ip = fixture["publishedIpBased"]
    require(
        "gross IP-based fund requirement",
        ip["serviceRevenueRequirement"]
        + ip["allocatedNdbedp"]
        + ip["allocatedAdministrativeCosts"],
        ip["grossFundRequirement"],
    )
    require(
        "net IP-based fund requirement",
        ip["grossFundRequirement"] - ip["lessAllocatedFundBalance"],
        ip["netFundRequirement"],
    )

    fund = fixture["publishedFund"]
    require(
        "total service revenue requirement",
        published["grossAnalogFundRequirement"] + ip["serviceRevenueRequirement"],
        fund["totalServiceRevenueRequirement"],
    )
    require(
        "gross fund requirement",
        fund["totalServiceRevenueRequirement"]
        + fund["ndbedp"]
        + fund["administrativeCosts"],
        fund["grossFundRequirement"],
    )
    require(
        "net fund requirement",
        fund["grossFundRequirement"] - fund["lessProjectedFundBalance"],
        fund["netFundRequirement"],
    )

    # These rows intentionally reproduce the April 2025 Annual Report proposal,
    # not the later FCC-approved 2025-26 contribution factors. Approved factors
    # are versioned separately in the contributor-assessment fixture.
    for name, row in fixture["contribution"].items():
        ratio = d(row["netRequirement"]) / d(row["revenueBase"])
        reported = ratio.quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)
        require(f"{name} proposed contribution factor", str(reported), row["reportedFactor"])


def validate_contributor_assessments(contributors: dict) -> None:
    factors = contributors["approvedFactors"]
    internet_factor = d(factors["internetBased"]["factor"])
    non_internet_factor = d(factors["nonInternetBased"]["factor"])
    policy = contributors["billingPolicy"]
    threshold = d(policy["monthlyBillingAnnualAssessmentThreshold"])
    minimum = d(policy["minimumAnnualContributionForFilersWithEndUserRevenue"])
    months = d(policy["programMonths"])

    require("2026-27 Internet-based factor", str(internet_factor), "0.02276")
    require("2026-27 non-Internet-based factor", str(non_internet_factor), "0.00021")
    require("Internet-based factor maps to Form 499-A line", factors["internetBased"]["form499ALine"], "514a")
    require("non-Internet-based factor maps to Form 499-A line", factors["nonInternetBased"]["form499ALine"], "514b")

    for row in contributors["syntheticContributors"]:
        cid = row["id"]
        line514a = d(row["form499A"]["line514a"])
        line514b = d(row["form499A"]["line514b"])
        expected = row["expected"]

        internet = cents(line514a * internet_factor)
        non_internet = cents(line514b * non_internet_factor)
        raw = line514a * internet_factor + line514b * non_internet_factor
        annual = max(cents(raw), minimum)

        if "internetBasedAssessment" in expected:
            require(f"{cid} Internet-based assessment", internet, d(expected["internetBasedAssessment"]))
        if "nonInternetBasedAssessment" in expected:
            require(f"{cid} non-Internet-based assessment", non_internet, d(expected["nonInternetBasedAssessment"]))
        if "rawAssessment" in expected:
            require(f"{cid} raw assessment", raw, d(expected["rawAssessment"]))

        require(f"{cid} annual assessment", annual, d(expected["annualAssessment"]))

        monthly_allowed = annual > threshold and row["goodStanding"]
        cadence = "monthly" if monthly_allowed else "annual"
        require(f"{cid} billing cadence", cadence, expected["billingCadence"])

        if cadence == "monthly":
            monthly = cents(annual / months)
            require(f"{cid} monthly invoice", monthly, d(expected["monthlyInvoice"]))
            require(f"{cid} 12-month invoice total", monthly * months, annual)
        else:
            require(f"{cid} annual invoice", annual, d(expected["annualInvoice"]))

    boundary = contributors["claimBoundary"]
    require("synthetic contributor revenue only", boundary["syntheticContributorRevenueOnly"], True)
    require("no production contributor account data", boundary["productionContributorAccountDataUsed"], False)
    require("no production billing portal compatibility claim", boundary["productionBillingPortalCompatibilityClaimed"], False)


def validate_journal_contract(journal: dict) -> None:
    accounts = journal["accounts"]
    for event_name, event in journal["events"].items():
        debit = event["debit"]
        credit = event["credit"]
        if debit == credit:
            raise AssertionError(f"{event_name}: debit and credit accounts must differ")
        if debit not in accounts or credit not in accounts:
            raise AssertionError(f"{event_name}: references unknown account")
        print(f"PASS {event_name}: Dr {debit} / Cr {credit}")


def apply_synthetic_event(
    balances: dict[str, Decimal], journal: dict, event: dict, reverse: bool = False
) -> None:
    event_type = event["type"]
    if event_type not in journal["events"]:
        raise AssertionError(f"{event['id']}: unknown journal event type {event_type!r}")
    amount = d(event["amount"])
    if amount <= 0:
        raise AssertionError(f"{event['id']}: amount must be positive")
    mapping = journal["events"][event_type]
    sign = Decimal("-1") if reverse else Decimal("1")
    balances[mapping["debit"]] += amount * sign
    balances[mapping["credit"]] -= amount * sign


def validate_live_scenario_oracle(scenario: dict, journal: dict) -> None:
    require("live scenario schema", scenario["schema"], "baudot.trs-fund-fineract-live-scenario@1")
    require("live scenario is synthetic", scenario["claimBoundary"]["syntheticOnly"], True)
    require(
        "Fineract acceptance is not program authorization",
        scenario["claimBoundary"]["fineractAcceptanceIsProgramAuthorization"],
        False,
    )
    require(
        "live scenario uses no production payment network",
        scenario["claimBoundary"]["productionPaymentNetworkUsed"],
        False,
    )

    events = scenario["events"]
    ids = [row["id"] for row in events]
    require("live scenario event IDs unique", len(set(ids)), len(ids))

    balances = {code: Decimal("0.00") for code in journal["accounts"]}
    event_index = {row["id"]: row for row in events}
    for event in events:
        apply_synthetic_event(balances, journal, event)

    probe = scenario["reversalProbe"]
    if probe["eventId"] not in event_index:
        raise AssertionError(f"reversal target does not exist: {probe['eventId']}")
    if probe["repostAs"] in event_index:
        raise AssertionError(f"repost ID collides with original scenario event: {probe['repostAs']}")

    reversed_event = event_index[probe["eventId"]]
    apply_synthetic_event(balances, journal, reversed_event, reverse=True)
    repost = dict(reversed_event)
    repost["id"] = probe["repostAs"]
    apply_synthetic_event(balances, journal, repost)

    expected = {code: d(value) for code, value in scenario["expectedFinalBalances"].items()}
    actual = {code: balances[code] for code in expected}
    require("live scenario ledger-independent ending balances", actual, expected)
    require("live scenario contributor receivable reconciles", balances["1200"], Decimal("0.00"))
    require("live scenario provider payable reconciles", balances["2100"], Decimal("0.00"))
    require("live scenario ending Fund cash", balances["1100"], Decimal("4000.00"))

    known_invariants = {
        "FUND-ACC-001",
        "FUND-REC-001",
        "FUND-CLM-001",
        "FUND-DIS-001",
        "FUND-ADJ-001",
        "FUND-CLS-001",
        "FUND-AUD-001",
        "FUND-AUT-001",
    }
    unknown = set(scenario["requiredInvariants"]) - known_invariants
    require("live scenario invariant vocabulary", unknown, set())
    require(
        "live scenario does not overclaim closure",
        "FUND-CLS-001" in scenario["requiredInvariants"],
        False,
    )


def main() -> None:
    fixture = json.loads(FIXTURE.read_text())
    contributors = json.loads(CONTRIBUTORS.read_text())
    journal = json.loads(JOURNAL.read_text())
    live_scenario = json.loads(LIVE_SCENARIO.read_text())

    validate_public_fund_model(fixture)
    validate_contributor_assessments(contributors)
    validate_journal_contract(journal)
    validate_live_scenario_oracle(live_scenario, journal)

    boundary = fixture["claimBoundary"]
    require("public aggregates only", boundary["publicAggregatesOnly"], True)
    require("provider-level demand remains synthetic", boundary["providerLevelDemandSyntheticOnly"], True)
    require("no production Rolka Loube compatibility claim", boundary["productionRolkaLoubeCompatibilityClaimed"], False)
    require("no provider eligibility claim", boundary["providerEligibilityClaimed"], False)

    print("TRS Fund public calibration, contributor model, and live-scenario oracle: PASS")


if __name__ == "__main__":
    main()
