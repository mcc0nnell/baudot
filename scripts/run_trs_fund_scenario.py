#!/usr/bin/env python3
"""Run a deterministic synthetic TRS Fund scenario.

The runtime is intentionally small and event-first:

- commands carry stable idempotency keys;
- accepted commands append immutable synthetic Fund events;
- state is folded deterministically from the accepted event stream;
- duplicate retries are acknowledged but never re-applied;
- each accepted business event emits a journal intent using the bounded
  Fineract contract; and
- final state is independently reconciled to the scenario expectation.

This is a synthetic proving-ground runtime. It is not an FCC, Rolka Loube,
or Fineract production implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "interop" / "fineract" / "journal-contract-v1.json"

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


COMMAND_TO_CONTRACT_EVENT = {
    "CONTRIBUTOR_ASSESSED": "contributorAssessment",
    "CONTRIBUTOR_RECEIPT": "contributorReceipt",
    "PROVIDER_CLAIM_APPROVED": "providerClaimApproved",
    "PROVIDER_DISBURSED": "providerDisbursement",
}


def require_positive(amount: Decimal, command_type: str) -> None:
    if amount <= 0:
        raise ValueError(f"{command_type}: amount must be positive")


def apply_event(state: FundState, event: dict[str, Any]) -> FundState:
    """Pure deterministic reducer. No I/O and no Fineract calls."""
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
        if amount > state.contributor_receivable:
            raise ValueError(
                f"{event_type}: receipt {money_text(amount)} exceeds open contributor receivable "
                f"{money_text(state.contributor_receivable)}"
            )
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
        if amount > state.provider_payable:
            raise ValueError(
                f"{event_type}: disbursement {money_text(amount)} exceeds open provider payable "
                f"{money_text(state.provider_payable)}"
            )
        if amount > state.cash:
            raise ValueError(
                f"{event_type}: disbursement {money_text(amount)} exceeds Fund cash "
                f"{money_text(state.cash)}"
            )
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
        if event["seq"] != expected_seq:
            raise ValueError(f"event sequence gap: expected {expected_seq}, got {event['seq']}")
        key = event["idempotencyKey"]
        if key in seen_keys:
            raise ValueError(f"event log contains duplicate idempotency key: {key}")
        seen_keys.add(key)
        state = apply_event(state, event)
        expected_seq += 1

    return state


def journal_intent(event: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    contract_event_name = COMMAND_TO_CONTRACT_EVENT[event["type"]]
    mapping = contract["events"][contract_event_name]
    accounts = contract["accounts"]

    return {
        "syntheticBusinessTransactionId": event["idempotencyKey"],
        "eventSeq": event["seq"],
        "eventType": contract_event_name,
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


def expected_state_from_json(expected: dict[str, Any]) -> FundState:
    return FundState(
        cash=money(expected["cash"]),
        contributor_receivable=money(expected["contributorReceivable"]),
        provider_payable=money(expected["providerPayable"]),
        contribution_revenue=money(expected["contributionRevenue"]),
        provider_compensation_expense=money(expected["providerCompensationExpense"]),
        last_seq=int(expected["lastSeq"]),
    )


def run_scenario(scenario_path: Path, contract_path: Path) -> dict[str, Any]:
    scenario = json.loads(scenario_path.read_text())
    contract = json.loads(contract_path.read_text())

    events: list[dict[str, Any]] = []
    key_to_seq: dict[str, int] = {}
    command_results: list[dict[str, Any]] = []
    intents: list[dict[str, Any]] = []
    state = FundState()

    for command in scenario["commands"]:
        command_type = command["type"]
        if command_type not in COMMAND_TO_CONTRACT_EVENT:
            raise ValueError(f"unsupported command type: {command_type}")

        key = command["idempotencyKey"]
        if key in key_to_seq:
            command_results.append(
                {
                    "idempotencyKey": key,
                    "seq": key_to_seq[key],
                    "applied": False,
                    "reason": "idempotent-replay",
                }
            )
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

        next_state = apply_event(state, event)
        events.append(event)
        key_to_seq[key] = event["seq"]
        intents.append(journal_intent(event, contract))
        state = next_state
        command_results.append(
            {
                "idempotencyKey": key,
                "seq": event["seq"],
                "applied": True,
            }
        )

    # Cold-start proof: rebuild state from the immutable accepted log and ensure
    # it is byte-for-byte equivalent at the semantic state boundary.
    replayed_state = fold_events(events)
    if replayed_state != state:
        raise AssertionError("cold-start replay diverged from live fold")

    expected = expected_state_from_json(scenario["expected"]["finalState"])
    if state != expected:
        raise AssertionError(
            "final-state reconciliation failed:\n"
            f"expected={expected.to_json()}\n"
            f"actual={state.to_json()}"
        )

    applied_count = sum(1 for result in command_results if result["applied"])
    replay_count = len(command_results) - applied_count
    if applied_count != int(scenario["expected"]["acceptedEvents"]):
        raise AssertionError(
            f"accepted event count: expected {scenario['expected']['acceptedEvents']}, got {applied_count}"
        )
    if replay_count != int(scenario["expected"]["idempotentReplays"]):
        raise AssertionError(
            f"idempotent replay count: expected {scenario['expected']['idempotentReplays']}, got {replay_count}"
        )

    return {
        "schema": "baudot.trs-fund-scenario-evidence@1",
        "scenarioId": scenario["scenarioId"],
        "scenarioSha256": sha256_file(scenario_path),
        "journalContractSha256": sha256_file(contract_path),
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
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--evidence", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    evidence = run_scenario(args.scenario, args.contract)
    rendered = json.dumps(evidence, indent=2, sort_keys=True)

    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(rendered + "\n")

    print(rendered)
    print(f"TRS Fund scenario {evidence['scenarioId']}: PASS")


if __name__ == "__main__":
    main()
