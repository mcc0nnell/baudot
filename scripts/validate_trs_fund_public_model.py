#!/usr/bin/env python3
"""Validate the public TRS Fund calibration fixture without external dependencies."""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "testkit" / "fund" / "rolka-loube-2025-26.json"
JOURNAL = ROOT / "interop" / "fineract" / "journal-contract-v1.json"


def money(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def d(value: str | int) -> Decimal:
    return Decimal(str(value))


def require(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"PASS {name}: {actual}")


def main() -> None:
    fixture = json.loads(FIXTURE.read_text())
    journal = json.loads(JOURNAL.read_text())

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

    for name, row in fixture["contribution"].items():
        ratio = d(row["netRequirement"]) / d(row["revenueBase"])
        reported = ratio.quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)
        require(f"{name} contribution factor", str(reported), row["reportedFactor"])

    accounts = journal["accounts"]
    for event_name, event in journal["events"].items():
        debit = event["debit"]
        credit = event["credit"]
        if debit == credit:
            raise AssertionError(f"{event_name}: debit and credit accounts must differ")
        if debit not in accounts or credit not in accounts:
            raise AssertionError(f"{event_name}: references unknown account")
        print(f"PASS {event_name}: Dr {debit} / Cr {credit}")

    boundary = fixture["claimBoundary"]
    require("public aggregates only", boundary["publicAggregatesOnly"], True)
    require("provider-level demand remains synthetic", boundary["providerLevelDemandSyntheticOnly"], True)
    require("no production Rolka Loube compatibility claim", boundary["productionRolkaLoubeCompatibilityClaimed"], False)
    require("no provider eligibility claim", boundary["providerEligibilityClaimed"], False)

    print("TRS Fund public calibration: PASS")


if __name__ == "__main__":
    main()
