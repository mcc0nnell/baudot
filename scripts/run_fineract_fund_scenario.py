#!/usr/bin/env python3
from __future__ import annotations

import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "interop" / "fineract"))

from fineract_executor import (  # noqa: E402
    ExecutionLedger,
    FineractConfig,
    FineractExecutor,
    UrllibJsonTransport,
    basic_auth_headers,
    load_contract,
)
from testkit.fund.runtime.fund_runtime import FundEvent, FundState, fold_events  # noqa: E402


DEFAULT_SCENARIO = ROOT / "testkit" / "fund" / "runtime" / "five-year-synthetic.json"
DEFAULT_CONTRACT = ROOT / "interop" / "fineract" / "journal-contract-v1.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute a validated synthetic TRS Fund scenario against Apache Fineract and reconcile it back to Baudot."
    )
    parser.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--base-url", default=os.getenv("FINERACT_BASE_URL"))
    parser.add_argument("--username", default=os.getenv("FINERACT_USERNAME"))
    parser.add_argument("--password", default=os.getenv("FINERACT_PASSWORD"))
    parser.add_argument("--tenant-id", default=os.getenv("FINERACT_TENANT_ID", "default"))
    parser.add_argument("--office-id", type=int, default=int(os.getenv("FINERACT_OFFICE_ID", "1")))
    parser.add_argument("--bootstrap-accounts", action="store_true")
    parser.add_argument("--plan-only", action="store_true", help="Validate and fold the scenario without making Fineract requests.")
    parser.add_argument("--evidence-out", type=Path)
    return parser.parse_args()


def load_scenario(path: Path) -> tuple[dict[str, Any], list[FundEvent]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    events: list[FundEvent] = []
    for item in raw["events"]:
        events.append(
            FundEvent(
                seq=int(item["seq"]),
                event_type=item["eventType"],  # type: ignore[arg-type]
                transaction_id=item["transactionId"],
                actor_id=item.get("actorId", "synthetic-fineract-runner"),
                effective_date=item["effectiveDate"],
                amount=Decimal(item.get("amount", "0")),
                entity_id=item.get("entityId"),
                policy_hash=item.get("policyHash"),
                target_transaction_id=item.get("targetTransactionId"),
                adjustment_direction=item.get("adjustmentDirection"),
                note=item.get("note"),
            )
        )
    return raw, events


def state_json(state: FundState) -> dict[str, Any]:
    return {
        "programYear": state.program_year,
        "policyHash": state.policy_hash,
        "cash": format(state.cash, "f"),
        "contributorReceivable": format(state.contributor_receivable, "f"),
        "providerPayable": format(state.provider_payable, "f"),
        "contributionRevenue": format(state.contribution_revenue, "f"),
        "providerCompensationExpense": format(state.provider_compensation_expense, "f"),
        "closedThrough": state.closed_through,
        "lastSeq": state.last_seq,
    }


def main() -> int:
    args = parse_args()
    scenario_raw, events = load_scenario(args.scenario)

    # Fail closed before any external write: the independent Baudot reducer must
    # accept the complete event stream first.
    expected_state = fold_events(events)
    declared = scenario_raw.get("expectedFinalState")
    if declared:
        actual_expected = state_json(expected_state)
        for key, value in declared.items():
            if str(actual_expected.get(key)) != str(value):
                raise SystemExit(
                    f"scenario expectedFinalState mismatch for {key}: declared {value}, reducer produced {actual_expected.get(key)}"
                )

    if args.plan_only:
        print(json.dumps({"scenarioId": scenario_raw.get("scenarioId"), "expectedFundState": state_json(expected_state)}, indent=2))
        return 0

    if not args.base_url or not args.username or args.password is None:
        raise SystemExit(
            "live execution requires --base-url/FINERACT_BASE_URL, --username/FINERACT_USERNAME, and --password/FINERACT_PASSWORD"
        )

    contract = load_contract(str(args.contract))
    headers = basic_auth_headers(args.username, args.password, tenant_id=args.tenant_id)
    transport = UrllibJsonTransport(args.base_url, default_headers=headers)
    executor = FineractExecutor(
        transport,
        contract,
        config=FineractConfig(office_id=args.office_id),
    )
    account_ids = executor.resolve_accounts(create_missing=args.bootstrap_accounts)
    ledger = ExecutionLedger()

    for event in events:
        record = executor.execute_event(event, ledger)
        if record is not None and not record.reconciled:
            raise SystemExit(
                f"Fineract transaction did not reconcile for synthetic event {event.transaction_id}: {record.to_evidence()}"
            )

    reconciliation = executor.reconcile_fund_state(expected_state)
    evidence = {
        "schema": "baudot.fineract-scenario-evidence@1",
        "scenarioId": scenario_raw.get("scenarioId"),
        "targetFineract": contract.get("targetFineract"),
        "accountIds": account_ids,
        "expectedFundState": state_json(expected_state),
        "execution": [ledger.records[key].to_evidence() for key in sorted(ledger.records)],
        "finalReconciliation": {
            "expected": {code: format(value, "f") for code, value in reconciliation.expected.items()},
            "actual": {code: format(value, "f") for code, value in reconciliation.actual.items()},
            "accountJournalEntryIds": {code: list(ids) for code, ids in reconciliation.account_entry_ids.items()},
            "reconciled": reconciliation.reconciled,
        },
    }

    if args.evidence_out:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(evidence["finalReconciliation"], indent=2, sort_keys=True))
    if not reconciliation.reconciled:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
