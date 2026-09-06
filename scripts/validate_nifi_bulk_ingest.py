#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "testkit" / "business" / "nifi-bulk-ingest-v1.json"

EXPECTED_FLOWS = {
    "provider-roster-import",
    "equipment-inventory-import",
    "fund-contribution-import",
    "cdr-backfill-import",
    "document-drop-ingest",
}

FORBIDDEN = {
    "subscriberEligible",
    "providerCertified",
    "itrsAuthorized",
    "compensable",
    "claimApproved",
    "paymentAuthorized",
    "fundPeriodClosed",
    "sourceAuthoritative",
    "accessibilityReady",
}


def require(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS {name}")


def walk_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_keys(item)


def main() -> None:
    profile = json.loads(PROFILE.read_text())

    require("schema", profile["schema"] == "baudot.nifi-bulk-ingest@1")
    nifi = profile["nifi"]
    require("NiFi version pin", nifi["version"] == "2.11.0")
    require(
        "NiFi release commit pin",
        nifi["releaseCommit"] == "e296b299805a7e3ff4c99916b79cfba16c5e4870",
    )
    require("Git-backed flow registry", nifi["registryStrategy"] == "git-flow-registry-client")
    require("deprecated NiFi Registry not required", nifi["nifiRegistryRequired"] is False)

    flows = profile["flows"]
    ids = [flow["id"] for flow in flows]
    require("flow IDs unique", len(ids) == len(set(ids)))
    require("expected flow set", set(ids) == EXPECTED_FLOWS)

    for flow in flows:
        require(f"{flow['id']} has source", bool(flow["source"]))
        require(f"{flow['id']} has target", bool(flow["target"]))
        require(f"{flow['id']} invalid data quarantined", flow["invalidAction"] == "quarantine")
        require(f"{flow['id']} valid mode", flow["mode"] in {"bulk", "backfill"})

    evidence = set(profile["requiredEvidence"])
    require(
        "provenance fields",
        {"sourceSystem", "sourceObjectId", "receivedAt", "contentSha256", "flowId", "correlationId"}.issubset(evidence),
    )

    require("forbidden promotion vocabulary", set(profile["forbiddenPromotions"]) == FORBIDDEN)

    authority = profile["authority"]
    for key, value in authority.items():
        require(f"authority boundary {key}", value is False)

    # No flow is allowed to smuggle business-authority fields into its contract.
    flow_keys = set()
    for flow in flows:
        flow_keys.update(walk_keys(flow))
    require("flows exclude authority fields", flow_keys.isdisjoint(FORBIDDEN))

    print("Baudot NiFi bulk-ingest profile: PASS")


if __name__ == "__main__":
    main()
