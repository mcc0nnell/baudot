#!/usr/bin/env python3
"""Execute a deterministic synthetic TRS Fund smoke scenario against Fineract.

This lane deliberately keeps TRS program semantics in Baudot. Fineract is only an
external accounting implementation under test. All records created by this script
are synthetic and the resulting evidence must not be interpreted as FCC, Fund
administrator, provider, contributor, or payment-network authority.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import ssl
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_PATH = ROOT / "testkit" / "fund" / "fineract-live-smoke-v1.json"
CONTRACT_PATH = ROOT / "interop" / "fineract" / "journal-contract-v1.json"

BASE_URL = os.environ.get(
    "FINERACT_BASE_URL", "https://localhost:8443/fineract-provider/api/v1"
).rstrip("/")
USERNAME = os.environ.get("FINERACT_USERNAME", "mifos")
PASSWORD = os.environ.get("FINERACT_PASSWORD", "password")
TENANT = os.environ.get("FINERACT_TENANT", "default")
INSECURE_TLS = os.environ.get("FINERACT_INSECURE_TLS", "0") == "1"
WAIT_SECONDS = int(os.environ.get("FINERACT_WAIT_SECONDS", "240"))
EVIDENCE_ROOT = Path(
    os.environ.get("TRS_FUND_EVIDENCE_DIR", str(ROOT / "artifacts" / "trs-fund-fineract"))
)

ACCOUNT_TYPE_IDS = {
    "ASSET": 1,
    "LIABILITY": 2,
    "EQUITY": 3,
    "INCOME": 4,
    "EXPENSE": 5,
}


class LaneError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def d(value: Any) -> Decimal:
    return Decimal(str(value))


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    return value


class FineractClient:
    def __init__(self, evidence_dir: Path) -> None:
        self.evidence_dir = evidence_dir / "http"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.sequence = 0
        token = base64.b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {token}",
            "Fineract-Platform-TenantId": TENANT,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self.ssl_context = None
        if INSECURE_TLS:
            self.ssl_context = ssl._create_unverified_context()  # noqa: SLF001

    def call(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        allow_error: bool = False,
    ) -> tuple[int, Any]:
        self.sequence += 1
        url = f"{BASE_URL}/{path.lstrip('/')}"
        if query:
            url += "?" + urlencode(query)
        body = None if payload is None else canonical_json(payload)
        request = Request(url, data=body, method=method, headers=self.headers)
        status = 0
        raw = b""
        error_text = None
        try:
            with urlopen(request, context=self.ssl_context, timeout=30) as response:
                status = response.status
                raw = response.read()
        except HTTPError as exc:
            status = exc.code
            raw = exc.read()
            error_text = str(exc)
        except URLError as exc:
            error_text = str(exc)
            if not allow_error:
                raise LaneError(f"Fineract request failed: {method} {url}: {exc}") from exc

        parsed: Any = None
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw.decode("utf-8", errors="replace")

        record = {
            "sequence": self.sequence,
            "method": method,
            "url": url,
            "request": payload,
            "status": status,
            "response": parsed,
            "error": error_text,
        }
        stem = f"{self.sequence:03d}-{method.lower()}-{path.strip('/').replace('/', '-') or 'root'}"
        (self.evidence_dir / f"{stem}.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n"
        )

        if not allow_error and not 200 <= status < 300:
            raise LaneError(f"Fineract returned HTTP {status} for {method} {url}: {parsed}")
        return status, parsed


def wait_for_fineract(client: FineractClient) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    last = "not attempted"
    while time.monotonic() < deadline:
        try:
            status, body = client.call("GET", "/offices", allow_error=True)
            if 200 <= status < 300:
                print("Fineract API: READY")
                return
            last = f"HTTP {status}: {body}"
        except LaneError as exc:
            last = str(exc)
        time.sleep(5)
    raise LaneError(f"Fineract did not become ready within {WAIT_SECONDS}s; last={last}")


def page_items(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ("pageItems", "content"):
            if isinstance(body.get(key), list):
                return body[key]
    return []


def ensure_accounts(
    client: FineractClient, contract: dict[str, Any]
) -> dict[str, int]:
    _, body = client.call("GET", "/glaccounts")
    existing = page_items(body)
    if not existing and isinstance(body, list):
        existing = body

    by_code = {str(row.get("glCode")): row for row in existing if row.get("glCode")}
    result: dict[str, int] = {}

    for source_code, definition in contract["accounts"].items():
        live_code = f"BAUDOT-{source_code}"
        row = by_code.get(live_code)
        if row is None:
            payload = {
                "name": f"Baudot Synthetic {definition['name']}",
                "glCode": live_code,
                "type": ACCOUNT_TYPE_IDS[definition["type"]],
                "usage": 1,
                "manualEntriesAllowed": True,
                "description": "Synthetic TRS Fund proving-ground account; no production authority",
            }
            _, created = client.call("POST", "/glaccounts", payload)
            account_id = created.get("resourceId") if isinstance(created, dict) else None
            if account_id is None:
                raise LaneError(f"Fineract did not return resourceId creating {live_code}: {created}")
            result[source_code] = int(account_id)
        else:
            result[source_code] = int(row["id"])

    return result


def extract_transaction_id(body: Any) -> str:
    if isinstance(body, dict):
        for key in ("transactionId", "resourceExternalId"):
            value = body.get(key)
            if value not in (None, ""):
                return str(value)
    raise LaneError(f"Fineract did not return a transactionId: {body}")


def classify_entry_type(value: Any) -> str | None:
    if isinstance(value, dict):
        code = str(value.get("code", "")).lower()
        label = str(value.get("value", "")).lower()
        entry_id = value.get("id")
        if "debit" in code or "debit" in label or entry_id == 1:
            return "debit"
        if "credit" in code or "credit" in label or entry_id == 2:
            return "credit"
    if isinstance(value, str):
        lowered = value.lower()
        if "debit" in lowered:
            return "debit"
        if "credit" in lowered:
            return "credit"
    return None


def verify_posted_transaction(
    client: FineractClient,
    transaction_id: str,
    debit_id: int,
    credit_id: int,
    amount: Decimal,
) -> list[dict[str, Any]]:
    _, body = client.call(
        "GET",
        "/journalentries",
        query={"transactionId": transaction_id, "transactionDetails": "true"},
    )
    entries = page_items(body)
    if not entries:
        raise LaneError(f"No journal entries returned for transaction {transaction_id}")

    seen = set()
    for row in entries:
        account_id = row.get("glAccountId")
        if account_id is None and isinstance(row.get("glAccount"), dict):
            account_id = row["glAccount"].get("id")
        side = classify_entry_type(row.get("entryType"))
        row_amount = row.get("amount")
        if account_id is not None and side and row_amount is not None:
            seen.add((int(account_id), side, d(row_amount)))

    required = {(debit_id, "debit", amount), (credit_id, "credit", amount)}
    if not required.issubset(seen):
        raise LaneError(
            f"Transaction {transaction_id} did not expose expected balanced rows; "
            f"required={required!r}, seen={seen!r}"
        )
    return entries


def post_event(
    client: FineractClient,
    scenario: dict[str, Any],
    contract: dict[str, Any],
    account_ids: dict[str, int],
    event: dict[str, Any],
) -> dict[str, Any]:
    mapping = contract["events"][event["type"]]
    amount = d(event["amount"])
    debit_code = mapping["debit"]
    credit_code = mapping["credit"]
    payload = {
        "officeId": scenario["officeId"],
        "transactionDate": scenario["postingDate"],
        "currencyCode": scenario["currencyCode"],
        "comments": f"{event['id']} | {event['memo']}",
        "debits": [{"glAccountId": account_ids[debit_code], "amount": str(amount)}],
        "credits": [{"glAccountId": account_ids[credit_code], "amount": str(amount)}],
        "dateFormat": "yyyy-MM-dd",
        "locale": "en",
    }
    _, response = client.call("POST", "/journalentries", payload)
    transaction_id = extract_transaction_id(response)
    entries = verify_posted_transaction(
        client,
        transaction_id,
        account_ids[debit_code],
        account_ids[credit_code],
        amount,
    )
    return {
        "syntheticBusinessTransactionId": event["id"],
        "eventType": event["type"],
        "postingDate": scenario["postingDate"],
        "amount": str(amount),
        "expectedDebitAccount": debit_code,
        "expectedCreditAccount": credit_code,
        "fineractTransactionId": transaction_id,
        "fineractJournalEntryIds": [row.get("id") for row in entries if row.get("id") is not None],
        "balanced": True,
        "reconciled": True,
    }


def reverse_transaction(
    client: FineractClient, transaction_id: str, memo: str
) -> dict[str, Any]:
    payload = {"comments": memo, "locale": "en"}
    status, response = client.call(
        "POST",
        f"/journalentries/{transaction_id}",
        payload,
        query={"command": "reverse"},
        allow_error=True,
    )
    api_shape = "command=reverse"
    if not 200 <= status < 300:
        status, response = client.call(
            "POST",
            f"/journalentries/{transaction_id}/reversal",
            payload,
            allow_error=True,
        )
        api_shape = "/reversal"
    if not 200 <= status < 300:
        raise LaneError(f"Fineract reversal failed for {transaction_id}: HTTP {status}: {response}")
    return {"apiShape": api_shape, "status": status, "response": response}


def apply_balance(
    balances: dict[str, Decimal],
    contract: dict[str, Any],
    event_type: str,
    amount: Decimal,
    reverse: bool = False,
) -> None:
    mapping = contract["events"][event_type]
    sign = Decimal("-1") if reverse else Decimal("1")
    balances[mapping["debit"]] += amount * sign
    balances[mapping["credit"]] -= amount * sign


def main() -> None:
    scenario = load_json(SCENARIO_PATH)
    contract = load_json(CONTRACT_PATH)
    evidence_dir = EVIDENCE_ROOT / scenario["scenarioId"]
    evidence_dir.mkdir(parents=True, exist_ok=True)

    client = FineractClient(evidence_dir)
    wait_for_fineract(client)
    account_ids = ensure_accounts(client, contract)

    balances = {code: Decimal("0.00") for code in contract["accounts"]}
    evidence_events: list[dict[str, Any]] = []
    event_index = {event["id"]: event for event in scenario["events"]}

    for event in scenario["events"]:
        record = post_event(client, scenario, contract, account_ids, event)
        evidence_events.append(record)
        apply_balance(balances, contract, event["type"], d(event["amount"]))
        print(f"PASS posted {event['id']} -> {record['fineractTransactionId']}")

    probe = scenario["reversalProbe"]
    original = event_index[probe["eventId"]]
    original_record = next(
        row for row in evidence_events if row["syntheticBusinessTransactionId"] == original["id"]
    )
    reversal = reverse_transaction(
        client, original_record["fineractTransactionId"], probe["memo"]
    )
    apply_balance(balances, contract, original["type"], d(original["amount"]), reverse=True)
    print(f"PASS reversed {original['id']} via {reversal['apiShape']}")

    repost = dict(original)
    repost["id"] = probe["repostAs"]
    repost["memo"] = f"Repost after explicit reversal of {original['id']}"
    repost_record = post_event(client, scenario, contract, account_ids, repost)
    evidence_events.append(repost_record)
    apply_balance(balances, contract, repost["type"], d(repost["amount"]))
    print(f"PASS reposted {repost['id']} -> {repost_record['fineractTransactionId']}")

    expected = {code: d(value) for code, value in scenario["expectedFinalBalances"].items()}
    actual = {code: balances[code] for code in expected}

    invariants = {
        "FUND-ACC-001": all(row["balanced"] for row in evidence_events),
        "FUND-REC-001": balances["1200"] == Decimal("0.00"),
        "FUND-CLM-001": any(row["eventType"] == "providerClaimApproved" for row in evidence_events),
        "FUND-DIS-001": balances["2100"] == Decimal("0.00"),
        "FUND-ADJ-001": reversal["status"] in range(200, 300)
        and repost_record["fineractTransactionId"] != original_record["fineractTransactionId"],
        "FUND-AUD-001": all(
            row["fineractTransactionId"] and row["fineractJournalEntryIds"]
            for row in evidence_events
        ),
        "FUND-AUT-001": contract["authority"] == "synthetic-accounting-adapter-only"
        and scenario["claimBoundary"]["fineractAcceptanceIsProgramAuthorization"] is False,
    }
    balances_match = actual == expected
    invariants["EXPECTED-BALANCES"] = balances_match

    manifest = {
        "schema": "baudot.trs-fund-fineract-evidence@1",
        "scenarioId": scenario["scenarioId"],
        "fineractBaseUrl": BASE_URL,
        "tenant": TENANT,
        "accountMap": account_ids,
        "policyProvenance": scenario["policyProvenance"],
        "events": evidence_events,
        "reversal": {
            "originalSyntheticEventId": original["id"],
            "originalFineractTransactionId": original_record["fineractTransactionId"],
            "apiShape": reversal["apiShape"],
            "repostSyntheticEventId": repost["id"],
            "repostFineractTransactionId": repost_record["fineractTransactionId"],
        },
        "expectedFinalBalances": jsonable(expected),
        "actualFinalBalances": jsonable(actual),
        "invariants": invariants,
        "claimBoundary": scenario["claimBoundary"],
    }
    manifest["canonicalSha256"] = hashlib.sha256(canonical_json(manifest)).hexdigest()
    (evidence_dir / "manifest.json").write_text(
        json.dumps(jsonable(manifest), indent=2, sort_keys=True) + "\n"
    )
    (evidence_dir / "summary.txt").write_text(
        "\n".join(
            [
                f"scenario={scenario['scenarioId']}",
                f"sha256={manifest['canonicalSha256']}",
                *[f"{name}={'PASS' if ok else 'FAIL'}" for name, ok in invariants.items()],
            ]
        )
        + "\n"
    )

    failed = [name for name, ok in invariants.items() if not ok]
    if failed:
        raise LaneError(f"Synthetic Fund Fineract lane failed invariants: {', '.join(failed)}")

    print("Synthetic TRS Fund external-ledger lane: PASS")
    print(f"Evidence: {evidence_dir}")
    print(f"Manifest SHA-256: {manifest['canonicalSha256']}")


if __name__ == "__main__":
    try:
        main()
    except LaneError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
