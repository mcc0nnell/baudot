#!/usr/bin/env python3
"""Validate the synthetic Fineract Consumer provider-facing boundary."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "interop" / "fineract-consumer" / "provider-access-contract-v1.json"
SCENARIOS_PATH = ROOT / "testkit" / "fund" / "fineract-consumer-provider-boundary-v1.json"


def require(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS {name}")


def path_matches(template: str, path: str) -> bool:
    pattern = re.escape(template)
    pattern = re.sub(r"\\\{[^}]+\\\}", r"[^/]+", pattern)
    return re.fullmatch(pattern, path) is not None


def request_is_allowed(contract: dict, request: dict) -> bool:
    surface = contract["providerReadSurface"]
    if request["method"] not in surface["allowedMethods"]:
        return False
    return any(path_matches(template, request["path"]) for template in surface["allowedEndpoints"])


def access_verdict(contract: dict, scenario: dict) -> str:
    provider_user = scenario["actorType"] == "provider-user"
    provider_scope_matches = scenario["actorProviderId"] == scenario["resourceProviderId"]
    allowed = all(
        (
            provider_user,
            scenario["authenticated"],
            scenario["providerAccessActive"],
            provider_scope_matches,
            scenario["bffAbacAllowed"],
            request_is_allowed(contract, scenario["request"]),
        )
    )
    return "PROVIDER_ACCESS_AUTHORIZED" if allowed else "PROVIDER_ACCESS_DENIED"


def validate_upstream(contract: dict, upstream_root: Path) -> None:
    expected_commit = contract["upstream"]["commit"]
    observed_commit = subprocess.check_output(
        ["git", "-C", str(upstream_root), "rev-parse", "HEAD"], text=True
    ).strip()
    require("Consumer-Facing checkout matches the pinned commit", observed_commit == expected_commit)

    api_doc = (upstream_root / "docs" / "consumer" / "api.adoc").read_text()
    for endpoint in contract["providerReadSurface"]["allowedEndpoints"]:
        require(f"upstream documents provider read endpoint {endpoint}", endpoint in api_doc)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--upstream-root",
        type=Path,
        help="optional checkout of apache/fineract-consumer-facing used to verify the source pin and documented endpoints",
    )
    args = parser.parse_args()

    contract = json.loads(CONTRACT_PATH.read_text())
    scenarios = json.loads(SCENARIOS_PATH.read_text())["scenarios"]

    upstream = contract["upstream"]
    require("Consumer-Facing source pin is a full commit SHA", re.fullmatch(r"[0-9a-f]{40}", upstream["commit"]) is not None)
    require("Consumer-Facing BFF is the declared upstream component", upstream["component"] == "consumer BFF")

    surfaces = contract["surfaces"]
    surface_ids = [row["id"] for row in surfaces]
    actor_types = [row["actorType"] for row in surfaces]
    require("consumer surface identifiers are unique", len(surface_ids) == len(set(surface_ids)))
    require("consumer actor types are unique", len(actor_types) == len(set(actor_types)))
    require(
        "provider self-service belongs to the Consumer-Facing BFF",
        next(row for row in surfaces if row["id"] == "provider-self-service")["owner"] == "fineract-consumer-facing-bff",
    )
    require(
        "operator control plane remains Baudot-owned",
        next(row for row in surfaces if row["id"] == "operator-control-plane")["owner"] == "baudot",
    )
    require("no access surface declares TRS program authority", all(not row["mayConferTrsProgramAuthority"] for row in surfaces))

    provider_surface = contract["providerReadSurface"]
    require("first provider slice is GET-only", provider_surface["allowedMethods"] == ["GET"])
    require("provider summary endpoint is admitted", "/api/v1/summary/accounts" in provider_surface["allowedEndpoints"])
    require("provider savings endpoint is admitted", "/api/v1/savings" in provider_surface["allowedEndpoints"])
    require(
        "first provider slice explicitly forbids payment authority",
        "payment-authorization" in provider_surface["forbiddenCapabilities"],
    )
    require(
        "first provider slice explicitly forbids ledger mutation",
        "ledger-journal-mutation" in provider_surface["forbiddenCapabilities"],
    )
    require(
        "first provider slice explicitly forbids Consumer transfer mutation",
        "consumer-transfer-mutation" in provider_surface["forbiddenCapabilities"],
    )

    access = contract["accessDecision"]
    require("ledger acceptance cannot satisfy provider access", "ledgerAccepted" in access["cannotBeSatisfiedBy"])
    require("claim approval cannot satisfy provider access", "claimApproved" in access["cannotBeSatisfiedBy"])
    require("Ranger allow cannot satisfy provider access", "rangerAllowed" in access["cannotBeSatisfiedBy"])

    for scenario in scenarios:
        observed = access_verdict(contract, scenario)
        require(f'{scenario["id"]} preserves provider access verdict', observed == scenario["expectedAccessVerdict"])
        require(
            f'{scenario["id"]} preserves downstream read gating',
            scenario["expectedDownstreamFineractRead"] == (observed == "PROVIDER_ACCESS_AUTHORIZED"),
        )
        require(f'{scenario["id"]} derives no TRS authority', scenario["trsProgramAuthority"] == "NOT_DERIVED")

    require(
        "accepted ledger state cannot resurrect revoked provider access",
        any(
            row["ledgerAccepted"] is True
            and row["providerAccessActive"] is False
            and row["expectedAccessVerdict"] == "PROVIDER_ACCESS_DENIED"
            for row in scenarios
        ),
    )
    require(
        "cross-provider access fails before a downstream Fineract read",
        any(
            row["actorProviderId"] != row["resourceProviderId"]
            and row["expectedAccessVerdict"] == "PROVIDER_ACCESS_DENIED"
            and row["expectedDownstreamFineractRead"] is False
            for row in scenarios
        ),
    )
    require(
        "operators are routed to the Baudot control plane",
        any(
            row["actorType"] == "operator"
            and row.get("requiredSurface") == "baudot-operator-control-plane"
            and row["expectedAccessVerdict"] == "PROVIDER_ACCESS_DENIED"
            for row in scenarios
        ),
    )
    require(
        "write-shaped Consumer request is rejected by the first provider slice",
        any(
            row["request"]["method"] != "GET" and row["expectedAccessVerdict"] == "PROVIDER_ACCESS_DENIED"
            for row in scenarios
        ),
    )

    if args.upstream_root is not None:
        validate_upstream(contract, args.upstream_root.resolve())

    print("Fineract Consumer provider-facing boundary: PASS")


if __name__ == "__main__":
    main()
