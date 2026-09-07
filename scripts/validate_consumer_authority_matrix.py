#!/usr/bin/env python3
"""Validate Baudot's cross-consumer authority non-interference matrix."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "interop" / "authority" / "consumer-authority-matrix-v1.json"


def require(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS {name}")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(facts: dict) -> dict[str, str]:
    machine = "NOT_DERIVED"
    if facts.get("machineConsentRevoked") is True:
        machine = "DENIED"
    elif facts.get("machineAccessAuthorized") is True:
        machine = "AUTHORIZED"

    return {
        "providerVisibility": "AUTHORIZED" if facts.get("providerAccessAuthorized") is True else "NOT_DERIVED",
        "machineVisibility": machine,
        "operatorAuthority": "NOT_DERIVED",
        "programCompensability": "AUTHORIZED" if facts.get("programEligible") is True else "NOT_DERIVED",
        "paymentAuthorization": "AUTHORIZED" if facts.get("paymentAuthorized") is True else "NOT_DERIVED",
        "accountingExecution": "OBSERVED" if facts.get("ledgerAccepted") is True else "NOT_DERIVED",
        "publicVisibility": "VISIBLE" if facts.get("publicProjectionPublished") is True else "NOT_DERIVED",
    }


def main() -> None:
    require("authority matrix exists", MATRIX.is_file())
    matrix = load_json(MATRIX)
    require("authority matrix schema is v1", matrix["schema"] == "baudot.consumer-authority-matrix@1")

    expected_source_ids = {"provider", "machine", "program-control", "public", "ledger"}
    sources = {source["id"]: source for source in matrix["sourceContracts"]}
    require("matrix pins all five source contracts", set(sources) == expected_source_ids)

    loaded_sources: dict[str, dict] = {}
    for source_id, source in sources.items():
        path = ROOT / source["path"]
        require(f"{source_id} source contract exists", path.is_file())
        doc = load_json(path)
        loaded_sources[source_id] = doc
        require(f"{source_id} source schema matches pin", doc.get("schema") == source["schema"])

    provider = loaded_sources["provider"]
    machine = loaded_sources["machine"]
    governance = loaded_sources["program-control"]
    public = loaded_sources["public"]
    ledger = loaded_sources["ledger"]

    provider_cannot = set(provider["accessDecision"]["cannotBeSatisfiedBy"])
    require("provider access cannot be created by payment authority", "paymentAuthorized" in provider_cannot)
    require("provider access cannot be created by ledger acceptance", "ledgerAccepted" in provider_cannot)
    require("provider access cannot be created by TRS business authority", "trsBusinessAuthorityAllowed" in provider_cannot)

    machine_cannot = set(machine["accessDecision"]["cannotBeSatisfiedBy"])
    require("machine access cannot be created by provider access", "providerAccessAuthorized" in machine_cannot)
    require("machine access cannot be created by operator authentication", "operatorAuthenticated" in machine_cannot)
    require("machine access cannot be created by payment authority", "paymentAuthorized" in machine_cannot)
    require("machine access cannot be created by ledger acceptance", "ledgerAccepted" in machine_cannot)
    require("machine token cannot substitute onto consumer surface", machine["tokenSeparation"]["openBankingBearerAcceptedOnConsumerSurface"] is False)
    require("provider session cannot substitute onto machine surface", machine["tokenSeparation"]["consumerSessionAcceptedOnMachineSurface"] is False)

    stages = {row["fact"]: row for row in governance["decisionStages"]}
    require("governance separates provider authority from ledger", "ledgerAccepted" in stages["providerAuthorized"]["cannotBeSatisfiedBy"])
    require("governance separates program eligibility from ledger", "ledgerAccepted" in stages["programEligible"]["cannotBeSatisfiedBy"])
    require("governance separates payment authorization from ledger", "ledgerAccepted" in stages["paymentAuthorized"]["cannotBeSatisfiedBy"])
    require("governance says accounting execution is not a program gate", stages["ledgerAccepted"]["gateForLedger"] is False)

    require("public publication is unauthenticated", public["publication"]["authenticationRequired"] is False)
    require("public publication is one-way", public["publication"]["direction"] == "one-way")
    require("public publication cannot mutate", public["publication"]["mutationAllowed"] is False)
    public_boundary = public["claimBoundary"]
    for field in (
        "providerLevelDataAllowed",
        "consumerAuthenticationDerived",
        "machineConsentDerived",
        "operatorAuthorityDerived",
        "claimAuthorityDerived",
        "paymentAuthorityDerived",
    ):
        require(f"public boundary keeps {field} false", public_boundary[field] is False)

    require(
        "Fineract journal explicitly rejects program implication",
        "fineract-ledger-success-does-not-imply-program-eligibility" in ledger["invariants"],
    )

    domains = matrix["domains"]
    expected_domains = {
        "providerVisibility",
        "machineVisibility",
        "operatorAuthority",
        "programCompensability",
        "paymentAuthorization",
        "accountingExecution",
        "publicVisibility",
    }
    require("matrix contains exactly the expected authority domains", set(domains) == expected_domains)
    require("operator authority has no positive fact in this stack", domains["operatorAuthority"]["positiveFact"] is None)

    cases = matrix["cases"]
    require("matrix includes at least eight non-interference cases", len(cases) >= 8)
    require("matrix case identifiers are unique", len({row["id"] for row in cases}) == len(cases))

    for row in cases:
        require(f'{row["id"]} declares every authority domain', set(row["expected"]) == expected_domains)
        observed = evaluate(row["facts"])
        require(f'{row["id"]} authority verdicts', observed == row["expected"])
        require(f'{row["id"]} never derives operator authority', row["expected"]["operatorAuthority"] == "NOT_DERIVED")

    by_id = {row["id"]: row for row in cases}
    revoke = by_id["AUTH-MATRIX-007"]
    require("revocation case preserves provider access", revoke["expected"]["providerVisibility"] == "AUTHORIZED")
    require("revocation case denies machine access", revoke["expected"]["machineVisibility"] == "DENIED")

    ledger_only = by_id["AUTH-MATRIX-005"]
    require("ledger-only case derives no payment authority", ledger_only["expected"]["paymentAuthorization"] == "NOT_DERIVED")
    require("ledger-only case derives no program authority", ledger_only["expected"]["programCompensability"] == "NOT_DERIVED")

    boundary = matrix["claimBoundary"]
    require("matrix does not claim operator authentication implementation", boundary["operatorAuthenticationImplemented"] is False)
    require("matrix does not claim production authorization policy", boundary["productionAuthorizationPolicyClaimed"] is False)
    require("matrix does not claim production Fund state", boundary["productionFundStateClaimed"] is False)
    require("matrix does not claim regulatory compliance", boundary["regulatoryComplianceClaimed"] is False)

    print("Consumer authority non-interference matrix: PASS")


if __name__ == "__main__":
    main()
