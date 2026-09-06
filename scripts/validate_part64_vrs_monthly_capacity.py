#!/usr/bin/env python3
"""Validate synthetic 47 CFR § 64.604(d) monthly VRS capacity controls."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQ = ROOT / "testkit/part64/vrs-monthly-capacity-requirements-v1.json"
CASES = ROOT / "testkit/part64/fixtures/vrs-monthly-capacity-cases.json"
REPORT = ROOT / "testkit/part64/fixtures/vrs-home-workstation-monthly-report.json"


def load(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle, parse_float=Decimal)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def cap(total: Decimal, projected: Decimal, fraction: Decimal) -> Decimal:
    return max(total * fraction, projected * fraction)


def main() -> None:
    requirements = load(REQ)
    cases_doc = load(CASES)
    report = load(REPORT)

    require(requirements["safety"], "safety declarations missing")
    require(all(value is False for value in requirements["safety"].values()),
            "public monthly-capacity corpus enables production/private data")

    req_ids = {item["id"] for item in requirements["requirements"]}
    require(req_ids == {
        "PART64-604-D1-THIRD-PARTY-30",
        "PART64-604-D1-MARKETING-NONCOMP",
        "PART64-604-D3-CA-NO-MINUTE-INCENTIVE",
        "PART64-604-D7-ATHOME-80",
        "PART64-604-D7-HOME-RECORDS",
        "PART64-604-D7-HOME-REPORT",
    }, "unexpected monthly-capacity requirement set")

    cases = {item["scenario"]: item for item in cases_doc["cases"]}
    require(set(cases) == {
        "VRS-MONTHLY-THIRD-PARTY-PASS-001",
        "VRS-MONTHLY-THIRD-PARTY-FAIL-001",
        "VRS-MONTHLY-ATHOME-PASS-001",
        "VRS-MONTHLY-ATHOME-FAIL-001",
        "VRS-MONTHLY-ATHOME-UNAUTHORIZED-001",
        "VRS-MARKETING-NONCOMP-001",
        "VRS-CA-MINUTE-INCENTIVE-001",
        "VRS-HOME-OVERSIGHT-001",
    }, "unexpected monthly-capacity scenario set")

    third_pass = cases["VRS-MONTHLY-THIRD-PARTY-PASS-001"]
    third_fail = cases["VRS-MONTHLY-THIRD-PARTY-FAIL-001"]
    for item, expected_within in ((third_pass, True), (third_fail, False)):
        calculated = cap(
            Decimal(item["totalCompensatedMinutes"]),
            Decimal(item["averageProjectedMonthlyConversationMinutes"]),
            Decimal("0.30"),
        )
        require(calculated == Decimal(item["expected"]["monthlyCapMinutes"]),
                "third-party interpretation cap calculation mismatch")
        within = Decimal(item["thirdPartyInterpretationMinutes"]) <= calculated
        require(within is expected_within and item["expected"]["withinCap"] is expected_within,
                "third-party interpretation cap boundary mismatch")

    home_pass = cases["VRS-MONTHLY-ATHOME-PASS-001"]
    home_fail = cases["VRS-MONTHLY-ATHOME-FAIL-001"]
    for item, expected_within in ((home_pass, True), (home_fail, False)):
        require(item["commissionAuthorizedAtHomeProgram"] is True,
                "at-home cap arm lacks Commission authorization input")
        calculated = cap(
            Decimal(item["totalCompensatedMinutes"]),
            Decimal(item["averageProjectedMonthlyConversationMinutes"]),
            Decimal("0.80"),
        )
        require(calculated == Decimal(item["expected"]["monthlyCapMinutes"]),
                "at-home VRS cap calculation mismatch")
        within = Decimal(item["atHomeMinutes"]) <= calculated
        require(within is expected_within and item["expected"]["withinCap"] is expected_within,
                "at-home VRS cap boundary mismatch")

    unauthorized_home = cases["VRS-MONTHLY-ATHOME-UNAUTHORIZED-001"]
    require(unauthorized_home["commissionAuthorizedAtHomeProgram"] is False,
            "unauthorized-home negative arm is marked authorized")
    require(unauthorized_home["atHomeMinutes"] > 0,
            "unauthorized-home negative arm has no home minutes")
    require(unauthorized_home["expected"]["atHomeHandlingAllowedByThisModel"] is False,
            "at-home handling was allowed without Commission authorization input")
    require(unauthorized_home["expected"]["withinCap"] is False,
            "unauthorized home handling cannot pass solely on percentage math")

    marketing = cases["VRS-MARKETING-NONCOMP-001"]
    require(marketing["authorizedThirdPartyFunction"] == "marketing-outreach",
            "marketing negative arm has wrong third-party function")
    require(marketing["vrsMinutesUsed"] > 0, "marketing negative arm has no VRS minutes")
    require(marketing["expected"]["perMinuteCompensable"] is False,
            "marketing/outreach VRS minutes were treated as per-minute compensable")
    require(marketing["expected"]["minutesEligibleForPayableJournal"] == 0,
            "marketing/outreach minutes leaked into payable journal input")

    incentive = cases["VRS-CA-MINUTE-INCENTIVE-001"]
    require(incentive["benefitBasis"] in {
        "session-minutes-relayed", "conversation-minutes-relayed", "calls-relayed"
    }, "CA incentive arm does not use a prohibited volume basis")
    require(incentive["expected"]["permitted"] is False and
            incentive["expected"]["policyResult"] == "reject",
            "minute/call-based CA compensation was not rejected")

    oversight = cases["VRS-HOME-OVERSIGHT-001"]
    require(oversight["homeWorkstations"] == 40,
            "oversight fixture changed; update exact 5-percent boundary test")
    minimum_inspections = 2
    require(oversight["expected"]["minimumInspections"] == minimum_inspections,
            "home-workstation minimum inspection count mismatch")
    require(oversight["randomUnannouncedInspections"] >= minimum_inspections and
            oversight["expected"]["inspectionThresholdMet"] is True,
            "five-percent home-workstation inspection threshold not met")
    require(oversight["recordsRetentionYears"] >= 5 and
            oversight["expected"]["retentionThresholdMet"] is True,
            "home-workstation retention threshold not met")
    require(oversight["conversationContentRetained"] is False,
            "home-workstation records fixture retains interpreted conversation content")

    require(report["scenario"] == "VRS-HOME-REPORT-001", "monthly report scenario mismatch")
    require(report["productionReport"] is False, "public fixture claims a production monthly report")
    require(len(report["workstations"]) >= 1, "monthly report contains no workstations")
    for workstation in report["workstations"]:
        require(workstation["workstationId"].startswith("HOME-EXAMPLE-"),
                "home workstation ID is not synthetic")
        require(workstation["syntheticAddress"] is True and workstation["streetAddress"],
                "home workstation address evidence missing or not synthetic")
        require(workstation["caIds"] and all(value.startswith("CA-EXAMPLE-") for value in workstation["caIds"]),
                "home workstation CA identifiers missing or non-synthetic")
        center = workstation["supervisingCallCenter"]
        require(center["callCenterId"].startswith("CENTER-EXAMPLE-"),
                "supervising call-center ID is not synthetic")
        require(center["syntheticAddress"] is True and center["streetAddress"],
                "supervising call-center address evidence missing or non-synthetic")
        require(center["supervisorName"].startswith("Example "),
                "supervisor identity is not synthetic")

    print("Part 64 VRS monthly capacity contract: PASS")


if __name__ == "__main__":
    main()
