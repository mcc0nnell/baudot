#!/usr/bin/env python3
"""Validate the synthetic TRS Fund governance boundary without requiring Fineract."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "testkit" / "fund" / "governance-boundaries-v1.json"


def require(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS {name}")


def authorization_verdict(contract: dict, facts: dict) -> str:
    gate_facts = [stage["fact"] for stage in contract["decisionStages"] if stage["gateForLedger"]]
    return "AUTHORIZED_FOR_LEDGER" if all(facts.get(fact) is True for fact in gate_facts) else "NOT_AUTHORIZED_FOR_LEDGER"


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    stages = contract["decisionStages"]
    controls = contract["negativeControls"]

    ids = [stage["id"] for stage in stages]
    facts = [stage["fact"] for stage in stages]
    require("governance stage identifiers are unique", len(ids) == len(set(ids)))
    require("governance decision facts are unique", len(facts) == len(set(facts)))

    stage_by_fact = {stage["fact"]: stage for stage in stages}
    program_gates = [stage for stage in stages if stage["gateForLedger"]]
    require("at least five independent gates precede ledger execution", len(program_gates) >= 5)
    require("accounting execution is not a program authorization gate", not stage_by_fact["ledgerAccepted"]["gateForLedger"])
    require("reconciliation is independent from ledger acceptance", not stage_by_fact["reconciled"]["gateForLedger"])
    require(
        "Fineract does not own a pre-ledger program decision",
        all("fineract" not in stage["owner"] for stage in program_gates),
    )
    require(
        "every program gate rejects ledger acceptance as substitute authority",
        all("ledgerAccepted" in stage["cannotBeSatisfiedBy"] for stage in program_gates),
    )
    require(
        "every decision stage declares evidence",
        all(stage["requiredEvidence"] for stage in stages),
    )

    for control in controls:
        observed = authorization_verdict(contract, control["facts"])
        require(
            f'{control["id"]} preserves authorization verdict',
            observed == control["expectedAuthorizationVerdict"],
        )

    require(
        "balanced accepted journal negative control remains unauthorized",
        any(
            row["facts"].get("journalBalanced") is True
            and row["facts"].get("ledgerAccepted") is True
            and row["expectedAuthorizationVerdict"] == "NOT_AUTHORIZED_FOR_LEDGER"
            for row in controls
        ),
    )
    require(
        "ledger rejection cannot erase prior business authority",
        any(
            row["facts"].get("ledgerAccepted") is False
            and row["expectedAuthorizationVerdict"] == "AUTHORIZED_FOR_LEDGER"
            for row in controls
        ),
    )

    history = contract["historyPolicy"]
    require("original source events remain immutable", history["originalEventsImmutable"])
    require("corrections are new events", history["correctionsAreNewEvents"])
    require("reversals preserve original ledger identifiers", history["reversalsPreserveOriginalLedgerIds"])
    require("policy version is bound at decision time", history["policyVersionBoundAtDecisionTime"])

    boundary = contract["publicSourceBoundary"]
    require("public build declares allowed source classes", len(boundary["allowed"]) >= 3)
    require("public build declares excluded source classes", len(boundary["excluded"]) >= 5)

    print("Synthetic TRS Fund governance boundary: PASS")


if __name__ == "__main__":
    main()
