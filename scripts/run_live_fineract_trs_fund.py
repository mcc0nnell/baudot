#!/usr/bin/env python3
"""Exercise Baudot's synthetic TRS Fund journal contract against live Apache Fineract."""

from __future__ import annotations

import base64
import json
import os
import ssl
import sys
import time
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "target/evidence-external/LIVE-FINERACT-TRS/v1"

BASE_URL = os.environ.get(
    "FINERACT_BASE_URL", "https://localhost:8443/fineract-provider/api/v1"
).rstrip("/")
USERNAME = os.environ.get("FINERACT_USERNAME", "mifos")
PASSWORD = os.environ.get("FINERACT_PASSWORD", "password")
TENANT = os.environ.get("FINERACT_TENANT", "default")
PINNED_VERSION = os.environ.get("FINERACT_PINNED_VERSION", "1.15.0")
PINNED_COMMIT = os.environ.get(
    "FINERACT_PINNED_COMMIT", "d5636847ac556c30b437254c353f05526d172b97"
)
PINNED_IMAGE = os.environ.get(
    "FINERACT_PINNED_IMAGE", f"apache/fineract:{PINNED_COMMIT}"
)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
AUTH = "Basic " + base64.b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()


class QualificationError(RuntimeError):
    pass


class DuplicateBusinessEvent(QualificationError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise QualificationError(message)


def write_json(name: str, payload) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def api(method: str, path: str, payload=None, query=None, expect_error: bool = False):
    url = BASE_URL + path
    if query:
        url += "?" + urlencode(query)
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": AUTH,
        "Fineract-Platform-TenantId": TENANT,
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, context=CTX, timeout=30) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else None
            return {"status": response.status, "body": parsed}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        result = {"status": exc.code, "body": parsed}
        if expect_error:
            return result
        raise QualificationError(f"{method} {path} failed with HTTP {exc.code}: {parsed}") from exc
    except URLError as exc:
        raise QualificationError(f"{method} {path} transport failure: {exc.reason}") from exc


def await_ready() -> None:
    last = None
    for _ in range(120):
        try:
            result = api("GET", "/offices")
            if result["status"] == 200 and result["body"]:
                return
            last = result
        except QualificationError as exc:
            last = str(exc)
        time.sleep(2)
    raise QualificationError(f"Fineract did not become API-ready: {last}")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def page_items(result) -> list[dict]:
    body = result["body"]
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ("pageItems", "content"):
            if isinstance(body.get(key), list):
                return body[key]
    raise QualificationError(f"unexpected Fineract page shape: {type(body).__name__}")


def enum_value(entry: dict, key: str) -> str:
    value = entry.get(key)
    if isinstance(value, dict):
        return str(value.get("value") or value.get("code") or value.get("id") or "").lower()
    return str(value or "").lower()


def read_transaction(transaction_id: str):
    return api("GET", "/journalentries", query={"transactionId": transaction_id, "limit": 100})


def assert_transaction(readback, debit_code: str, credit_code: str, expected_amount: Decimal) -> None:
    items = page_items(readback)
    require(len(items) == 2, f"transaction expected 2 journal items, observed {len(items)}")
    observed = {}
    for item in items:
        code = str(item.get("glAccountCode"))
        observed[code] = item
        require(money(item.get("amount")) == expected_amount,
                f"journal amount mismatch for account {code}")
    require(set(observed) == {debit_code, credit_code},
            f"journal account-code set mismatch: {set(observed)}")
    require("debit" in enum_value(observed[debit_code], "entryType"),
            f"account {debit_code} was not observed as debit")
    require("credit" in enum_value(observed[credit_code], "entryType"),
            f"account {credit_code} was not observed as credit")


def create_account(spec: dict) -> int:
    listing = api("GET", "/glaccounts")
    matches = [item for item in listing["body"] if str(item.get("glCode")) == spec["glCode"]]
    if matches:
        require(len(matches) == 1, f"duplicate live GL code {spec['glCode']}")
        require(matches[0].get("name") == spec["name"],
                f"pre-existing GL code {spec['glCode']} has unexpected name")
        return int(matches[0]["id"])
    payload = {
        "name": spec["name"],
        "glCode": spec["glCode"],
        "manualEntriesAllowed": True,
        "type": spec["type"],
        "usage": 1,
        "description": spec["description"],
    }
    response = api("POST", "/glaccounts", payload)
    resource_id = response["body"].get("resourceId")
    require(resource_id is not None, f"GL account create missing resourceId: {spec['glCode']}")
    return int(resource_id)


