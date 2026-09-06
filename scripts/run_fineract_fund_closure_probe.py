#!/usr/bin/env python3
"""Prove closed-period behavior for the synthetic TRS Fund Fineract lane.

This probe runs after the base live-ledger smoke test. It creates an accounting
closure, requires a closed-date manual journal to fail for Fineract's explicit
ACCOUNTING_CLOSED reason, then posts the same synthetic correction on an open
business date and reverses it there. The probe augments the existing evidence
manifest without changing the base scenario's final economic state.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import run_fineract_fund_lane as lane

ERROR_CODE = "error.msg.gljournalentry.invalid.accounting.closed"


def normalize_date(value: Any) -> str | None:
    if isinstance(value, str):
        return value[:10]
    if isinstance(value, list) and len(value) >= 3:
        try:
            return f"{int(value[0]):04d}-{int(value[1]):02d}-{int(value[2]):02d}"
        except (TypeError, ValueError):
            return None
    return None


def create_or_verify_closure(
    client: lane.FineractClient, scenario: dict[str, Any], probe: dict[str, Any]
) -> dict[str, Any]:
    office_id = scenario["officeId"]
    closing_date = probe["closingDate"]

    _, existing_body = client.call("GET", "/glclosures", query={"officeId": office_id})
    existing = lane.page_items(existing_body)
    if not existing and isinstance(existing_body, list):
        existing = existing_body

    match = next(
        (
            row
            for row in existing
            if normalize_date(row.get("closingDate")) == closing_date
            and int(row.get("officeId", office_id)) == int(office_id)
        ),
        None,
    )

    created_response: Any = None
    if match is None:
        payload = {
            "officeId": office_id,
            "closingDate": closing_date,
            "comments": "Baudot synthetic Fund accounting-closure proof; no production authority",
            "dateFormat": "yyyy-MM-dd",
            "locale": "en",
        }
        _, created_response = client.call("POST", "/glclosures", payload)
        closure_id = (
            created_response.get("resourceId")
            if isinstance(created_response, dict)
            else None
        )
    else:
        closure_id = match.get("id")

    _, verify_body = client.call("GET", "/glclosures", query={"officeId": office_id})
    rows = lane.page_items(verify_body)
    if not rows and isinstance(verify_body, list):
        rows = verify_body
    verified = next(
        (
            row
            for row in rows
            if normalize_date(row.get("closingDate")) == closing_date
            and int(row.get("officeId", office_id)) == int(office_id)
        ),
        None,
    )
    if verified is None:
        raise lane.LaneError(
            f"Accounting closure {closing_date} for office {office_id} was not observable after creation"
        )

    closure_id = verified.get("id", closure_id)
    return {
        "closingDate": closing_date,
        "officeId": office_id,
        "closureResourceId": closure_id,
        "createdThisRun": match is None,
        "createResponse": created_response,
    }


def journal_payload(
    scenario: dict[str, Any],
    contract: dict[str, Any],
    account_ids: dict[str, int],
    event: dict[str, Any],
    posting_date: str,
) -> dict[str, Any]:
    mapping = contract["events"][event["type"]]
    return {
        "officeId": scenario["officeId"],
        "transactionDate": posting_date,
        "currencyCode": scenario["currencyCode"],
        "comments": f"{event['id']} | {event['memo']}",
        "debits": [
            {
                "glAccountId": account_ids[mapping["debit"]],
                "amount": str(lane.d(event["amount"])),
            }
        ],
        "credits": [
            {
                "glAccountId": account_ids[mapping["credit"]],
                "amount": str(lane.d(event["amount"])),
            }
        ],
        "dateFormat": "yyyy-MM-dd",
        "locale": "en",
    }


def require_closed_period_rejection(
    client: lane.FineractClient,
    scenario: dict[str, Any],
    contract: dict[str, Any],
    account_ids: dict[str, int],
    probe: dict[str, Any],
) -> dict[str, Any]:
    event = dict(probe["event"])
    event["id"] = probe["rejectedEventId"]
    event["memo"] = f"{event['memo']} | expected closed-period rejection"
    payload = journal_payload(
        scenario,
        contract,
        account_ids,
        event,
        probe["rejectedPostingDate"],
    )
    status, response = client.call(
        "POST", "/journalentries", payload, allow_error=True
    )
    serialized = json.dumps(response, sort_keys=True).lower()
    correct_reason = ERROR_CODE in serialized
    rejected = not 200 <= status < 300
    if not rejected:
        raise lane.LaneError(
            f"Closed-period journal unexpectedly succeeded with HTTP {status}: {response}"
        )
    if not correct_reason:
        raise lane.LaneError(
            f"Closed-period journal failed for the wrong reason; expected {ERROR_CODE}: {response}"
        )
    return {
        "syntheticBusinessTransactionId": event["id"],
        "postingDate": probe["rejectedPostingDate"],
        "httpStatus": status,
        "expectedErrorCode": ERROR_CODE,
        "expectedErrorObserved": True,
        "transactionCreated": False,
    }


def post_open_date_correction(
    client: lane.FineractClient,
    scenario: dict[str, Any],
    contract: dict[str, Any],
    account_ids: dict[str, int],
    probe: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    event = dict(probe["event"])
    event["id"] = probe["authorizedEventId"]
    event["memo"] = f"{event['memo']} | authorized open-date correction"
    open_scenario = dict(scenario)
    open_scenario["postingDate"] = probe["authorizedOpenDate"]

    record = lane.post_event(client, open_scenario, contract, account_ids, event)
    reversal = lane.reverse_transaction(
        client,
        record["fineractTransactionId"],
        f"Reverse {event['id']} after closure probe to preserve base scenario end state",
    )

    _, body = client.call(
        "GET",
        "/journalentries",
        query={
            "transactionId": record["fineractTransactionId"],
            "transactionDetails": "true",
        },
    )
    rows = lane.page_items(body)
    reversed_flags = [row.get("reversed") for row in rows if "reversed" in row]
    all_reversed = bool(reversed_flags) and all(flag is True for flag in reversed_flags)
    if not all_reversed:
        raise lane.LaneError(
            f"Open-date correction reversal was not observable on every journal row: {rows}"
        )
    return record, {
        "apiShape": reversal["apiShape"],
        "httpStatus": reversal["status"],
        "allOriginalRowsMarkedReversed": True,
    }


def augment_manifest(
    evidence_dir: Path,
    closure: dict[str, Any],
    rejection: dict[str, Any],
    correction: dict[str, Any],
    correction_reversal: dict[str, Any],
) -> str:
    manifest_path = evidence_dir / "manifest.json"
    if not manifest_path.exists():
        raise lane.LaneError(
            f"Base Fineract evidence manifest is missing: {manifest_path}"
        )
    manifest = json.loads(manifest_path.read_text())
    previous_hash = manifest.pop("canonicalSha256", None)

    closure_pass = (
        closure["closureResourceId"] is not None
        and rejection["expectedErrorObserved"] is True
        and rejection["transactionCreated"] is False
        and bool(correction["fineractTransactionId"])
        and correction_reversal["allOriginalRowsMarkedReversed"] is True
    )
    manifest.setdefault("invariants", {})["FUND-CLS-001"] = closure_pass
    manifest["closureProbe"] = {
        "preClosureCanonicalSha256": previous_hash,
        "closure": closure,
        "closedDateRejection": rejection,
        "authorizedOpenDateCorrection": correction,
        "authorizedOpenDateCorrectionReversal": correction_reversal,
    }
    manifest["canonicalSha256"] = hashlib.sha256(
        lane.canonical_json(manifest)
    ).hexdigest()
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
    if not closure_pass:
        raise lane.LaneError("FUND-CLS-001 failed")
    return manifest["canonicalSha256"]


def main() -> None:
    scenario = lane.load_json(lane.SCENARIO_PATH)
    contract = lane.load_json(lane.CONTRACT_PATH)
    probe = scenario["closureProbe"]
    evidence_dir = lane.EVIDENCE_ROOT / scenario["scenarioId"]

    client = lane.FineractClient(evidence_dir)
    lane.wait_for_fineract(client)
    account_ids = lane.ensure_accounts(client, contract)

    closure = create_or_verify_closure(client, scenario, probe)
    print(
        f"PASS closure {closure['closingDate']} -> resource {closure['closureResourceId']}"
    )

    rejection = require_closed_period_rejection(
        client, scenario, contract, account_ids, probe
    )
    print(
        f"PASS closed-date rejection {rejection['syntheticBusinessTransactionId']} "
        f"-> HTTP {rejection['httpStatus']} / {ERROR_CODE}"
    )

    correction, correction_reversal = post_open_date_correction(
        client, scenario, contract, account_ids, probe
    )
    print(
        f"PASS open-date correction {correction['syntheticBusinessTransactionId']} "
        f"-> {correction['fineractTransactionId']}"
    )
    print(
        f"PASS open-date correction reversal via {correction_reversal['apiShape']}"
    )

    digest = augment_manifest(
        evidence_dir, closure, rejection, correction, correction_reversal
    )
    print("FUND-CLS-001: PASS")
    print(f"Updated manifest SHA-256: {digest}")


if __name__ == "__main__":
    try:
        main()
    except lane.LaneError as exc:
        print(f"FAIL: {exc}", file=lane.sys.stderr)
        raise SystemExit(1)
