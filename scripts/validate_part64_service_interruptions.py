#!/usr/bin/env python3
"""Validate synthetic 47 CFR § 64.606(h) service-interruption contracts."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQ = ROOT / "testkit/part64/service-interruption-requirements-v1.json"
CASES = ROOT / "testkit/part64/fixtures/service-interruption-cases.json"


def load(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    requirements = load(REQ)
    cases_doc = load(CASES)

    require(requirements["safety"], "safety declarations missing")
    require(all(value is False for value in requirements["safety"].values()),
            "public interruption corpus enables production/real regulatory data")

    req_ids = {item["id"] for item in requirements["requirements"]}
    require(req_ids == {
        "PART64-606-H1-CONTINUITY",
        "PART64-606-H2-PLANNED-30",
        "PART64-606-H2-DECISION-35",
        "PART64-606-H3-SHORT-UNFORESEEN",
        "PART64-606-H3-RESTORE",
        "PART64-606-H4-CONSEQUENCE-BOUNDARY",
    }, "unexpected service-interruption requirement set")

    cases = {item["scenario"]: item for item in cases_doc["cases"]}
    require(set(cases) == {
        "VRS-OUTAGE-PLANNED-030-PASS",
        "VRS-OUTAGE-PLANNED-060DAY-FAIL",
        "VRS-OUTAGE-PLANNED-029-001",
        "VRS-OUTAGE-UNFORESEEN-002DAY-PASS",
        "VRS-OUTAGE-UNFORESEEN-003DAY-FAIL",
        "VRS-OUTAGE-RESTORE-003DAY-FAIL",
        "VRS-OUTAGE-WEBSITE-NOTICE-FAIL",
    }, "unexpected service-interruption scenario set")

    planned = cases["VRS-OUTAGE-PLANNED-030-PASS"]
    require(planned["interruptionType"] == "voluntary-planned" and planned["durationMinutes"] >= 30,
            "planned 30-minute boundary arm malformed")
    require(planned["expected"]["priorAuthorizationRequired"] is True,
            "30-minute voluntary interruption must require prior authorization")
    require(planned["authorizationRequestDaysBefore"] >= 60 and planned["expected"]["requestTimely"] is True,
            "60-day prior-authorization request boundary should pass")
    require(all(planned["requestContains"].values()), "planned interruption request package incomplete")
    require(planned["commissionDecision"] == "authorized",
            "positive planned interruption arm lacks external authorization input")
    require(planned["decisionDaysBeforeInterruption"] >= 35 and planned["expected"]["decisionTimingConforming"] is True,
            "35-day CGB decision timing boundary not preserved")
    require(planned["expected"]["interruptionAuthorizedByModeledInput"] is True,
            "external authorization input not reflected")

    late_request = cases["VRS-OUTAGE-PLANNED-060DAY-FAIL"]
    require(late_request["durationMinutes"] >= 30, "late-request control is under 30 minutes")
    require(late_request["authorizationRequestDaysBefore"] < 60,
            "late-request control accidentally satisfies 60-day boundary")
    require(late_request["expected"]["requestTimely"] is False,
            "59-day planned interruption request should fail")
    require(late_request["commissionDecision"] == "not-determined" and
            late_request["expected"]["interruptionAuthorizedByModeledInput"] is False,
            "late-request arm fabricated authorization")
    require(late_request["expected"]["possibleEnforcementExposure"] is True and
            late_request["expected"]["actualEnforcementOutcome"] == "not-determined",
            "late request must preserve enforcement authority boundary")

    short = cases["VRS-OUTAGE-PLANNED-029-001"]
    require(short["durationMinutes"] < 30, "short voluntary interruption is not under 30 minutes")
    require(short["expected"]["priorAuthorizationRequired"] is False,
            "sub-30-minute voluntary interruption incorrectly requires prior authorization")
    require(short["writtenNotificationBusinessDaysAfterCommencement"] <= 2 and
            short["expected"]["postCommencementNoticeTimely"] is True,
            "short voluntary interruption notice missed two-business-day boundary")
    require(short["accessibleStatusWebsiteNotice"] and short["statusNoticeUpdatedTimely"],
            "short voluntary interruption lacks accessible/timely status notice")

    unforeseen = cases["VRS-OUTAGE-UNFORESEEN-002DAY-PASS"]
    require(unforeseen["interruptionType"] == "unforeseen-beyond-provider-control",
            "unforeseen control has wrong interruption type")
    require(unforeseen["writtenNotificationBusinessDaysAfterCommencement"] <= 2 and
            unforeseen["expected"]["initialNoticeTimely"] is True,
            "unforeseen interruption initial notice should pass at two business days")
    require(unforeseen["accessibleStatusWebsiteNotice"] and unforeseen["statusNoticeUpdatedTimely"],
            "unforeseen interruption lacks accessible/timely status notice")
    require(unforeseen["serviceRestoredAtFirstReport"] is False,
            "unforeseen restoration control should still be open at first report")
    require(unforeseen["secondReportBusinessDaysAfterRestoration"] <= 2 and
            unforeseen["restorationExplanationPresent"] and unforeseen["expected"]["secondReportTimely"] is True,
            "restoration second report should pass at two business days")

    late_initial = cases["VRS-OUTAGE-UNFORESEEN-003DAY-FAIL"]
    require(late_initial["writtenNotificationBusinessDaysAfterCommencement"] > 2 and
            late_initial["expected"]["initialNoticeTimely"] is False,
            "three-business-day unforeseen notice should fail")
    require(late_initial["expected"]["possibleEnforcementExposure"] is True and
            late_initial["expected"]["actualEnforcementOutcome"] == "not-determined",
            "late initial notice fabricated enforcement outcome")

    late_restore = cases["VRS-OUTAGE-RESTORE-003DAY-FAIL"]
    require(late_restore["writtenNotificationBusinessDaysAfterCommencement"] <= 2 and
            late_restore["expected"]["initialNoticeTimely"] is True,
            "late-restoration control must have timely initial notice")
    require(late_restore["serviceRestoredAtFirstReport"] is False,
            "late-restoration control should require second report")
    require(late_restore["secondReportBusinessDaysAfterRestoration"] > 2 and
            late_restore["expected"]["secondReportTimely"] is False,
            "three-business-day restoration report should fail")
    require(late_restore["expected"]["actualEnforcementOutcome"] == "not-determined",
            "late restoration report fabricated enforcement outcome")

    website = cases["VRS-OUTAGE-WEBSITE-NOTICE-FAIL"]
    require(website["durationMinutes"] < 30, "website-notice control should use short interruption")
    require(website["writtenNotificationBusinessDaysAfterCommencement"] <= 2,
            "website-notice control should otherwise have timely written notification")
    require(website["accessibleStatusWebsiteNotice"] is False or website["statusNoticeUpdatedTimely"] is False,
            "website-notice negative control accidentally complete")
    require(website["expected"]["notificationPackageComplete"] is False,
            "missing accessible/timely website notice did not fail package")
    require(website["expected"]["actualEnforcementOutcome"] == "not-determined",
            "website-notice failure fabricated enforcement outcome")

    print("Part 64 VRS service interruption contract: PASS")


if __name__ == "__main__":
    main()
