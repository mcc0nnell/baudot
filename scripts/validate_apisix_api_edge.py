#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "testkit" / "business" / "apisix-api-edge-v1.json"

EXPECTED_ROUTES = {"itrs-edge", "equipment-edge", "fund-edge", "analytics-edge"}
FORBIDDEN = {
    "subscriberEligible",
    "providerCertified",
    "itrsProtocolValid",
    "compensable",
    "claimApproved",
    "paymentAuthorized",
    "accessibilityReady",
}


def require(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS {name}")


def main() -> None:
    profile = json.loads(PROFILE.read_text())

    require("schema", profile["schema"] == "baudot.apisix-api-edge@1")
    require("APISIX version", profile["apisix"]["version"] == "3.18.0")
    require(
        "APISIX release commit",
        profile["apisix"]["releaseCommit"] == "0796d9c2cbedb1f8bf8194292ff526599f4fde20",
    )

    routes = profile["routes"]
    ids = [route["id"] for route in routes]
    require("route IDs unique", len(ids) == len(set(ids)))
    require("expected route set", set(ids) == EXPECTED_ROUTES)

    for route in routes:
        require(f"{route['id']} TLS", route["tlsRequired"] is True)
        require(f"{route['id']} OIDC", route["authentication"] == "oidc")
        require(f"{route['id']} rate limit", route["rateLimit"] is True)
        require(f"{route['id']} wildcard path", route["path"].startswith("/") and route["path"].endswith("/*"))
        require(f"{route['id']} upstream", bool(route["upstream"]))

    protected = {route["id"] for route in routes if route["rangerDecisionRequiredDownstream"]}
    require("Ranger-protected business routes", protected == {"itrs-edge", "equipment-edge", "fund-edge"})

    logging = profile["logging"]
    for key in (
        "requestBodyLogging",
        "responseBodyLogging",
        "authorizationHeaderLogging",
        "tokenLogging",
        "telephoneNumberLogging",
        "subscriberIdLogging",
    ):
        require(f"logging boundary {key}", logging[key] is False)

    require(
        "opaque correlation logging only",
        set(logging["allowedCorrelationAttributes"]) == {"requestId", "correlationId", "routeId", "upstreamService"},
    )

    for key, value in profile["authority"].items():
        require(f"authority boundary {key}", value is False)

    require("forbidden gateway claims", set(profile["forbiddenGatewayClaims"]) == FORBIDDEN)
    require("gateway claim fields absent from routes", all(FORBIDDEN.isdisjoint(route.keys()) for route in routes))

    print("Baudot APISIX API-edge profile: PASS")


if __name__ == "__main__":
    main()
