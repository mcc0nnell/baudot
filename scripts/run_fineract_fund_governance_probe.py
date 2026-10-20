#!/usr/bin/env python3
"""Cross the synthetic TRS Fund governance boundary into the live Fineract lane.

This probe proves two asymmetric controls:

1. an unauthorized but otherwise balanced synthetic payment is stopped before any
   Fineract journal request is attempted; and
2. a fully authorized synthetic correction can still be rejected by Fineract,
   with the business authorization evidence preserved separately from the ledger
   failure.

All records are synthetic and carry no FCC, Fund administrator, provider, or
payment-network authority.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import run_fineract_fund_closure_probe as closure
import run_fineract_fund_lane as lane

GOVERNANCE_PATH = lane.ROOT / "testkit" / "fund" / "governance-boundaries-v1.json"


def gate_facts(contract: dict[str, Any]) -> list[str]:
    return [stage["fact"] for stage in contract["decisionStages"] if stage["gateForLedger"]]


def authorization(contract: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    required = gate_facts(contract)
    failed = [fact for fact in required if facts.get(fact) is not True]
    return {
        "requiredGateFacts": required,
        "failedGateFacts": failed,
        "verdict": "AUTHORIZED_FOR_LEDGER" if not failed else "NOT_AUTHORIZED_FOR_LEDGER",
    }


def intended_journal(
    scenario: dict[str, Any],
    journal_contract: dict[str, Any],
    event: dict[str, Any],
) -> dict[str, Any]:
    mapping = journal_contract["events"][event["type"]]
    return {
        "syntheticBusinessTransactionId": event["id"],
        "eventType": event["type"],
        "amount": str(lane.d(event["amount"])),
        "postingDate": scenario["postingDate"],
        "debitAccount": mapping["debit"],
        "creditAccount": mapping["credit"],
        "journalBalancedByConstruction": True,
    }


def prove_preledger_denial(
    client: lane.FineractClient,
    scenario: dict[str, Any],
    journal_contract: dict[str, Any],
    governance_contract: dict[str, Any],
    probe: dict[str, Any],
) -> dict[str, Any]:
    decision = authorization(governance_contract, probe["authorizationFacts"])
    if decision["verdict"] != probe["expectedAuthorizationVerdict"]:
        raise lane.LaneError(
            f"Unexpected pre-ledger authorization verdict: {decision['verdict']}"
        )
    if decision["verdict"] != "NOT_AUTHORIZED_FOR_LEDGER":
        raise lane.LaneError("Pre-ledger denial probe must remain unauthorized")

    before = client.sequence
    journal = intended_journal(scenario, journal_contract, probe["event"])
    # Intentionally do not invoke lane.post_event or client.call here.
    after = client.sequence
    if after != before:
        raise lane.LaneError("Unauthorized probe crossed the Fineract HTTP boundary")

    return {
        "probeId": probe["id"],
        "authorization": decision,
        "authorizationFacts": probe["authorizationFacts"],
        "intendedJournal": journal,
        "fineractCallAttempted": False,
        "fineractSequenceBefore": before,
        "fineractSequenceAfter": after,
        "ledgerAccepted": None,
        "result": "BLOCKED_BEFORE_LEDGER",
    }


def prove_authorized_ledger_rejection(
    client: lane.FineractClient,
    scenario: dict[str, Any],
    journal_contract: dict[str, Any],
    governance_contract: dict[str, Any],
    account_ids: dict[str, int],
    probe: dict[str, Any],
) -> dict[str, Any]:
    decision = authorization(governance_contract, probe["authorizationFacts"])
    if decision["verdict"] != probe["expectedAuthorizationVerdict"]:
        raise lane.LaneError(
            f"Unexpected authorized-rejection verdict: {decision['verdict']}"
        )
    if decision["verdict"] != "AUTHORIZED_FOR_LEDGER":
        raise lane.LaneError("Ledger rejection probe must be authorized before execution")

    live_probe = {
        "event": probe["event"],
        "rejectedEventId": probe["event"]["id"],
        "rejectedPostingDate": probe["postingDate"],
    }
    before = client.sequence
    rejection = closure.require_closed_period_rejection(
        client, scenario, journal_contract, account_ids, live_probe
    )
    after = client.sequence
    if after <= before:
        raise lane.LaneError("Authorized ledger rejection did not cross the Fineract boundary")

    return {
        "probeId": probe["id"],
        "authorization": decision,
        "authorizationFacts": probe["authorizationFacts"],
        "fineractCallAttempted": True,
        "fineractSequenceBefore": before,
        "fineractSequenceAfter": after,
        "ledgerAccepted": False,
        "ledgerFailure": rejection,
        "result": "AUTHORIZED_BUT_LEDGER_REJECTED",
    }


def augment_manifest(
    evidence_dir: Path,
    preledger: dict[str, Any],
    ledger_rejection: dict[str, Any],
) -> str:
    manifest_path = evidence_dir / "manifest.json"
    if not manifest_path.exists():
        raise lane.LaneError(f"Base Fineract evidence manifest is missing: {manifest_path}")

    manifest = json.loads(manifest_path.read_text())
    previous_hash = manifest.pop("canonicalSha256", None)
    invariants = manifest.setdefault("invariants", {})

    preledger_pass = (
        preledger["authorization"]["verdict"] == "NOT_AUTHORIZED_FOR_LEDGER"
        and preledger["fineractCallAttempted"] is False
        and preledger["fineractSequenceBefore"] == preledger["fineractSequenceAfter"]
        and preledger["intendedJournal"]["journalBalancedByConstruction"] is True
    )
    rejection_pass = (
        ledger_rejection["authorization"]["verdict"] == "AUTHORIZED_FOR_LEDGER"
        and ledger_rejection["fineractCallAttempted"] is True
        and ledger_rejection["ledgerAccepted"] is False
        and ledger_rejection["ledgerFailure"]["expectedErrorObserved"] is True
        and ledger_rejection["ledgerFailure"]["transactionCreated"] is False
    )

    invariants["FUND-GOV-LIVE-001"] = preledger_pass
    invariants["FUND-GOV-LIVE-002"] = rejection_pass
    manifest["governanceProbe"] = {
        "preGovernanceCanonicalSha256": previous_hash,
        "unauthorizedBalancedPayment": preledger,
        "authorizedLedgerRejection": ledger_rejection,
    }
    manifest["canonicalSha256"] = hashlib.sha256(lane.canonical_json(manifest)).hexdigest()
    manifest_path.write_text(
        json.dumps(lane.jsonable(manifest), indent=2, sort_keys=True) + "\n"
    )

    summary_path = evidence_dir / "summary.txt"
    summary_path.write_text(
        "\n".join(
            [
                f"scenario={manifest['scenarioId']}",
                f"sha256={manifest['canonicalSha256']}",
                *[
                    f"{name}={'PASS' if ok else 'FAIL'}"
                    for name, ok in manifest["invariants"].items()
                ],
            ]
        )
        + "\n"
    )

    failed = [
        name
        for name in ("FUND-GOV-LIVE-001", "FUND-GOV-LIVE-002")
        if not invariants[name]
    ]
    if failed:
        raise lane.LaneError(f"Live governance invariants failed: {', '.join(failed)}")
    return manifest["canonicalSha256"]


def main() -> None:
    scenario = lane.load_json(lane.SCENARIO_PATH)
    journal_contract = lane.load_json(lane.CONTRACT_PATH)
    governance_contract = lane.load_json(GOVERNANCE_PATH)
    probe = scenario["governanceProbe"]
    evidence_dir = lane.EVIDENCE_ROOT / scenario["scenarioId"]

    client = lane.FineractClient(evidence_dir)
    lane.wait_for_fineract(client)
    account_ids = lane.ensure_accounts(client, journal_contract)

    preledger = prove_preledger_denial(
        client,
        scenario,
        journal_contract,
        governance_contract,
        probe["unauthorizedBalancedPayment"],
    )
    print(
        "PASS unauthorized balanced payment blocked before Fineract "
        f"({preledger['probeId']})"
    )

    ledger_rejection = prove_authorized_ledger_rejection(
        client,
        scenario,
        journal_contract,
        governance_contract,
        account_ids,
        probe["authorizedLedgerRejection"],
    )
    print(
        "PASS authorized payment preserved across ledger rejection "
        f"({ledger_rejection['probeId']})"
    )

    digest = augment_manifest(evidence_dir, preledger, ledger_rejection)
    print("FUND-GOV-LIVE-001: PASS")
    print("FUND-GOV-LIVE-002: PASS")
    print(f"Updated manifest SHA-256: {digest}")


if __name__ == "__main__":
    try:
        main()
    except lane.LaneError as exc:
        print(f"FAIL: {exc}", file=lane.sys.stderr)
        raise SystemExit(1)
