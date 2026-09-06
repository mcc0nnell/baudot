#!/usr/bin/env python3
"""Validate the synthetic Part 64 registration/numbering/validation contract."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQ = ROOT / "testkit/part64/requirements-v1.json"
REG = ROOT / "testkit/part64/fixtures/registration-valid.json"
NUM = ROOT / "testkit/part64/fixtures/numbering-directory.json"
VAL = ROOT / "testkit/part64/fixtures/validation-cases.json"


def load(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    requirements = load(REQ)
    registration = load(REG)
    numbering = load(NUM)
    validation = load(VAL)

    # Clean-room boundary: these must remain false in the public corpus.
    safety = requirements["safety"]
    forbidden = {
        "liveTrsNumberingDirectory",
        "realSubscriberData",
        "providerCredentials",
        "productionCallRecords",
        "realEmergencyCalls",
    }
    require(forbidden <= set(safety), "missing clean-room safety declarations")
    require(all(safety[key] is False for key in forbidden), "public corpus enables forbidden live data/action")

    reqs = {item["id"]: item for item in requirements["requirements"]}
    expected_ids = {
        "PART64-611-REG",
        "PART64-613-NUM",
        "PART64-615-VAL-PASS",
        "PART64-615-VAL-FAIL",
        "PART64-615-EMERG",
    }
    require(expected_ids <= set(reqs), "required Part 64 rows missing")
    require(len({item["scenario"] for item in requirements["requirements"]}) == len(requirements["requirements"]),
            "requirement scenarios must be unique")

    # Registration fixture proves only synthetic local state.
    require(registration["scenario"] == "ITRS-REG-001", "unexpected registration scenario")
    require(registration["nanpNumber"].startswith("+1"), "registration must use NANP-shaped number")
    require(registration["defaultProvider"].endswith(".example"), "provider domain must be reserved example domain")
    require(registration["registeredLocation"]["synthetic"] is True, "Registered Location must remain synthetic")
    require(registration["provenance"] == "baudot-authored-synthetic-fixture", "registration provenance missing")

    # Numbering fixture preserves mapping/routing as a separate fact.
    entries = {item["nanpNumber"]: item for item in numbering["entries"]}
    require(registration["nanpNumber"] in entries, "registered number absent from synthetic directory")
    route = entries[registration["nanpNumber"]]
    require(route["routeOwner"] == registration["defaultProvider"], "default provider and directory route owner diverge")
    require(route["uri"].startswith("sip:"), "directory mapping must produce a SIP URI")
    require(route["routeOwner"].endswith(".example"), "route owner must use reserved example domain")

    # Validation cases enforce routable != validated and keep 911 offline-only.
    cases = {item["scenario"]: item for item in validation["cases"]}
    positive = cases["ITRS-VAL-001"]
    negative = cases["ITRS-VAL-002"]
    emergency = cases["ITRS-VAL-911"]
    porting = cases["ITRS-VAL-PORT-PENDING"]

    require(positive["routeExists"] is True and positive["expected"]["validated"] is True,
            "positive validation arm malformed")
    require(positive["expected"]["compensable"] == "not-determined",
            "successful validation must not imply compensability")

    require(negative["routeExists"] is True, "negative arm must remain routable")
    require(negative["expected"]["validated"] is False, "negative arm must fail validation")
    require(negative["expected"]["ordinaryCallPlacementAllowed"] is False,
            "ordinary call placement must fail when eligibility is not validated")
    require(negative["expected"]["compensable"] is False,
            "failed validation must not be compensation eligible")

    require(emergency["emergency"] is True and emergency["offlineOnly"] is True,
            "emergency arm must remain offline-only")
    require(emergency["expected"]["validationRequiredForPlacement"] is False,
            "911 arm must preserve the validation exception")
    require(emergency["expected"]["realEmergencyRoutingExercised"] is False,
            "public validation must never exercise real 911 routing")

    require(porting["identityVerification"] == "pending", "porting arm must be identity-pending")
    require(porting["submittedWithinDays"] <= 14, "provisional identity window exceeds two weeks")
    require(porting["routeState"] == "provisional-porting-in", "porting route must be explicitly provisional")
    require(porting["expected"]["compensationBeforeVerification"] is False,
            "pending identity verification must not imply compensation entitlement")

    print("Part 64 registration/numbering/validation contract: PASS")


if __name__ == "__main__":
    main()
