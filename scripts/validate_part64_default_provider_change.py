#!/usr/bin/env python3
"""Validate the synthetic Part 64 default-provider change contract."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQ = ROOT / "testkit/part64/default-provider-change-requirements-v1.json"
LOA = ROOT / "testkit/part64/fixtures/default-provider-loa.json"
TPV = ROOT / "testkit/part64/fixtures/default-provider-tpv.json"
CASES = ROOT / "testkit/part64/fixtures/default-provider-change-cases.json"


def load(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle, parse_float=Decimal)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def example_provider(value: str) -> bool:
    return value.endswith(".example")


def main() -> None:
    requirements = load(REQ)
    loa = load(LOA)
    tpv = load(TPV)
    cases_doc = load(CASES)

    # Public-repository safety boundary.
    safety = requirements["safety"]
    require(safety, "safety declarations missing")
    require(all(value is False for value in safety.values()),
            "default-provider public corpus enables live/private data")

    reqs = {item["id"]: item for item in requirements["requirements"]}
    expected_ids = {
        "PART64-630-APPLICABILITY",
        "PART64-631-AUTH-VERIFY",
        "PART64-631-MULTI-SERVICE",
        "PART64-631-TPV",
        "PART64-631-IMPLEMENT-60",
        "PART64-631-CONTINUITY",
        "PART64-631-TRANSFER",
        "PART64-632-LOA",
        "PART64-633-COMPLAINT",
        "PART64-634-PREPAY",
        "PART64-635-PAID",
        "PART64-636-NO-FREEZE",
    }
    require(expected_ids <= set(reqs), "required default-provider rule rows missing")

    # § 64.632 LOA structure. Identity values are deliberately absent.
    require(loa["scenario"] == "ITRS-CHANGE-LOA-001", "LOA scenario mismatch")
    require(loa["separateDocumentOrScreen"] is True, "LOA must be separate document/screen")
    require(loa["title"] == "Letter of Authorization to Change my Default Provider",
            "LOA prescribed title mismatch")
    require(loa["authorizingLanguageOnly"] is True, "LOA contains non-authorizing content")
    require(loa["signed"] is True and loa["dated"] is True, "LOA must be signed and dated")
    require(loa["electronicSignature"] is True and loa["esignConsumerDisclosuresPresent"] is True,
            "electronic LOA disclosure state incomplete")
    require(loa["language"] == loa["promotionalMaterialLanguage"], "LOA language inconsistency")
    require(loa["registeredIdentity"]["namePresent"] is True, "registered name presence missing")
    require(loa["registeredIdentity"]["addressPresent"] is True, "registered address presence missing")
    require(loa["registeredIdentity"]["valuesStoredInPublicFixture"] is False,
            "public LOA fixture stores identity values")
    require(len(loa["telephoneNumbers"]) >= 1, "LOA telephone number missing")
    require(all(number.startswith("+1") for number in loa["telephoneNumbers"]),
            "LOA numbers must be synthetic NANP-shaped values")
    require(example_provider(loa["originalDefaultProvider"]) and example_provider(loa["newDefaultProvider"]),
            "LOA providers must use reserved example domains")
    require(loa["originalDefaultProvider"] != loa["newDefaultProvider"], "LOA provider change is a no-op")
    require(loa["changeDecisionExplicit"] is True, "provider-change decision missing")
    require(loa["newProviderAgencyDesignationExplicit"] is True, "new-provider agency designation missing")
    require(loa["oneDefaultProviderPerNumberAcknowledged"] is True,
            "single-default-provider acknowledgment missing")
    require(loa["realSubscriberData"] is False, "LOA fixture claims real subscriber data")

    # § 64.631(c)(2) TPV independence, format, content, recording and retention.
    verifier = tpv["verifier"]
    require(all(verifier[key] is False for key in (
        "ownedManagedControlledOrDirectedByProvider",
        "ownedManagedControlledOrDirectedByMarketingAgent",
        "financialIncentiveToConfirmOrders",
    )), "third-party verifier is not independent")
    require(verifier["physicallySeparate"] is True, "third-party verifier is not physically separate")
    require(tpv["providerDroppedAfterThreeWayConnection"] is True,
            "provider must leave modeled three-way verification after connection")
    require(tpv["nonMisleading"] is True, "TPV is marked misleading")
    for key in (
        "newProviderIdentifiedAtStart",
        "changeMeaningConfirmed",
        "userIdentityConfirmed",
        "userIsPersonOnVerificationConfirmed",
        "changeRequestedConfirmed",
        "notUpgradeConfirmed",
        "equipmentReturnPossibilityConfirmed",
        "registrationDataCheckedAgainstSyntheticUrd",
        "recordedInEntirety",
        "recordingNoticeGiven",
    ):
        require(tpv[key] is True, f"TPV required evidence missing: {key}")
    require(tpv["verificationLanguage"] == tpv["underlyingMarketingTransaction"]["language"],
            "TPV language must match underlying transaction")
    require(tpv["verificationFormat"] == tpv["underlyingMarketingTransaction"]["format"],
            "TPV format must match underlying transaction")
    require(example_provider(tpv["newDefaultProvider"]), "TPV provider must use reserved example domain")
    require(tpv["telephoneNumber"].startswith("+1"), "TPV number must be NANP-shaped")
    require(tpv["realAuthorizationRecordingStored"] is False,
            "public fixture must not store real authorization recording")
    require(tpv["evidence"]["immutable"] is True, "verification evidence must be immutable")
    require(tpv["evidence"]["retentionYears"] >= 5, "verification retention is less than five years")
    require(tpv["evidence"]["syntheticDigest"].startswith("sha256:"), "synthetic evidence digest missing")

    cases = {item["scenario"]: item for item in cases_doc["cases"]}
    expected_scenarios = {
        "ITRS-CHANGE-LOA-001",
        "ITRS-CHANGE-VOID-060",
        "ITRS-CHANGE-MULTI-001",
        "ITRS-CHANGE-CONTINUITY-001",
        "ITRS-TRANSFER-001",
        "ITRS-DISPUTE-PREPAY-001",
        "ITRS-DISPUTE-PAID-001",
        "ITRS-FREEZE-001",
    }
    require(expected_scenarios == set(cases), "default-provider scenario set changed unexpectedly")

    # Authorization/verification do not themselves imply compensation.
    valid = cases["ITRS-CHANGE-LOA-001"]
    require(valid["authorizationObtained"] and valid["authorizationVerified"],
            "valid LOA arm lacks authorization/verification")
    require(valid["verificationRetentionYears"] >= 5 and valid["verificationImmutable"],
            "valid LOA arm lacks durable verification evidence")
    require(valid["implementedDay"] <= 60, "valid LOA arm implemented too late")
    require(valid["expected"]["orderValid"] is True and valid["expected"]["changeMayProceed"] is True,
            "valid LOA order cannot proceed")
    require(valid["expected"]["compensability"] == "not-determined",
            "authorized change must not imply compensability")

    # Day 61 is intentionally void under the modeled order.
    expired = cases["ITRS-CHANGE-VOID-060"]
    require(expired["authorizationObtained"] and expired["authorizationVerified"],
            "expiry control must otherwise be authorized/verified")
    require(expired["implementedDay"] > 60, "expiry control must exceed 60 days")
    require(expired["expected"]["orderValid"] is False,
            "order implemented after day 60 must be void in this model")
    require(expired["expected"]["routeChangeAuthorizedByThisOrder"] is False,
            "void order must not authorize route change")

    # Multi-service authorization is never transitive.
    multi = cases["ITRS-CHANGE-MULTI-001"]
    require(multi["services"]["VRS"]["authorized"] is True and multi["services"]["VRS"]["verified"] is True,
            "VRS control arm malformed")
    require(multi["services"]["VRS"]["changeMayProceed"] is True, "verified VRS arm blocked")
    require(multi["services"]["IP_RELAY"]["verified"] is False,
            "IP Relay negative control must remain unverified")
    require(multi["services"]["IP_RELAY"]["changeMayProceed"] is False,
            "unverified IP Relay arm must not proceed")
    require(multi["expected"]["crossServiceAuthorizationPromotion"] is False,
            "authorization leaked across TRS types")

    # Pending change must not degrade original-provider service or access technology.
    continuity = cases["ITRS-CHANGE-CONTINUITY-001"]
    require(continuity["changePending"] is True, "continuity arm must be pending")
    require(continuity["serviceQualityBefore"] == continuity["serviceQualityDuring"],
            "service quality degraded during provider change")
    require(continuity["vrsAccessTechnologyFunctionalityBefore"] ==
            continuity["vrsAccessTechnologyFunctionalityDuring"],
            "VRS access technology functionality degraded during provider change")
    require(continuity["expected"]["impermissibleDegradationObserved"] is False,
            "continuity result contradicts observations")

    # Provider-user-base transfer notice remains offline and structural.
    transfer = cases["ITRS-TRANSFER-001"]
    require(transfer["advanceNoticeDays"] >= 30, "provider transfer notice is less than 30 days")
    require(transfer["noticeFormat"] == "prerecorded-asl-video",
            "VRS transfer notice must be modeled as prerecorded ASL video")
    require(all(transfer["noticeContains"].values()), "provider transfer notice disclosure missing")
    require(transfer["realSubscriberNoticeSent"] is False, "public fixture sent/claims real subscriber notice")

    # Complaint creates hold/evidence state; final determination drives Fund consequence.
    prepay = cases["ITRS-DISPUTE-PREPAY-001"]
    require(prepay["allegedUnauthorizedChange"] is True and prepay["fundAlreadyReimbursed"] is False,
            "prepay dispute arm malformed")
    require(all(prepay["notifications"].values()), "prepay complaint notification evidence missing")
    require(prepay["affectedMinutesIdentified"] is True, "affected minutes not identified")
    require(prepay["reimbursementWithheldPendingDetermination"] is True,
            "prepay dispute must withhold reimbursement pending determination")
    require(prepay["proofOfVerificationSubmittedDay"] <= 30,
            "verification proof response exceeded 30 days")
    require(prepay["commissionDetermination"] == "unauthorized",
            "prepay negative arm needs final unauthorized determination")
    require(prepay["expected"]["newProviderReimbursementForAffectedMinutes"] is False and
            prepay["expected"]["originalProviderReimbursementForAffectedMinutes"] is False,
            "unauthorized prepay minutes must not be reimbursed to either provider")

    paid = cases["ITRS-DISPUTE-PAID-001"]
    require(paid["fundAlreadyReimbursed"] is True, "paid dispute arm must begin reimbursed")
    require(paid["commissionDetermination"] == "unauthorized",
            "paid negative arm needs final unauthorized determination")
    require(paid["clawbackPercent"] == 100, "unauthorized paid arm must model 100% clawback")
    require(paid["expected"]["syntheticRemittanceDue"] == paid["syntheticAffectedPayments"],
            "100% clawback amount mismatch")
    require(paid["expected"]["actualFundRemittance"] is False,
            "public fixture must not claim actual Fund remittance")

    freeze = cases["ITRS-FREEZE-001"]
    require(freeze["defaultProviderFreezeRequested"] is True, "freeze negative control missing")
    require(freeze["expected"]["permitted"] is False and freeze["expected"]["policyResult"] == "reject",
            "default-provider freeze was not rejected")

    print("Part 64 default-provider change contract: PASS")


if __name__ == "__main__":
    main()
