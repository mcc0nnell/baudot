#!/usr/bin/env python3
"""Validate synthetic 47 CFR § 64.604 VRS call-evidence contracts."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQ = ROOT / "testkit/part64/vrs-call-evidence-requirements-v1.json"
CDR = ROOT / "testkit/part64/fixtures/vrs-call-records.json"
SOA = ROOT / "testkit/part64/fixtures/vrs-speed-of-answer-months.json"


def load(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle, parse_float=Decimal)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def seconds_between(start: str, end: str) -> int:
    return int((instant(end) - instant(start)).total_seconds())


def minutes_decimal(seconds: int) -> Decimal:
    return Decimal(seconds) / Decimal(60)


def main() -> None:
    requirements = load(REQ)
    cdr_doc = load(CDR)
    soa_doc = load(SOA)

    require(requirements["safety"], "safety declarations missing")
    require(all(value is False for value in requirements["safety"].values()),
            "public §64.604 corpus enables production/private data")

    req_ids = {item["id"] for item in requirements["requirements"]}
    require(req_ids == {
        "PART64-604-VRS-SOA",
        "PART64-604-CDR-FIELDS",
        "PART64-604-SOA-SUBMISSION",
        "PART64-604-AUTOMATED-RECORDS",
        "PART64-604-CDR-RETENTION",
        "PART64-604-IVCS-CDR",
    }, "unexpected §64.604 requirement set")

    capture = cdr_doc["capture"]
    require(capture["automatedElectronic"] is True, "CDR capture must be automated/electronic")
    require(capture["standardizedFormat"] == "json", "CDR fixture must declare standardized format")
    require(capture["humanInterventionDuringCallTiming"] is False,
            "human intervention during call timing is not permitted in this evidence model")
    require(capture["retentionYears"] >= 5, "CDR retention horizon is less than five years")
    require(capture["easilyRetrievable"] is True, "CDR retention is not marked easily retrievable")

    records = {record["scenario"]: record for record in cdr_doc["records"]}
    require(set(records) == {"VRS-CDR-001", "VRS-IVCS-CDR-001"}, "unexpected CDR scenario set")

    ordinary = records["VRS-CDR-001"]
    for key in (
        "callRecordId", "caId", "sessionStart", "sessionEnd", "conversationStart", "conversationEnd",
        "incoming", "outbound", "totalConversationMinutes", "totalSessionMinutes", "handlingLocation",
        "initiatingUrl",
    ):
        require(key in ordinary, f"ordinary CDR field missing: {key}")

    require(ordinary["incoming"]["telephoneNumber"].startswith("+1"), "incoming number not NANP-shaped")
    require(ordinary["outbound"]["telephoneNumber"].startswith("+1"), "outbound number not NANP-shaped")
    require(ordinary["incoming"]["ipAddress"].startswith("192.0.2."), "incoming IP not documentation-range")
    require(ordinary["outbound"]["ipAddress"].startswith("198.51.100."), "outbound IP not documentation-range")
    require(ordinary["initiatingUrl"].startswith("https://") and ".example/" in ordinary["initiatingUrl"],
            "initiating URL must be synthetic example-domain HTTPS")
    require(ordinary["handlingLocation"]["id"].startswith("CENTER-EXAMPLE-"),
            "handling-location ID must remain synthetic")

    session_seconds = seconds_between(ordinary["sessionStart"], ordinary["sessionEnd"])
    conversation_seconds = seconds_between(ordinary["conversationStart"], ordinary["conversationEnd"])
    require(session_seconds > 0 and conversation_seconds > 0, "non-positive CDR duration")
    require(instant(ordinary["sessionStart"]) <= instant(ordinary["conversationStart"]),
            "conversation begins before session")
    require(instant(ordinary["conversationEnd"]) <= instant(ordinary["sessionEnd"]),
            "conversation ends after session")
    require(minutes_decimal(session_seconds) == ordinary["totalSessionMinutes"],
            "session minutes do not match timestamps")
    require(minutes_decimal(conversation_seconds) == ordinary["totalConversationMinutes"],
            "conversation minutes do not match timestamps")
    require(ordinary["compensable"] == "not-determined", "complete CDR must not imply compensability")

    ivcs = records["VRS-IVCS-CDR-001"]
    require("integratedVrs" in ivcs, "integrated VRS conference identity missing")
    require(ivcs["integratedVrs"]["videoConferenceId"].startswith("CONF-EXAMPLE-"),
            "IVCS conference ID must remain synthetic")
    require(ivcs["integratedVrs"]["requestingVrsUserId"].startswith("VRS-USER-EXAMPLE-"),
            "IVCS requesting-user ID must remain synthetic")
    require(ivcs["integratedVrs"]["platform"] == "synthetic-ivcs-fixture",
            "IVCS fixture must not promote a named production platform")
    require(ivcs["compensable"] == "not-determined", "IVCS CDR must not imply compensability")
    ivcs_session = seconds_between(ivcs["sessionStart"], ivcs["sessionEnd"])
    ivcs_conversation = seconds_between(ivcs["conversationStart"], ivcs["conversationEnd"])
    require(minutes_decimal(ivcs_session) == ivcs["totalSessionMinutes"], "IVCS session duration mismatch")
    require(minutes_decimal(ivcs_conversation) == ivcs["totalConversationMinutes"],
            "IVCS conversation duration mismatch")

    soa_capture = soa_doc["capture"]
    require(soa_capture["automatedElectronic"] is True, "SOA capture must be automated/electronic")
    require(soa_capture["humanInterventionDuringCallTiming"] is False,
            "SOA timing cannot permit human intervention")

    months = {month["scenario"]: month for month in soa_doc["months"]}
    require(set(months) == {"VRS-SOA-PASS-001", "VRS-SOA-FAIL-001"}, "unexpected SOA scenario set")

    for scenario, month in months.items():
        require(month["thresholdPercent"] == 80, f"{scenario}: VRS threshold percent drifted")
        require(month["thresholdSeconds"] == 120, f"{scenario}: VRS threshold seconds drifted")
        attempts = [attempt for attempt in month["attempts"] if attempt["eligibleForSoaCorpus"]]
        require(len(attempts) == len(month["attempts"]),
                f"{scenario}: validation-prohibited/excluded calls belong outside this fixture")
        denominator = len(attempts)
        require(denominator > 0, f"{scenario}: empty SOA denominator")
        timely = sum(
            1 for attempt in attempts
            if not attempt["abandoned"]
            and attempt["elapsedToCaAnswerSeconds"] is not None
            and attempt["elapsedToCaAnswerSeconds"] <= month["thresholdSeconds"]
        )
        abandoned = [attempt for attempt in attempts if attempt["abandoned"]]
        require(abandoned, f"{scenario}: abandoned-call denominator control missing")
        require(all(attempt["elapsedToCaAnswerSeconds"] is None for attempt in abandoned),
                f"{scenario}: abandoned control has a CA-answer timestamp")
        percent = Decimal(timely * 100) / Decimal(denominator)
        expected = month["expected"]
        require(expected["denominator"] == denominator, f"{scenario}: denominator mismatch")
        require(expected["timelyCaAnswers"] == timely, f"{scenario}: timely-answer count mismatch")
        require(expected["percent"] == percent, f"{scenario}: SOA percentage mismatch")
        require(expected["compliant"] is (percent >= Decimal(month["thresholdPercent"])),
                f"{scenario}: compliance result contradicts calculated percentage")

    require(months["VRS-SOA-PASS-001"]["expected"]["compliant"] is True,
            "80% boundary arm must pass")
    require(months["VRS-SOA-FAIL-001"]["expected"]["compliant"] is False,
            "70% negative arm must fail")

    print("Part 64 VRS call evidence and speed-of-answer contract: PASS")


if __name__ == "__main__":
    main()
