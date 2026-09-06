#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "testkit" / "business" / "nifi-tika-solr-handoff-v1.json"

UPSTREAM = {
    "sourceSystem",
    "sourceObjectId",
    "receivedAt",
    "contentSha256",
    "flowId",
    "correlationId",
}
SOURCE_IDENTITY = ["sourceSystem", "sourceObjectId", "contentSha256"]
FORBIDDEN_AUTHORITY = {
    "sourceAuthoritative",
    "subscriberEligible",
    "providerCertified",
    "itrsAuthorized",
    "compensable",
    "claimApproved",
    "paymentAuthorized",
    "fundPeriodClosed",
    "accessibilityReady",
}


def require(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS {name}")


def walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_keys(child)


def main() -> None:
    profile = json.loads(PROFILE.read_text())
    require("schema", profile["schema"] == "baudot.nifi-tika-solr-handoff@1")

    composition = profile["composition"]
    require("common base pin", composition["commonBase"] == "65723f8c6f566f092ebdd4a3901cf8743ca5a0bc")
    require("NiFi PR pin", composition["nifiPr"] == 121)
    require("NiFi head pin", composition["nifiHead"] == "bf6ffa25423c9107ef3b1ca546bc14f7574116bf")
    require("document PR pin", composition["documentPr"] == 129)
    require("document head pin", composition["documentHead"] == "9df3f208cc126d070060f495295c1babbedf6cb6")
    require("exact-head composition", composition["strategy"] == "ci-local-merge-of-exact-sibling-heads")

    pins = profile["runtimePins"]
    require("NiFi runtime pin", pins["nifi"] == "2.11.0")
    require("Tika runtime pin", pins["tika"] == "4.0.0")
    require("Solr runtime pin", pins["solr"] == "10.0.0")

    handoff = profile["handoff"]
    upstream = set(handoff["requiredUpstreamFields"])
    derived = set(handoff["derivedFieldsOnly"])
    require("exact upstream envelope", upstream == UPSTREAM)
    require("derived fields append-only", upstream.isdisjoint(derived))
    require("stable source evidence id is derived", "sourceEvidenceId" in derived)
    require("append-only marker", handoff["appendOnly"] is True)
    require("raw bytes immutable", handoff["rawBytesMustRemainIdentical"] is True)
    require("upstream envelope immutable", handoff["upstreamEnvelopeMustRemainByteIdentical"] is True)
    require("document flow id", handoff["flowId"] == "document-drop-ingest")
    require(
        "forbidden provenance renames",
        handoff["forbiddenRenames"] == {
            "sourceObjectId": "documentId",
            "contentSha256": "sourceSha256",
        },
    )

    replay = profile["replay"]
    require("source identity fields", replay["sourceIdentityFields"] == SOURCE_IDENTITY)
    require("index id source-derived", replay["indexIdDerivedOnlyFromSourceIdentity"] is True)
    require("exact replay idempotent", replay["exactEnvelopeReplayIsIdempotent"] is True)
    require("divergent observation rejected", replay["sameSourceDifferentEnvelopeRejectedFromSearch"] is True)
    require("no observation-ledger claim", replay["observationLedgerClaimed"] is False)

    for key, value in profile["authority"].items():
        require(f"authority boundary {key}", value is False)
    for key, value in profile["claimBoundary"].items():
        require(f"claim boundary {key}", value is False)

    all_keys = set(walk_keys(profile))
    require("no authority promotion fields", all_keys.isdisjoint(FORBIDDEN_AUTHORITY))
    print("Baudot NiFi -> Tika -> Solr handoff profile: PASS")


if __name__ == "__main__":
    main()
