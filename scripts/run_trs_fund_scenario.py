#!/usr/bin/env python3
"""Run a deterministic synthetic TRS Fund scenario.

The event log is scenario execution authority only. Public Fund policy remains in
canonical public fixtures; accounting vocabulary remains in the canonical
Fineract journal contract; provider lifecycle invariants remain in the runtime
lifecycle contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JOURNAL = ROOT / "interop" / "fineract" / "journal-contract-v1.json"
DEFAULT_RUNTIME = ROOT / "testkit" / "fund" / "trs-fund-runtime-contract-v1.json"
MONEY = Decimal("0.01")


def money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def money_text(value: Decimal) -> str:
    return f"{value.quantize(MONEY, rounding=ROUND_HALF_UP):.2f}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True)
class FundState:
    cash: Decimal = Decimal("0.00")
    contributor_receivable: Decimal = Decimal("0.00")
    provider_payable: Decimal = Decimal("0.00")
    contribution_revenue: Decimal = Decimal("0.00")
    provider_compensation_expense: Decimal = Decimal("0.00")
    last_seq: int = 0

    def to_json(self) -> dict[str, Any]:
        return {
            "cash": money_text(self.cash),
            "contributorReceivable": money_text(self.contributor_receivable),
            "providerPayable": money_text(self.provider_payable),
            "contributionRevenue": money_text(self.contribution_revenue),
            "providerCompensationExpense": money_text(self.provider_compensation_expense),
            "lastSeq": self.last_seq,
        }


COMMAND_TO_JOURNAL_EVENT = {
    "CONTRIBUTOR_ASSESSED": "contributorAssessment",
    "CONTRIBUTOR_RECEIPT": "contributorReceipt",
    "PROVIDER_CLAIM_APPROVED": "providerClaimApproved",
    "PROVIDER_DISBURSED": "providerDisbursement",
}


def validate_authority_contracts(journal: dict[str, Any], runtime: dict[str, Any]) -> None:
    require(journal.get("schema") == "baudot.fineract-trs-journal-contract@1", "unexpected journal contract")
    require(runtime.get("schema") == "baudot.trs-fund-runtime-contract@1", "unexpected lifecycle contract")
    require(runtime.get("status") == "experimental", "lifecycle contract must remain experimental")
    require("accounts" not in runtime, "lifecycle runtime must not define accounts")
    require("rateProfiles" not in runtime, "lifecycle runtime must not define rates")
    require(runtime["dependsOn"].get("journalContract") == journal["schema"],
            "lifecycle contract no longer depends on canonical journal contract")

    scenarios = {item["id"]: item for item in runtime["scenarios"]}
    require(scenarios["FUND-001"].get("journalEvent") == "providerClaimApproved",
            "event runtime provider approval drifted from FUND-001")
    require(scenarios["FUND-002"].get("journalEvent") == "providerDisbursement",
            "event runtime provider disbursement drifted from FUND-002")

    for event_name in COMMAND_TO_JOURNAL_EVENT.values():
        require(event_name in journal["events"], f"missing canonical journal event: {event_name}")


def require_positive(amount: Decimal, event_type: str) -> None:
    require(amount > 0, f"{event_type}: amount must be positive")


def apply_event(state: FundState, event: dict[str, Any]) -> FundState:
    amount = money(event["amount"])
    event_type = event["type"]
    require_positive(amount, event_type)

    if event_type == "CONTRIBUTOR_ASSESSED":
        return FundState(
            cash=state.cash,
            contributor_receivable=state.contributor_receivable + amount,
            provider_payable=state.provider_payable,
            contribution_revenue=state.contribution_revenue + amount,
            provider_compensation_expense=state.provider_compensation_expense,
            last_seq=event["seq"],
        )
    if event_type == "CONTRIBUTOR_RECEIPT":
        require(amount <= state.contributor_receivable,
                f"{event_type}: receipt exceeds open contributor receivable")
        return FundState(
            cash=state.cash + amount,
            contributor_receivable=state.contributor_receivable - amount,
            provider_payable=state.provider_payable,
            contribution_revenue=state.contribution_revenue,
            provider_compensation_expense=state.provider_compensation_expense,
            last_seq=event["seq"],
        )
    if event_type == "PROVIDER_CLAIM_APPROVED":
        return FundState(
            cash=state.cash,
            contributor_receivable=state.contributor_receivable,
            provider_payable=state.provider_payable + amount,
            contribution_revenue=state.contribution_revenue,
            provider_compensation_expense=state.provider_compensation_expense + amount,
            last_seq=event["seq"],
        )
    if event_type == "PROVIDER_DISBURSED":
        require(amount <= state.provider_payable,
                f"{event_type}: disbursement exceeds open provider payable")
        require(amount <= state.cash, f"{event_type}: disbursement exceeds Fund cash")
        return FundState(
            cash=state.cash - amount,
            contributor_receivable=state.contributor_receivable,
            provider_payable=state.provider_payable - amount,
            contribution_revenue=state.contribution_revenue,
            provider_compensation_expense=state.provider_compensation_expense,
            last_seq=event["seq"],
        )
    raise ValueError(f"unsupported event type: {event_type}")


def fold_events(events: list[dict[str, Any]]) -> FundState:
    state = FundState()
    expected_seq = 1
    seen_keys: set[str] = set()
    for event in events:
        require(event["seq"] == expected_seq,
                f"event sequence gap: expected {expected_seq}, got {event['seq']}")
        key = event["idempotencyKey"]
        require(key not in seen_keys, f"event log contains duplicate idempotency key: {key}")
        seen_keys.add(key)
        state = apply_event(state, event)
        expected_seq += 1
    return state


def journal_intent(event: dict[str, Any], journal: dict[str, Any]) -> dict[str, Any]:
    event_name = COMMAND_TO_JOURNAL_EVENT[event["type"]]
    mapping = journal["events"][event_name]
    accounts = journal["accounts"]
    return {
        "syntheticBusinessTransactionId": event["idempotencyKey"],
        "eventSeq": event["seq"],
        "eventType": event_name,
        "postingDate": event["effectiveDate"],
        "amount": money_text(money(event["amount"])),
        "debit": {
            "accountCode": mapping["debit"],
            "accountName": accounts[mapping["debit"]]["name"],
        },
        "credit": {
            "accountCode": mapping["credit"],
            "accountName": accounts[mapping["credit"]]["name"],
        },
        "businessAuthority": mapping["businessAuthority"],
        "fineractTransactionId": None,
        "fineractJournalEntryIds": [],
        "reconciled": False,
    }


def expected_state(expected: dict[str, Any]) -> FundState:
    return FundState(
        cash=money(expected["cash"]),
        contributor_receivable=money(expected["contributorReceivable"]),
        provider_payable=money(expected["providerPayable"]),
        contribution_revenue=money(expected["contributionRevenue"]),
        provider_compensation_expense=money(expected["providerCompensationExpense"]),
        last_seq=int(expected["lastSeq"]),
    )


def run_scenario(
    scenario_path: Path,
    journal_path: Path,
    runtime_path: Path,
) -> dict[str, Any]:
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    validate_authority_contracts(journal, runtime)

    require(scenario.get("schema") == "baudot.trs-fund-scenario@1", "unexpected scenario schema")
    require(scenario["claimBoundary"].get("syntheticOnly") is True, "scenario must remain synthetic")
    require(scenario["claimBoundary"].get("noFineractPostingInThisScenario") is True,
            "scenario cannot imply live Fineract posting")

    events: list[dict[str, Any]] = []
    key_to_seq: dict[str, int] = {}
    command_results: list[dict[str, Any]] = []
    intents: list[dict[str, Any]] = []
    state = FundState()

    for command in scenario["commands"]:
        command_type = command["type"]
        require(command_type in COMMAND_TO_JOURNAL_EVENT, f"unsupported command type: {command_type}")
        key = command["idempotencyKey"]

        if key in key_to_seq:
            command_results.append({
                "idempotencyKey": key,
                "seq": key_to_seq[key],
                "applied": False,
                "reason": "idempotent-replay",
            })
            continue

        event = {
            "seq": state.last_seq + 1,
            "idempotencyKey": key,
            "type": command_type,
            "effectiveDate": command["effectiveDate"],
            "amount": money_text(money(command["amount"])),
            "actorId": command.get("actorId", "synthetic-runner"),
            "authorityRef": command.get("authorityRef"),
        }
        state = apply_event(state, event)
        events.append(event)
        key_to_seq[key] = event["seq"]
        intents.append(journal_intent(event, journal))
        command_results.append({"idempotencyKey": key, "seq": event["seq"], "applied": True})

    replayed = fold_events(events)
    require(replayed == state, "cold-start replay diverged from live fold")
    require(state == expected_state(scenario["expected"]["finalState"]),
            "final-state reconciliation failed")

    applied = sum(1 for result in command_results if result["applied"])
    retries = len(command_results) - applied
    require(applied == int(scenario["expected"]["acceptedEvents"]), "accepted event count drift")
    require(retries == int(scenario["expected"]["idempotentReplays"]), "idempotent replay count drift")

    return {
        "schema": "baudot.trs-fund-scenario-evidence@1",
        "scenarioId": scenario["scenarioId"],
        "scenarioSha256": sha256_file(scenario_path),
        "journalContractSha256": sha256_file(journal_path),
        "runtimeLifecycleContractSha256": sha256_file(runtime_path),
        "authorityBindings": {
            "journalContract": journal["schema"],
            "runtimeLifecycleContract": runtime["schema"],
            "eventLogRole": "synthetic-scenario-execution-authority",
            "policyAuthorityOwnedHere": False,
            "rateAuthorityOwnedHere": False,
            "accountCatalogOwnedHere": False,
        },
        "acceptedEvents": events,
        "commandResults": command_results,
        "journalIntents": intents,
        "finalState": state.to_json(),
        "reconciliation": {
            "coldStartReplayMatches": True,
            "expectedFinalStateMatches": True,
            "fineractPosted": False,
            "fineractReconciled": False,
        },
        "claimBoundary": {
            "syntheticOnly": True,
            "programAuthorizationProven": False,
            "fineractProductionSuitabilityProven": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", type=Path)
    parser.add_argument("--contract", type=Path, default=DEFAULT_JOURNAL)
    parser.add_argument("--runtime-contract", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--evidence", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    evidence = run_scenario(args.scenario, args.contract, args.runtime_contract)
    rendered = json.dumps(evidence, indent=2, sort_keys=True)
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    print(f"TRS Fund scenario {evidence['scenarioId']}: PASS")


if __name__ == "__main__":
    main()
