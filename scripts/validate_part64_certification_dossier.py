#!/usr/bin/env python3
"""Validate synthetic 47 CFR § 64.606 certification evidence contracts."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQ = ROOT / "testkit/part64/certification-requirements-v1.json"
DOSSIER = ROOT / "testkit/part64/fixtures/internet-trs-certification-dossier.json"
ANNUAL = ROOT / "testkit/part64/fixtures/vrs-annual-compliance.json"


def load(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    requirements = load(REQ)
    dossier = load(DOSSIER)
    annual = load(ANNUAL)

    require(requirements["safety"], "safety declarations missing")
    require(all(value is False for value in requirements["safety"].values()),
            "public certification corpus enables real/private certification data")

    req_ids = {item["id"] for item in requirements["requirements"]}
    require(req_ids == {
        "PART64-606-A2-SERVICES",
        "PART64-606-A2-STANDARDS",
        "PART64-606-A2-VRS-FACILITIES",
        "PART64-606-A2-ORG",
        "PART64-606-A2-COMPLAINTS",
        "PART64-606-A2-ANNUAL-COMMIT",
        "PART64-606-A2-EXEC-CERT",
        "PART64-606-A3-ONSITE",
        "PART64-606-A4-ATHOME",
        "PART64-606-B2-EXTERNAL-CERT",
        "PART64-606-C2-RENEWAL",
        "PART64-606-F2-CHANGE",
        "PART64-606-G-ANNUAL",
        "PART64-606-G3-PLAN",
        "PART64-606-G4-CURE",
    }, "unexpected certification requirement set")

    require(dossier["scenario"] == "ITRS-CERT-DOSSIER-001", "dossier scenario mismatch")
    require(dossier["caption"] == "Internet-based TRS Certification Application",
            "certification application caption mismatch")
    require(dossier["services"] == ["VRS"], "current certification fixture must be VRS-only")

    standards = dossier["mandatoryMinimumStandardsEvidence"]
    require(standards["allApplicableNonWaivedStandardsMapped"] is True,
            "mandatory-minimum-standard map incomplete")
    expected_docs = {
        "docs/part64-registration-numbering-validation.md",
        "docs/part64-default-provider-change.md",
        "docs/part64-vrs-call-evidence.md",
        "docs/part64-vrs-compensability.md",
        "docs/part64-vrs-monthly-capacity.md",
    }
    require(expected_docs <= set(standards["evidenceIndex"]), "upstream Part 64 evidence map missing")
    require(standards["actualComplianceEstablished"] is False,
            "synthetic evidence map claims actual provider compliance")

    facilities = dossier["vrsFacilities"]
    require(facilities["usCallCenters"] == 2 and facilities["foreignCallCenters"] == 0,
            "synthetic facility count changed unexpectedly")
    require(facilities["deedOrLeaseEvidencePresentForEachApplicableCenter"] is True,
            "facility deed/lease evidence state missing")
    require(facilities["callCenterEmployeesCommunicationsAssistants"] is True,
            "VRS call centers lack modeled CA employees")
    require(facilities["technologyDescriptionPresent"] is True,
            "call-center technology description missing")
    required_core = {"automatic-call-distribution", "routing", "call-setup", "mapping", "call-features", "billing", "registration"}
    require(required_core <= set(facilities["coreFunctionsCovered"]), "call-center core-function evidence incomplete")
    require(facilities["technologyOwnership"] == "owned" and facilities["proofOfPurchaseEvidencePresent"] is True,
            "owned technology lacks proof-of-purchase evidence state")
    require(facilities["acdLeaseOrLicenseUsed"] is False,
            "fixture unexpectedly requires an ACD lease/license document")

    org = dossier["organization"]
    require(org["tenPercentOwnershipOrControlListProvided"] is True,
            "10-percent ownership/control list evidence missing")
    require(org["organizationalStructureProvided"] is True and org["executiveOfficerBoardRoleListProvided"] is True,
            "organization/governance evidence incomplete")
    require(org["realNamesStored"] is False, "public fixture stores real ownership/governance names")

    employees = dossier["trsEmployees"]
    require(employees["countsProvidedByRole"] is True, "TRS employee counts by role missing")
    require(all(value >= 0 for value in employees["roles"].values()), "negative TRS employee count")
    require(employees["realEmployeeNamesStored"] is False, "public fixture stores real employee names")
    require(employees["employmentAgreementsRetainedYears"] >= 5,
            "employment-agreement retention is less than five years")
    require(employees["employmentAgreementsStoredInPublicFixture"] is False,
            "public fixture stores employment agreements")

    sponsorships = dossier["sponsorships"]
    require(sponsorships["listProvided"] is True, "sponsorship list evidence missing")
    require(sponsorships["agreementsRetentionYearsWhenApplicable"] >= 3,
            "sponsorship agreement retention is less than three years")
    require(dossier["complaintProceduresDescriptionPresent"] is True,
            "complaint procedure description missing")
    require(dossier["annualComplianceReportCommitment"] is True,
            "annual compliance report commitment missing")

    cert = dossier["executiveCertification"]
    require(cert["role"] in {"ceo", "cfo", "other-senior-executive"}, "invalid certification signer role")
    require(cert["firstHandKnowledge"] and cert["underPenaltyOfPerjury"],
            "application executive certification incomplete")
    require(cert["allRequiredInformationProvided"] and cert["factsAndDocumentationTrueAccurateCompleteAsserted"],
            "application certification assertions incomplete")
    require(cert["realIdentityStored"] is False, "public fixture stores real certifier identity")
    require(dossier["consentsToCommissionOnSiteVisits"] is True, "on-site visit consent missing")
    require(dossier["requestsAtHomeVrsAtInitialCertification"] is True and dossier["atHomeCompliancePlanPresent"] is True,
            "initial at-home VRS request lacks detailed compliance plan state")

    # Complete evidence dossier never self-promotes into FCC certification.
    require(dossier["commissionDecision"] == "not-determined",
            "synthetic dossier contains a fabricated Commission certification decision")
    require(dossier["claimsActualFccCertification"] is False,
            "synthetic dossier claims actual FCC certification")

    report = annual["annualReport"]
    require(report["scenario"] == "VRS-ANNUAL-REPORT-001", "annual report scenario mismatch")
    require(report["updatesCertificationInformation"] is True,
            "annual report does not update certification information")
    require(report["updatedDocumentationOrNoChangeCertificationPresent"] is True,
            "annual update/no-change certification missing")
    require(report["summaryOfUpdatesPresent"] is True, "annual update summary missing")
    annual_cert = report["executiveCertification"]
    require(annual_cert["role"] in {"ceo", "cfo", "other-senior-executive"},
            "annual report certifier role invalid")
    require(annual_cert["firstHandKnowledge"] and annual_cert["underPenaltyOfPerjury"] and
            annual_cert["factsAndDocumentationTrueAccurateCompleteAsserted"],
            "annual report executive certification incomplete")
    require(annual_cert["realIdentityStored"] is False, "annual report stores real certifier identity")

    plan = report["compliancePlan"]
    for key in (
        "filed", "responsibleOfficerOrManagerIdentified", "complianceTrainingDescribed",
        "employeeAbuseReportingMechanismsIdentified", "internalAuditProcessesDescribed",
        "wasteFraudAbusePreventionPoliciesDescribed",
    ):
        require(plan[key] is True, f"annual VRS compliance plan missing: {key}")
    require(plan["commissionAdequacyDetermination"] == "not-determined",
            "submitted plan claims Commission adequacy finding")

    home = report["atHomeAnnualInformation"]
    require(home["authorized"] is True, "at-home annual information lacks authorization state")
    require(home["totalHomeCas"] >= 0 and home["homeWorkstation911Calls"] >= 0 and home["atHomeComplaints"] >= 0,
            "negative at-home annual report count")
    require(home["substantivePlanChangesDescriptionPresent"] is True,
            "at-home substantive plan-change description missing")
    require(report["productionAnnualReport"] is False, "public fixture claims production annual filing")

    cases = {item["scenario"]: item for item in annual["timelineCases"]}
    require(set(cases) == {
        "ITRS-CERT-RENEW-090-PASS",
        "ITRS-CERT-RENEW-089-FAIL",
        "VRS-SUBSTANTIVE-CHANGE-060-PASS",
        "VRS-SUBSTANTIVE-CHANGE-061-FAIL",
        "VRS-COMPLIANCE-PLAN-MISSING-001",
        "VRS-COMPLIANCE-CURE-060-PASS",
        "VRS-COMPLIANCE-CURE-061-FAIL",
    }, "unexpected certification timeline scenario set")

    renew_pass = cases["ITRS-CERT-RENEW-090-PASS"]
    renew_fail = cases["ITRS-CERT-RENEW-089-FAIL"]
    require(renew_pass["certificationTermYears"] == 5 and renew_fail["certificationTermYears"] == 5,
            "certification term must be five years")
    require(renew_pass["renewalFiledDaysBeforeExpiration"] >= 90 and renew_pass["expected"]["timely"] is True,
            "90-day renewal boundary should pass")
    require(renew_fail["renewalFiledDaysBeforeExpiration"] < 90 and renew_fail["expected"]["timely"] is False,
            "89-day renewal boundary should fail")

    change_pass = cases["VRS-SUBSTANTIVE-CHANGE-060-PASS"]
    change_fail = cases["VRS-SUBSTANTIVE-CHANGE-061-FAIL"]
    require(change_pass["notificationDaysAfterChange"] <= 60 and
            change_pass["continuedMinimumStandardsCertificationPresent"] and change_pass["expected"]["timely"],
            "60-day substantive-change boundary should pass")
    require(change_fail["notificationDaysAfterChange"] > 60 and change_fail["expected"]["timely"] is False,
            "61-day substantive-change boundary should fail")

    missing = cases["VRS-COMPLIANCE-PLAN-MISSING-001"]
    require(missing["annualReportFiled"] is True and missing["compliancePlanFiled"] is False,
            "missing-plan negative arm malformed")
    require(missing["expected"]["entitledToCompensationDuringNoncompliance"] is False,
            "missing VRS compliance plan did not remove compensation entitlement")

    cure_pass = cases["VRS-COMPLIANCE-CURE-060-PASS"]
    cure_fail = cases["VRS-COMPLIANCE-CURE-061-FAIL"]
    for item in (cure_pass, cure_fail):
        require(item["commissionFoundPlanInadequate"] is True,
                "compliance-plan cure arm lacks Commission inadequacy input")
        require(item["directedCorrectionPeriodDays"] <= 60,
                "modeled Commission correction period exceeds 60 days")
    require(cure_pass["amendedPlanSubmittedDay"] <= cure_pass["directedCorrectionPeriodDays"] and
            cure_pass["expected"]["curedWithinDirectedPeriod"] is True,
            "day-60 compliance-plan correction should pass")
    require(cure_fail["amendedPlanSubmittedDay"] > cure_fail["directedCorrectionPeriodDays"] and
            cure_fail["expected"]["curedWithinDirectedPeriod"] is False and
            cure_fail["expected"]["entitledToCompensationDuringNoncompliance"] is False,
            "late compliance-plan correction did not preserve noncompliance consequence")

    print("Part 64 Internet-based TRS certification dossier: PASS")


if __name__ == "__main__":
    main()
