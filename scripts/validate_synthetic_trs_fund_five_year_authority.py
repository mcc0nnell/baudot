#!/usr/bin/env python3
"""Guard the five-year benchmark's authority boundary against canonical Fund fixtures."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "testkit" / "fund" / "synthetic-trs-fund-five-year-v1.json"
CALIBRATION = ROOT / "testkit" / "fund" / "rolka-loube-2025-26.json"
CONTRIBUTORS = ROOT / "testkit" / "fund" / "contributor-assessments-2026-27.json"
RUNTIME = ROOT / "testkit" / "fund" / "trs-fund-runtime-contract-v1.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def d(value: object) -> Decimal:
    return Decimal(str(value))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def year(corpus: dict, year_id: str) -> dict:
    return next(item for item in corpus["programYears"] if item["id"] == year_id)


def require_rate(actual: object, expected: object, label: str) -> None:
    require(d(actual) == d(expected), f"{label} drift: {actual} != {expected}")


def main() -> int:
    corpus = load(CORPUS)
    calibration = load(CALIBRATION)
    contributors = load(CONTRIBUTORS)
    runtime = load(RUNTIME)

    require(corpus.get("schema") == "baudot.synthetic-trs-fund-five-year@1", "unexpected benchmark schema")
    require(calibration.get("schema") == "baudot.trs-fund-public-calibration@1", "unexpected public calibration schema")
    require(contributors.get("schema") == "baudot.trs-fund-contributor-assessment@1", "unexpected contributor schema")
    require(runtime.get("schema") == "baudot.trs-fund-runtime-contract@1", "unexpected runtime contract schema")

    boundary = corpus["authorityBoundary"]
    require(boundary.get("publicParametersAreSourceFacts") is True, "public parameters must remain source facts")
    require(boundary.get("providerVolumesAreSynthetic") is True, "provider volumes must remain synthetic")
    require(boundary.get("contributorRevenueBasesAreSynthetic") is True, "contributor revenue bases must remain synthetic")
    require(boundary.get("administratorPrivateImplementationModeled") is False, "private administrator implementation leaked into benchmark")
    require(boundary.get("productionAccountingModeled") is False, "benchmark cannot claim production accounting")
    require(boundary.get("productionPaymentRailModeled") is False, "benchmark cannot claim production payment rail")
    require("accounts" not in corpus, "five-year benchmark must not define a chart of accounts")

    source_urls = {source["url"] for source in corpus.get("publicParameterSources", [])}
    require("https://rolkaloube.com/programs/federal-itrs/trs-providers" in source_urls,
            "provider-rate public source missing")
    require("https://rolkaloube.com/programs/federal-itrs/trs-contributors" in source_urls,
            "contributor-factor public source missing")

    y2526 = year(corpus, "FY2025-26")
    canonical_2526 = calibration["rates"]["2025-07-01/2026-06-30"]
    require_rate(y2526["rates"]["vrsEmergent"], canonical_2526["VRS_EMERGENT"], "2025-26 VRS emergent")
    require_rate(y2526["rates"]["ipctsCa"], canonical_2526["IP_CTS_CA_BASE"], "2025-26 IP CTS CA")
    require_rate(y2526["rates"]["ipctsAsr"], canonical_2526["IP_CTS_ASR"], "2025-26 IP CTS ASR")
    require_rate(y2526["rates"]["ipRelay"], canonical_2526["IP_RELAY"], "2025-26 IP Relay")

    y2627 = year(corpus, "FY2026-27")
    canonical_2627 = calibration["rates"]["2026-07-01/2027-06-30"]
    require_rate(y2627["rates"]["ipctsCa"], canonical_2627["IP_CTS_CA_BASE"], "2026-27 IP CTS CA")
    require_rate(y2627["rates"]["ipctsAsr"], canonical_2627["IP_CTS_ASR"], "2026-27 IP CTS ASR")
    require_rate(y2627["rates"]["ipRelay"], canonical_2627["IP_RELAY"], "2026-27 IP Relay")

    factor = y2627["contributionFormula"]
    canonical_factors = contributors["approvedFactors"]
    require(factor.get("kind") == "form499-line-split", "2026-27 factor kind drift")
    require(factor.get("nonInternetLine") == canonical_factors["nonInternetBased"]["form499ALine"],
            "2026-27 non-internet Form 499 line drift")
    require(factor.get("internetLine") == canonical_factors["internetBased"]["form499ALine"],
            "2026-27 internet Form 499 line drift")
    require_rate(factor["nonInternetFactor"], canonical_factors["nonInternetBased"]["factor"],
                 "2026-27 non-internet factor")
    require_rate(factor["internetFactor"], canonical_factors["internetBased"]["factor"],
                 "2026-27 internet factor")

    require(runtime["dependsOn"].get("publicCalibration") == calibration["schema"],
            "runtime no longer points to canonical public calibration")
    require("accounts" not in runtime and "rateProfiles" not in runtime,
            "runtime layer reintroduced policy/account authority")

    require(all(provider.get("synthetic") is True for provider in corpus["providers"]),
            "all benchmark providers must be explicit synthetic actors")
    require(all(str(contributor["id"]).startswith("carrier-") for contributor in corpus["contributors"]),
            "benchmark contributor fixture identity drift")

    print("five-year public-parameter overlap with canonical Fund fixtures: PASS")
    print("five-year benchmark owns synthetic scenario pressure, not policy/account authority: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
