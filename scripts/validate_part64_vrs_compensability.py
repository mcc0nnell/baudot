#!/usr/bin/env python3
"""Validate synthetic 47 CFR § 64.604 VRS compensability contracts."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQ = ROOT / "testkit/part64/vrs-compensability-requirements-v1.json"
CASES = ROOT / "testkit/part64/fixtures/vrs-compensability-cases.json"
CERT = ROOT / "testkit/part64/fixtures/vrs-compensation-certification.json"


def load(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> None:
    requirements = load(REQ)
    cases_doc = load(CASES)
    certification = load(CERT)

    require(requirements["safety"], "safety declarations missing")
    require(all(value is False for value in requirements["safety"].values()),
            "public compensability corpus enables production/private data")

    req_ids = {item["id"] for item in requirements["requirements"]}
    require(req_ids == {
        "PART64-604-E2-MINUTES",
        "PART64-604-E6-COMPENSABLE",
        "PART64-604-F2-ELIGIBLE-PROVIDER",
        "PART64-604-D5-CERTIFICATION",
        "PART64-604-D6-AUDIT",
        "PART64-604-L-WITHHOLD",
        "PART64-604-C8-INCENTIVES",
        "PART64-604-C13-UNAUTHORIZED",
        "PART64-604-D4-TRAINING",
        "PART64-604-D6-INTERNATIONAL",
        "PART64-604-E-IVCS-SINGLE",
        "PART64-604-E-IVCS-START",
        "PART64-604-E-IVCS-END",
    }, "unexpected VRS compensability requirement set")

    # Executive certification is evidence for a request, not a self-issued Fund verdict.
    require(certification["scenario"] == "VRS-CERT-001", "certification scenario mismatch")
    signer = certification["signer"]
    require(signer["role"] in {"ceo", "cfo", "other-senior-executive"},
            "certification signer role is not eligible")
    require(signer["firstHandKnowledge"] is True, "certifier lacks first-hand knowledge")
    require(signer["realIdentityStored"] is False, "public fixture stores real executive identity")
    cert = certification["certification"]
    require(all(cert.values()), "executive certification is incomplete")
    require(certification["claimScope"]["productionClaim"] is False,
            "public fixture claims a production compensation request")

    cases = {item["scenario"]: item for item in cases_doc["cases"]}
    require(set(cases) == {
        "VRS-COMP-DOMESTIC-001",
        "VRS-COMP-PENDING-001",
        "VRS-COMP-INTERNATIONAL-DENY-001",
        "VRS-COMP-INTERNATIONAL-EXCEPTION-001",
        "VRS-COMP-TRAINING-DENY-001",
        "VRS-COMP-INCENTIVE-DENY-001",
        "VRS-COMP-UNAUTHORIZED-USE-001",
        "VRS-COMP-AUDIT-SUSPEND-001",
        "VRS-COMP-WITHHOLD-001",
        "VRS-IVCS-COMP-001",
        "VRS-IVCS-NO-USER-001",
    }, "unexpected compensability scenario set")

    domestic = cases["VRS-COMP-DOMESTIC-001"]
    for key in (
        "completedInternetBasedTrsCall", "providerCommissionCertified", "upstreamUserValidated",
        "callRecordComplete", "executiveCertificationPresent",
    ):
        require(domestic[key] is True, f"domestic positive arm missing {key}")
    require(domestic["prohibitedIncentiveKnown"] is False, "positive arm has prohibited incentive")
    require(domestic["unauthorizedOrUnnecessaryUseKnown"] is False,
            "positive arm has unauthorized/unnecessary use")
    require(domestic["providerInvolvedRemoteTraining"] is False,
            "positive arm is provider-involved training")
    require(domestic["internationalIpOrigin"] is False, "positive domestic arm is international")
    require(domestic["auditPaymentSuspended"] is False, "positive arm is audit-suspended")
    require(domestic["administratorDetermination"] == "compensable",
            "positive arm lacks external compensability determination")
    require(domestic["expected"]["establishedCompensable"] is True,
            "external compensability determination not reflected")

    pending = cases["VRS-COMP-PENDING-001"]
    require(pending["expected"]["eligibleToSeekCompensation"] is True,
            "pending arm should remain eligible to seek compensation")
    require(pending["administratorDetermination"] == "pending",
            "pending arm already has a final determination")
    require(pending["expected"]["establishedCompensable"] is False,
            "claim became compensable before administrator/Commission determination")
    require(pending["expected"]["paymentState"] == "not-yet-payable",
            "pending claim should not be payable")

    intl_deny = cases["VRS-COMP-INTERNATIONAL-DENY-001"]
    require(intl_deny["internationalIpOrigin"] is True, "international denial arm is domestic")
    travel = intl_deny["travelException"]
    require(not all(travel.values()), "international denial arm accidentally satisfies travel exception")
    require(intl_deny["expected"]["eligibleToSeekCompensation"] is False,
            "incomplete international travel exception was allowed")

    intl_ok = cases["VRS-COMP-INTERNATIONAL-EXCEPTION-001"]
    require(intl_ok["internationalIpOrigin"] is True, "travel-exception arm is not international")
    require(all(intl_ok["travelException"].values()), "travel exception evidence incomplete")
    require(intl_ok["expected"]["internationalRuleAllowsCandidate"] is True,
            "complete travel exception did not pass international gate")
    require(intl_ok["expected"]["establishedCompensable"] is False,
            "travel exception itself incorrectly established compensability")

    training = cases["VRS-COMP-TRAINING-DENY-001"]
    require(training["providerInvolvedRemoteTraining"] is True,
            "training negative arm lacks provider involvement")
    require(len(training["providerInvolvement"]) > 0, "training involvement evidence missing")
    require(training["expected"]["eligibleToSeekCompensation"] is False,
            "provider-involved training was treated as compensable candidate")

    incentive = cases["VRS-COMP-INCENTIVE-DENY-001"]
    require(incentive["prohibitedIncentiveKnown"] is True, "incentive negative arm missing")
    require(incentive["expected"]["serviceFundEligible"] is False,
            "prohibited incentive did not make service ineligible in modeled arm")
    require(incentive["expected"]["eligibleToSeekCompensation"] is False,
            "incentive-tainted service was allowed to seek compensation")

    unauthorized = cases["VRS-COMP-UNAUTHORIZED-USE-001"]
    require(unauthorized["unauthorizedOrUnnecessaryUseKnown"] is True,
            "unauthorized-use negative arm missing")
    require(unauthorized["expected"]["seekPaymentAllowed"] is False,
            "known unauthorized/unnecessary-use minutes were allowed for billing")
    require(unauthorized["expected"]["reportAsSoonAsPracticable"] is True,
            "known prohibited practice did not produce reporting obligation")

    audit = cases["VRS-COMP-AUDIT-SUSPEND-001"]
    require(audit["auditRequested"] is True, "audit suspension arm lacks audit request")
    require(audit["submittedToAudit"] is False and audit["verificationDocumentationProvided"] is False,
            "audit suspension control accidentally cured")
    require(audit["expected"]["automaticPaymentSuspension"] is True,
            "audit refusal did not trigger automatic suspension")
    require(audit["expected"]["suspensionUntilCured"] is True,
            "audit suspension is not modeled as cure-dependent")

    withheld = cases["VRS-COMP-WITHHOLD-001"]
    require(withheld["monthsFromClaimToWithholdNotice"] <= 2,
            "withholding notice exceeds modeled two-month review window")
    require(withheld["providerResponseMonthsAfterNotice"] <= 2,
            "provider justification response exceeds two-month response window")
    require(withheld["expected"]["paymentBeforeDetermination"] is False,
            "withheld claim paid before compensability determination")
    require(withheld["administratorDetermination"] == "compensable",
            "withholding release arm lacks compensable determination")
    require(withheld["expected"]["establishedCompensable"] is True,
            "released claim did not reflect final compensability determination")

    ivcs = cases["VRS-IVCS-COMP-001"]
    require(ivcs["conferenceCount"] == 1 and ivcs["expected"]["singleCompensationCall"] is True,
            "integrated VRS conference was split into multiple compensation calls")
    identification_delay = int((instant(ivcs["requestingUserIdentifiedAt"]) - instant(ivcs["caEnteredAt"])).total_seconds())
    require(0 <= identification_delay <= 300, "requesting VRS user not identified within five minutes")
    require(ivcs["expected"]["compensableStart"] == ivcs["caEnteredAt"],
            "IVCS compensable start must be CA conference entry after timely identification")

    events = ivcs["terminationEvents"]
    end_candidates = [
        instant(events["caDisconnectedAt"]),
        instant(events["allNonSigningDisconnectedAt"]),
        instant(events["allSigningDisconnectedAt"]),
    ]
    if not events["newRegisteredRequestWithinFiveMinutes"]:
        end_candidates.append(instant(events["requestingUserFiveMinuteExpiryAt"]))
    expected_end = min(end_candidates)
    require(instant(ivcs["expected"]["compensableEnd"]) == expected_end,
            "IVCS compensable end is not the earliest applicable event")
    seconds = int((expected_end - instant(ivcs["expected"]["compensableStart"])).total_seconds())
    require(ivcs["expected"]["conversationSeconds"] == seconds,
            "IVCS compensable seconds do not match preserved timestamps")
    require(ivcs["expected"]["establishedCompensable"] is False,
            "IVCS timing eligibility incorrectly became a Fund determination")

    no_user = cases["VRS-IVCS-NO-USER-001"]
    require(no_user["requestingUserIdentifiedAt"] is None,
            "no-user IVCS control unexpectedly identified requesting user")
    require(no_user["elapsedWithoutIdentificationSeconds"] >= 300,
            "no-user IVCS control ended before five-minute identification boundary")
    require(no_user["expected"]["callMustBeIdentifiedNonCompensable"] is True,
            "IVCS without identified requesting user was not marked non-compensable")

    print("Part 64 VRS compensability contract: PASS")


if __name__ == "__main__":
    main()