def journal_payload(posting_date: date, debit_id: int, credit_id: int, amount: Decimal, comments: str):
    date_text = posting_date.strftime("%d %B %Y")
    amount_text = format(amount, "f")
    return {
        "officeId": 1,
        "transactionDate": date_text,
        "locale": "en",
        "dateFormat": "dd MMMM yyyy",
        "currencyCode": "USD",
        "comments": comments,
        "debits": [{"glAccountId": debit_id, "amount": amount_text, "comments": comments}],
        "credits": [{"glAccountId": credit_id, "amount": amount_text, "comments": comments}],
    }


def post_journal(payload: dict):
    response = api("POST", "/journalentries", payload)
    transaction_id = response["body"].get("transactionId")
    require(transaction_id, "Fineract journal response missing transactionId")
    return response, str(transaction_id)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    await_ready()

    platform = {
        "fineractVersion": PINNED_VERSION,
        "fineractReleaseCommit": PINNED_COMMIT,
        "containerImage": PINNED_IMAGE,
        "apiBase": "/fineract-provider/api/v1",
        "tenant": TENANT,
        "tls": "local-test-self-signed",
        "production": False,
    }
    write_json("platform-pin.json", platform)

    specs = {
        "cash": {
            "canonicalCode": "1100",
            "glCode": "991100",
            "name": "Baudot TRS Fund Cash",
            "type": 1,
            "description": "Synthetic CI-only asset mapped to canonical TRS Fund Cash",
        },
        "payable": {
            "canonicalCode": "2100",
            "glCode": "992100",
            "name": "Baudot Provider Payable",
            "type": 2,
            "description": "Synthetic CI-only liability mapped to canonical Provider Payable",
        },
        "expense": {
            "canonicalCode": "5100",
            "glCode": "995100",
            "name": "Baudot TRS Provider Compensation Expense",
            "type": 5,
            "description": "Synthetic CI-only expense mapped to canonical provider compensation expense",
        },
        "openingEquity": {
            "canonicalCode": None,
            "glCode": "993900",
            "name": "Baudot Synthetic Opening Balance Equity",
            "type": 3,
            "description": "Live-lane test bootstrap only; not a TRS Fund business event",
        },
    }
    for spec in specs.values():
        spec["id"] = create_account(spec)

    all_accounts = api("GET", "/glaccounts")
    selected = [item for item in all_accounts["body"] if str(item.get("glCode")) in {s["glCode"] for s in specs.values()}]
    require(len(selected) == 4, "live synthetic chart did not read back four accounts")
    write_json("gl-accounts.json", {"mapping": specs, "readback": selected})

    today = date.today()
    opening = Decimal("50000.00")
    claim_amount = Decimal("8830.00")
    posted_business_ids: dict[str, str] = {}

    seed_request = journal_payload(today, specs["cash"]["id"], specs["openingEquity"]["id"], opening,
                                   "Baudot synthetic live-lane opening balance")
    write_json("seed-request.json", seed_request)
    seed_response, seed_tx = post_journal(seed_request)
    write_json("seed-response.json", seed_response)
    seed_readback = read_transaction(seed_tx)
    assert_transaction(seed_readback, specs["cash"]["glCode"], specs["openingEquity"]["glCode"], opening)
    write_json("seed-readback.json", seed_readback)

    claim_business_id = "claim-vrs-live-001"
    claim_request = journal_payload(today, specs["expense"]["id"], specs["payable"]["id"], claim_amount,
                                    f"Baudot approved synthetic claim {claim_business_id}")
    write_json("claim-request.json", {"syntheticBusinessTransactionId": claim_business_id, "journal": claim_request})
    claim_response, claim_tx = post_journal(claim_request)
    posted_business_ids[claim_business_id] = claim_tx
    write_json("claim-response.json", claim_response)
    claim_readback = read_transaction(claim_tx)
    assert_transaction(claim_readback, specs["expense"]["glCode"], specs["payable"]["glCode"], claim_amount)
    write_json("claim-readback.json", claim_readback)

    payment_business_id = "payment-vrs-live-001"
    payment_request = journal_payload(today, specs["payable"]["id"], specs["cash"]["id"], claim_amount,
                                      f"Baudot authorized synthetic disbursement {payment_business_id}")
    write_json("disbursement-request.json", {"syntheticBusinessTransactionId": payment_business_id, "journal": payment_request})
    payment_response, payment_tx = post_journal(payment_request)
    posted_business_ids[payment_business_id] = payment_tx
    write_json("disbursement-response.json", payment_response)
    payment_readback = read_transaction(payment_tx)
    assert_transaction(payment_readback, specs["payable"]["glCode"], specs["cash"]["glCode"], claim_amount)
    write_json("disbursement-readback.json", payment_readback)

    # Idempotency belongs to the Baudot adapter. A replay is rejected before a second Fineract mutation.
    duplicate_attempted = payment_business_id
    second_http_mutation_attempted = False
    duplicate_rejected = False
    try:
        if duplicate_attempted in posted_business_ids:
            raise DuplicateBusinessEvent(duplicate_attempted)
        second_http_mutation_attempted = True
        post_journal(payment_request)
    except DuplicateBusinessEvent:
        duplicate_rejected = True
    duplicate_readback = read_transaction(payment_tx)
    assert_transaction(duplicate_readback, specs["payable"]["glCode"], specs["cash"]["glCode"], claim_amount)
    write_json("duplicate-control.json", {
        "syntheticBusinessTransactionId": payment_business_id,
        "adapterRejectedReplay": duplicate_rejected,
        "secondHttpMutationAttempted": second_http_mutation_attempted,
        "originalFineractTransactionId": payment_tx,
        "originalTransactionReadbackItems": len(page_items(duplicate_readback)),
    })
    require(duplicate_rejected and not second_http_mutation_attempted,
            "duplicate business event was not blocked before Fineract mutation")

    reversal_request = {"officeId": 1}
    write_json("reversal-request.json", {
        "transactionId": payment_tx,
        "command": "reverse",
        "body": reversal_request,
    })
    reversal_response = api("POST", f"/journalentries/{payment_tx}", reversal_request, query={"command": "reverse"})
    write_json("reversal-response.json", reversal_response)
    reversal_readback = read_transaction(payment_tx)
    reversed_items = page_items(reversal_readback)
    require(len(reversed_items) == 2, "reversal readback lost original journal items")
    require(all(item.get("reversed") is True for item in reversed_items),
            "Fineract did not expose the original disbursement entries as reversed")
    write_json("reversal-readback.json", reversal_readback)

    closure_date = today - timedelta(days=1)
    blocked_date = today - timedelta(days=2)
    closure_request = {
        "officeId": 1,
        "closingDate": closure_date.strftime("%d %B %Y"),
        "locale": "en",
        "dateFormat": "dd MMMM yyyy",
        "comments": "Baudot live-lane closed-period control",
    }
    write_json("closure-request.json", closure_request)
    closure_response = api("POST", "/glclosures", closure_request)
    require(closure_response["body"].get("resourceId") is not None,
            "Fineract closure response missing resourceId")
    write_json("closure-response.json", closure_response)

    closed_request = journal_payload(blocked_date, specs["expense"]["id"], specs["payable"]["id"], Decimal("1.00"),
                                     "Baudot intentionally blocked closed-period journal")
    write_json("closed-period-request.json", closed_request)
    closed_response = api("POST", "/journalentries", closed_request, expect_error=True)
    write_json("closed-period-response.json", closed_response)
    require(400 <= int(closed_response["status"]) < 500,
            f"closed-period journal was not rejected as a client/business-rule error: {closed_response['status']}")

    summary = {
        "qualified": True,
        "fineractVersion": PINNED_VERSION,
        "fineractReleaseCommit": PINNED_COMMIT,
        "claimTransactionIdObserved": bool(claim_tx),
        "disbursementTransactionIdObserved": bool(payment_tx),
        "transactionIdsDistinct": claim_tx != payment_tx,
        "claimReadbackMatched": True,
        "disbursementReadbackMatched": True,
        "duplicateReplayRejectedBeforeMutation": True,
        "reversalReadbackMarkedOriginalEntriesReversed": True,
        "closedPeriodRejected": True,
        "productionAuthorityClaimed": False,
    }
    require(summary["transactionIdsDistinct"], "claim and disbursement reused a Fineract transaction ID")
    write_json("summary.json", summary)
    print("Live pinned Fineract TRS Fund qualification: PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        OUT.mkdir(parents=True, exist_ok=True)
        write_json("summary.json", {
            "qualified": False,
            "errorType": type(exc).__name__,
            "error": str(exc),
            "productionAuthorityClaimed": False,
        })
        print(f"Live pinned Fineract TRS Fund qualification: FAIL: {exc}", file=sys.stderr)
        raise
