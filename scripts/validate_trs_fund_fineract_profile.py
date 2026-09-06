#!/usr/bin/env python3
"""Validate the bounded live-Fineract profile without starting Fineract."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "interop" / "fineract" / "fineract-live-profile-v1.json"
CONTRACT = ROOT / "interop" / "fineract" / "journal-contract-v1.json"
EXPECTED_COMMIT = "d5636847ac556c30b437254c353f05526d172b97"
EXPECTED_TAG_OBJECT = "9e76f088db71a4458b68f7855b03b21d23b86f1c"
EXPECTED_REVERSAL = "/api/v1/journalentries/{transactionId}?command=reverse"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    require(profile.get("schema") == "baudot.fineract-live-profile@1", "unexpected live profile schema")
    require(profile.get("status") == "experimental", "live profile must remain experimental")
    require(profile["source"]["repository"] == "apache/fineract", "unexpected upstream repository")
    require(profile["source"]["releaseTag"] == "1.15.0", "unexpected release tag")
    require(profile["source"]["annotatedTagObject"] == EXPECTED_TAG_OBJECT, "annotated tag object drift")
    require(profile["source"]["commit"] == EXPECTED_COMMIT, "release commit drift")
    require(profile["source"]["annotatedTagVerified"] is True, "release tag verification not recorded")

    require(profile["baseUrl"].startswith("https://localhost:"), "profile must be loopback HTTPS")
    require(profile["tenant"] == "default", "unexpected test tenant")
    require(profile["officeId"] == 1, "unexpected test office")
    require(profile["currencyCode"] == "USD", "unexpected test currency")
    require(profile["imageBuild"]["method"] == "source-built-jib", "runtime must be source-built")
    require(profile["imageBuild"]["registryImageAuthority"] is False,
            "floating registry image cannot become runtime authority")

    require(contract.get("schema") == "baudot.fineract-trs-journal-contract@1",
            "unexpected canonical journal contract")
    require(len(contract["accounts"]) == profile["expected"]["canonicalAccountCount"] == 7,
            "canonical chart size drift")
    require(contract["fineractApiSurface"]["reversal"] == EXPECTED_REVERSAL,
            "canonical reversal API drift")
    require(profile["apiSurface"]["journalReversal"] == EXPECTED_REVERSAL,
            "profile reversal API drift")

    boundary = profile["claimBoundary"]
    require(boundary["testContainerOnly"] is True, "profile must remain test-container-only")
    require(boundary["productionDeploymentProfile"] is False, "profile cannot claim production deployment")
    require(boundary["productionCredentials"] is False, "profile cannot use production credentials")
    require(boundary["productionFundData"] is False, "profile cannot use production Fund data")
    require(boundary["programAuthorizationOwnedByFineract"] is False,
            "Fineract cannot become Fund program authority")
    require(boundary["fineractConformanceClaimed"] is False,
            "live slice cannot claim Fineract conformance")

    print("TRS Fund live Fineract profile: PASS")


if __name__ == "__main__":
    main()
