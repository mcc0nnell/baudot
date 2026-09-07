#!/usr/bin/env python3
"""Build and validate the public/oversight TRS Fund projection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "interop" / "publication" / "trs-fund-publication-contract-v1.json"
SOURCE_PATH = ROOT / "testkit" / "fund" / "rolka-loube-2025-26.json"
OUTPUT_PATH = ROOT / "site" / "public" / "data" / "trs-fund-public-2025-26.json"


def require(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS {name}")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def walk(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def validate_projection(contract: dict[str, Any], projection: dict[str, Any]) -> None:
    allowed = set(contract["allowedTopLevelFields"])
    require("public projection top-level fields are allowlisted", set(projection) <= allowed)

    forbidden_fields = set(contract["forbiddenFieldsAnywhere"])
    encountered = {key for key, _ in walk(projection)}
    require("public projection contains no forbidden field", forbidden_fields.isdisjoint(encountered))

    serialized = json.dumps(projection, sort_keys=True)
    for marker in contract["forbiddenValueMarkers"]:
        require(f"public projection excludes value marker {marker!r}", marker not in serialized)

    boundary = projection["claimBoundary"]
    require("projection declares public aggregates only", boundary["publicAggregatesOnly"] is True)
    require("projection is not an official FCC publication", boundary["officialFccPublication"] is False)
    require("projection contains no provider-level data", boundary["providerLevelData"] is False)
    require("projection derives no provider entitlement", boundary["providerEntitlementDerived"] is False)
    require("projection derives no machine consent", boundary["machineConsentDerived"] is False)
    require("projection derives no operator authority", boundary["operatorAuthorityDerived"] is False)
    require("projection derives no TRS program authority", boundary["trsProgramAuthorityDerived"] is False)
    require("projection derives no claim authority", boundary["claimAuthorityDerived"] is False)
    require("projection derives no payment authority", boundary["paymentAuthorityDerived"] is False)


def build_projection(contract: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    required_source = contract["source"]
    require("public source schema matches contract", source["schema"] == required_source["requiredSchema"])
    require(
        "source explicitly declares public aggregates only",
        source["claimBoundary"][required_source["requiredBoundaryFact"]]
        is required_source["requiredBoundaryValue"],
    )

    analog_net = source["publishedAnalog"]["netAnalogFundRequirement"]
    ip_net = source["publishedIpBased"]["netFundRequirement"]
    total_net = source["publishedFund"]["netFundRequirement"]
    require("analog plus IP net requirements equal published Fund net requirement", analog_net + ip_net == total_net)

    projection = {
        "schema": "baudot.trs-fund-public-projection@1",
        "programYear": source["programYear"],
        "sources": source["sources"],
        "fund": {
            "totalServiceRevenueRequirement": source["publishedFund"]["totalServiceRevenueRequirement"],
            "ndbedp": source["publishedFund"]["ndbedp"],
            "administrativeCosts": source["publishedFund"]["administrativeCosts"],
            "grossFundRequirement": source["publishedFund"]["grossFundRequirement"],
            "lessProjectedFundBalance": source["publishedFund"]["lessProjectedFundBalance"],
            "netFundRequirement": total_net,
        },
        "serviceRequirements": {
            "analogNetFundRequirement": analog_net,
            "ipBasedNetFundRequirement": ip_net,
        },
        "contribution": {
            "analog": {
                "netRequirement": source["contribution"]["analog"]["netRequirement"],
                "revenueBase": source["contribution"]["analog"]["revenueBase"],
                "reportedFactor": source["contribution"]["analog"]["reportedFactor"],
            },
            "ipBased": {
                "netRequirement": source["contribution"]["ipBased"]["netRequirement"],
                "revenueBase": source["contribution"]["ipBased"]["revenueBase"],
                "reportedFactor": source["contribution"]["ipBased"]["reportedFactor"],
            },
        },
        "rates": source["rates"]["2025-07-01/2026-06-30"],
        "claimBoundary": {
            "publicAggregatesOnly": True,
            "officialFccPublication": False,
            "productionFundStateClaimed": False,
            "providerLevelData": False,
            "providerEntitlementDerived": False,
            "consumerAuthenticationDerived": False,
            "machineConsentDerived": False,
            "operatorAuthorityDerived": False,
            "trsProgramAuthorityDerived": False,
            "claimAuthorityDerived": False,
            "paymentAuthorityDerived": False,
            "regulatoryComplianceClaimed": False,
        },
    }
    validate_projection(contract, projection)
    return projection


def render(projection: dict[str, Any]) -> str:
    return json.dumps(projection, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write the checked-in public projection")
    args = parser.parse_args()

    contract = load(CONTRACT_PATH)
    source = load(SOURCE_PATH)
    projection = build_projection(contract, source)
    expected = render(projection)

    if args.write:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(expected, encoding="utf-8")
        print(f"WROTE {OUTPUT_PATH.relative_to(ROOT)}")
    else:
        require("checked-in public projection exists", OUTPUT_PATH.is_file())
        require("checked-in public projection is deterministic", OUTPUT_PATH.read_text(encoding="utf-8") == expected)

    print("TRS Fund public publication boundary: PASS")


if __name__ == "__main__":
    main()
