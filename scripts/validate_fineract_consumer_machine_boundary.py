#!/usr/bin/env python3
"""Validate the synthetic Fineract Consumer machine-access boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "interop" / "fineract-consumer" / "machine-access-contract-v1.json"
FIXTURE = ROOT / "testkit" / "fund" / "fineract-consumer-machine-boundary-v1.json"


def require(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS {name}")


def machine_access(contract: dict, facts: dict) -> str:
    if facts.get("consumerSessionPresented") is True and facts.get("oauthPurposeIsOpenBanking") is not True:
        return "UNAUTHENTICATED"

    required = contract["accessDecision"]["requiredFacts"]
    return "AUTHORIZED" if all(facts.get(fact) is True for fact in required) else "DENIED"


def provider_access(facts: dict, expected: str) -> str:
    if facts.get("openBankingBearerPresentedToConsumerSurface") is True:
        return "UNAUTHENTICATED"
    if facts.get("providerSessionActive") is True:
        return "AUTHORIZED"
    return expected if expected in {"UNCHANGED", "NOT_APPLICABLE"} else "UNCHANGED"


def validate_upstream(contract: dict, upstream_root: Path) -> None:
    docs = upstream_root / "docs" / "consumer" / "features" / "openbanking.adoc"
    require("pinned upstream Open Banking documentation exists", docs.is_file())
    text = docs.read_text(encoding="utf-8")

    expected_fragments = [
        "/api/v1/openbanking/accounts",
        "/api/v1/openbanking/accounts/{accountId}/balances",
        "purpose=openbanking",
        "openbanking:accounts.read",
        "REVOKED",
        "revocation takes effect immediately",
        "read-only",
    ]
    for fragment in expected_fragments:
        require(f"upstream contract documents {fragment}", fragment in text)

    require(
        "contract pin matches checked-out upstream commit",
        contract["upstream"]["commit"] == _git_head(upstream_root),
    )


def _git_head(root: Path) -> str:
    head = root / ".git" / "HEAD"
    if not head.is_file():
        raise AssertionError("upstream checkout has no .git/HEAD")
    value = head.read_text(encoding="utf-8").strip()
    if value.startswith("ref: "):
        ref = root / ".git" / value.removeprefix("ref: ")
        return ref.read_text(encoding="utf-8").strip()
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-root", type=Path)
    args = parser.parse_args()

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    surface = contract["machineSurface"]
    require("machine surface is GET-only", surface["allowedMethods"] == ["GET"])
    require("machine surface has exactly two data endpoints", len(surface["allowedEndpoints"]) == 2)
    require("machine token purpose is openbanking", surface["tokenPurpose"] == "openbanking")
    require("machine token scope is accounts.read", surface["requiredScope"] == "openbanking:accounts.read")

    lifecycle = contract["consentLifecycle"]
    require("consent is rechecked on every read", lifecycle["consentRecheckedOnEveryRead"])
    require("consent expiry is checked at use", lifecycle["expiryCheckedAtUse"])
    require("revocation can cut access before token expiry", lifecycle["revocationTakesEffectBeforeTokenExpiry"])

    separation = contract["tokenSeparation"]
    require("consumer session is rejected on machine surface", not separation["consumerSessionAcceptedOnMachineSurface"])
    require("open banking bearer is rejected on consumer surface", not separation["openBankingBearerAcceptedOnConsumerSurface"])
    require("operator credential is rejected on machine surface", not separation["operatorCredentialAcceptedOnMachineSurface"])

    forbidden = set(contract["forbiddenCapabilities"])
    require("machine surface forbids money movement", "money-movement" in forbidden)
    require("machine surface forbids payment authority", "payment-authorization" in forbidden)
    require("machine surface forbids operator authority", "baudot-operator-authority" in forbidden)

    controls = fixture["controls"]
    require("machine fixture includes at least seven controls", len(controls) >= 7)

    by_id = {row["id"]: row for row in controls}
    require("machine control identifiers are unique", len(by_id) == len(controls))

    for row in controls:
        expected_machine = row["expectedMachineAccess"]
        if expected_machine != "NOT_APPLICABLE":
            observed_machine = machine_access(contract, row["facts"])
            require(f'{row["id"]} machine verdict', observed_machine == expected_machine)

        expected_provider = row["expectedProviderAccess"]
        observed_provider = provider_access(row["facts"], expected_provider)
        require(f'{row["id"]} provider verdict', observed_provider == expected_provider)
        require(
            f'{row["id"]} never derives TRS program authority',
            row["expectedTrsProgramAuthority"] == "NOT_DERIVED",
        )

    revoke = by_id["consent-revoked-provider-session-survives"]
    require("revocation control denies machine access", revoke["expectedMachineAccess"] == "DENIED")
    require("revocation control preserves provider access", revoke["expectedProviderAccess"] == "AUTHORIZED")

    require(
        "provider access cannot satisfy machine consent",
        "providerAccessAuthorized" in contract["accessDecision"]["cannotBeSatisfiedBy"],
    )
    require(
        "ledger acceptance cannot satisfy machine consent",
        "ledgerAccepted" in contract["accessDecision"]["cannotBeSatisfiedBy"],
    )

    if args.upstream_root is not None:
        validate_upstream(contract, args.upstream_root)

    print("Fineract Consumer machine consent boundary: PASS")


if __name__ == "__main__":
    main()
