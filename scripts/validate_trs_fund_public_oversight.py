#!/usr/bin/env python3
"""Validate that the public Fund oversight page consumes only the public projection."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "site" / "src" / "components" / "PublicFundOversight.astro"
PAGE = ROOT / "site" / "src" / "pages" / "public-fund.astro"
CONFIG = ROOT / "site" / "astro.config.mjs"
PACKAGE = ROOT / "site" / "package.json"
PROJECTION = ROOT / "site" / "public" / "data" / "trs-fund-public-2025-26.json"


def require(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS {name}")


def main() -> None:
    require("public oversight component exists", COMPONENT.is_file())
    require("public oversight page exists", PAGE.is_file())
    require("public projection exists", PROJECTION.is_file())

    component = COMPONENT.read_text(encoding="utf-8")
    page = PAGE.read_text(encoding="utf-8")
    config = CONFIG.read_text(encoding="utf-8")
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    projection = json.loads(PROJECTION.read_text(encoding="utf-8"))

    require("oversight page uses StarlightPage", "@astrojs/starlight/components/StarlightPage.astro" in page)
    require("oversight page renders the public component", "<PublicFundOversight" in page)
    require("oversight page is present in Starlight navigation", "Public TRS Fund overview" in config and "/public-fund/" in config)
    require(
        "component imports the checked-in public projection directly",
        "../../public/data/trs-fund-public-2025-26.json" in component,
    )

    json_references = [line for line in component.splitlines() if ".json" in line]
    require("component references exactly one JSON data source", len(json_references) == 1)

    forbidden_markers = [
        "fetch(",
        "xmlhttprequest",
        "websocket",
        "eventsource",
        "/api/v1",
        "authorization:",
        "cookie:",
        "access_token",
        "refresh_token",
        "x-device-fingerprint",
        "/openbanking/",
        "/savings",
    ]
    lowered = component.lower()
    for marker in forbidden_markers:
        require(f"component excludes runtime/private marker {marker!r}", marker not in lowered)

    require("site pins Apache ECharts 6.1.0", package["dependencies"].get("echarts") == "6.1.0")
    require("chart uses tree-shakeable ECharts core", "from 'echarts/core'" in component)
    require("chart uses SVG renderer", "SVGRenderer" in component and "renderer: 'svg'" in component)
    require("chart enables ECharts ARIA", "AriaComponent" in component and "aria:" in component)
    require("page carries a non-chart textual equivalent", "Fund requirement bridge" in component and "<table>" in component)

    boundary = projection["claimBoundary"]
    require("projection remains public aggregates only", boundary["publicAggregatesOnly"] is True)
    require("projection remains non-official", boundary["officialFccPublication"] is False)
    require("projection carries no provider-level data", boundary["providerLevelData"] is False)
    require("projection derives no machine consent", boundary["machineConsentDerived"] is False)
    require("projection derives no operator authority", boundary["operatorAuthorityDerived"] is False)
    require("projection derives no TRS authority", boundary["trsProgramAuthorityDerived"] is False)
    require("projection derives no claim authority", boundary["claimAuthorityDerived"] is False)
    require("projection derives no payment authority", boundary["paymentAuthorityDerived"] is False)

    print("TRS Fund public oversight surface: PASS")


if __name__ == "__main__":
    main()
