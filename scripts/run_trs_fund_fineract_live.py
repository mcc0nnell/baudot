#!/usr/bin/env python3
"""Exercise canonical synthetic TRS Fund journal intents against live Fineract.

Baudot owns the synthetic business decisions and independent reconciliation.
Fineract is an external general-ledger implementation under test. A successful
ledger post never creates provider eligibility, contributor liability, payment
authorization, routing authority, or accessibility readiness.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "interop" / "fineract" / "journal-contract-v1.json"
DEFAULT_PROFILE = ROOT / "interop" / "fineract" / "fineract-live-profile-v1.json"
MONEY = Decimal("0.01")

ACCOUNT_TYPE = {
    "ASSET": 1,
    "LIABILITY": 2,
    "EQUITY": 3,
    "INCOME": 4,
    "EXPENSE": 5,
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def money_text(value: Any) -> str:
    return f"{money(value):.2f}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def page_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("pageItems", "content", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise ValueError("unexpected Fineract list response shape")


def enum_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(str(v) for v in value.values()).lower()
    return str(value).lower()


def enum_id(value: Any) -> int:
    if isinstance(value, dict):
        require(value.get("id") is not None, "enum object missing id")
        return int(value["id"])
    return int(value)


class ApiFailure(RuntimeError):
    def __init__(self, status: int, body: Any):
        super().__init__(f"Fineract HTTP {status}: {body}")
        self.status = status
        self.body = body


class Fineract:
    def __init__(self, base_url: str, tenant: str, username: str, password: str):
        parsed = urllib.parse.urlparse(base_url)
        require(parsed.scheme == "https", "live Fineract profile must use HTTPS")
        require(parsed.hostname in {"localhost", "127.0.0.1"},
                "live Fineract adapter is loopback-only")
        self.base_url = base_url.rstrip("/")
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        self.headers = {
            "Authorization": f"Basic {token}",
            "Fineract-Platform-TenantId": tenant,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self.ssl_context = ssl._create_unverified_context()
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        expect_failure: bool = False,
    ) -> tuple[int, Any]:
        encoded = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=encoded,
            headers=self.headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, context=self.ssl_context, timeout=30) as response:
                status = response.status
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8")

        try:
            payload: Any = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw}

        self.calls.append({
            "method": method,
            "path": path,
            "status": status,
            "requestBody": body,
            "responseBody": payload,
        })

        if expect_failure:
            require(status >= 400, f"expected Fineract request to fail: {method} {path}")
            return status, payload
        if status >= 400:
            raise ApiFailure(status, payload)
        return status, payload


def validate_inputs(
    profile: dict[str, Any],
    contract: dict[str, Any],
    scenario: dict[str, Any],
) -> None:
    require(profile.get("schema") == "baudot.fineract-live-profile@1", "unexpected live profile")
    require(profile.get("status") == "experimental", "live profile must remain experimental")
    require(profile["source"]["repository"] == "apache/fineract", "unexpected upstream repository")
    require(profile["source"]["releaseTag"] == "1.15.0", "unexpected Fineract release")
    require(
        profile["source"]["commit"] == "d5636847ac556c30b437254c353f05526d172b97",
        "Fineract source commit drift",
    )
    require(profile["claimBoundary"].get("testContainerOnly") is True,
            "live profile must remain test-container-only")
    require(contract.get("schema") == "baudot.fineract-trs-journal-contract@1",
            "unexpected journal contract")
    expected_reversal = "/api/v1/journalentries/{transactionId}?command=reverse"
    require(contract["fineractApiSurface"]["reversal"] == expected_reversal,
            "journal contract reversal path is not aligned with Fineract 1.15.0")
    require(profile["apiSurface"]["journalReversal"] == expected_reversal,
            "live profile reversal path drift")
    require(scenario.get("schema") == "baudot.trs-fund-scenario-evidence@1",
            "unexpected scenario evidence")
    require(scenario["scenarioId"] == profile["expected"]["scenarioId"],
            "unexpected scenario ID")
    require(scenario["reconciliation"].get("fineractPosted") is False,
            "source scenario must not pre-claim Fineract posting")
    require(len(scenario["journalIntents"]) == profile["expected"]["journalIntentCount"],
            "unexpected journal intent count")


def ensure_accounts(api: Fineract, contract: dict[str, Any]) -> dict[str, int]:
    _, existing_payload = api.request("GET", "/glaccounts")
    existing = page_items(existing_payload)
    by_code = {str(item.get("glCode")): item for item in existing if item.get("glCode") is not None}
    result: dict[str, int] = {}

    for code, spec in contract["accounts"].items():
        if code in by_code:
            item = by_code[code]
            require(item.get("name") == spec["name"], f"existing GL code {code} has unexpected name")
            require(enum_id(item.get("type")) == ACCOUNT_TYPE[spec["type"]],
                    f"existing GL code {code} has unexpected type")
            require(item.get("manualEntriesAllowed") is True,
                    f"existing GL code {code} disallows manual entries")
            result[code] = int(item["id"])
            continue

        request = {
            "name": spec["name"],
            "glCode": code,
            "type": ACCOUNT_TYPE[spec["type"]],
            "usage": 1,
            "manualEntriesAllowed": True,
            "description": "Baudot synthetic TRS Fund proving-ground account",
        }
        _, created = api.request("POST", "/glaccounts", request)
        resource_id = created.get("resourceId")
        require(resource_id is not None, f"Fineract did not return resourceId for GL {code}")
        result[code] = int(resource_id)

    require(len(result) == len(contract["accounts"]), "canonical chart creation incomplete")
    return result


def make_journal_request(
    intent: dict[str, Any],
    accounts: dict[str, int],
    office_id: int,
    currency_code: str,
) -> dict[str, Any]:
    amount = money_text(intent["amount"])
    key = intent["syntheticBusinessTransactionId"]
    return {
        "officeId": office_id,
        "transactionDate": intent["postingDate"],
        "currencyCode": currency_code,
        "locale": "en",
        "dateFormat": "uuuu-MM-dd",
        "referenceNumber": key,
        "comments": f"Baudot synthetic Fund event {intent['eventType']}",
        "debits": [{
            "glAccountId": accounts[intent["debit"]["accountCode"]],
            "amount": amount,
            "comments": key,
        }],
        "credits": [{
            "glAccountId": accounts[intent["credit"]["accountCode"]],
            "amount": amount,
            "comments": key,
        }],
    }


def read_transaction(api: Fineract, transaction_id: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({
        "transactionId": transaction_id,
        "manualEntriesOnly": "true",
        "limit": "20",
    })
    _, payload = api.request("GET", f"/journalentries?{query}")
    items = page_items(payload)
    require(items, f"no journal entries returned for {transaction_id}")
    return items


def reconcile_transaction(intent: dict[str, Any], entries: list[dict[str, Any]]) -> dict[str, Any]:
    require(len(entries) == 2, "expected exactly two journal entries")
    txid = entries[0].get("transactionId")
    require(txid, "journal readback missing transaction ID")
    require(all(item.get("transactionId") == txid for item in entries),
            "journal readback contains mixed transaction IDs")
    amount = money(intent["amount"])
    debit_code = intent["debit"]["accountCode"]
    credit_code = intent["credit"]["accountCode"]

    debit_matches = [
        item for item in entries
        if str(item.get("glAccountCode")) == debit_code and "debit" in enum_text(item.get("entryType"))
    ]
    credit_matches = [
        item for item in entries
        if str(item.get("glAccountCode")) == credit_code and "credit" in enum_text(item.get("entryType"))
    ]
    require(len(debit_matches) == 1, f"expected one debit for {debit_code}")
    require(len(credit_matches) == 1, f"expected one credit for {credit_code}")
    require(money(debit_matches[0]["amount"]) == amount, "debit amount mismatch")
    require(money(credit_matches[0]["amount"]) == amount, "credit amount mismatch")

    ids = sorted(int(item["id"]) for item in entries if item.get("id") is not None)
    require(len(ids) == 2, "expected two journal entry IDs")
    return {
        "transactionId": str(txid),
        "journalEntryIds": ids,
        "balanced": True,
        "readbackMatched": True,
    }


def scenario_balances(posts: list[dict[str, Any]], contract: dict[str, Any]) -> dict[str, str]:
    debits: dict[str, Decimal] = {code: Decimal("0.00") for code in contract["accounts"]}
    credits: dict[str, Decimal] = {code: Decimal("0.00") for code in contract["accounts"]}

    for post in posts:
        for entry in post["entries"]:
            code = str(entry["glAccountCode"])
            require(code in contract["accounts"], f"unexpected GL code in readback: {code}")
            amount = money(entry["amount"])
            kind = enum_text(entry.get("entryType"))
            if "debit" in kind:
                debits[code] += amount
            elif "credit" in kind:
                credits[code] += amount
            else:
                raise ValueError(f"unclassified journal entry type for GL {code}")

    values: dict[str, str] = {}
    for code, spec in contract["accounts"].items():
        if spec["type"] in {"ASSET", "EXPENSE"}:
            value = debits[code] - credits[code]
        else:
            value = credits[code] - debits[code]
        values[code] = money_text(value)
    return values


def verify_scenario_state(balances: dict[str, str], scenario: dict[str, Any]) -> dict[str, Any]:
    expected = scenario["finalState"]
    mapping = {
        "1100": "cash",
        "1200": "contributorReceivable",
        "2100": "providerPayable",
        "4100": "contributionRevenue",
        "5100": "providerCompensationExpense",
    }
    for code, state_name in mapping.items():
        require(balances[code] == money_text(expected[state_name]),
                f"Fineract readback balance mismatch for {code}/{state_name}")
    return {
        "matched": True,
        "balancesByGlCode": balances,
        "scenarioState": expected,
    }


def opposite(kind: str) -> str:
    return "credit" if kind == "debit" else "debit"


def verify_reversal(original: list[dict[str, Any]], reversal: list[dict[str, Any]]) -> dict[str, Any]:
    require(len(original) == 2 and len(reversal) == 2, "unexpected reversal entry count")
    require(all(item.get("reversed") is True for item in original),
            "original journal entries were not marked reversed")
    original_by_code = {str(item["glAccountCode"]): item for item in original}
    reversal_by_code = {str(item["glAccountCode"]): item for item in reversal}
    require(original_by_code.keys() == reversal_by_code.keys(),
            "reversal GL account set differs from original")

    for code, original_entry in original_by_code.items():
        reversal_entry = reversal_by_code[code]
        original_kind = "debit" if "debit" in enum_text(original_entry.get("entryType")) else "credit"
        reversal_kind = "debit" if "debit" in enum_text(reversal_entry.get("entryType")) else "credit"
        require(reversal_kind == opposite(original_kind), f"reversal entry type mismatch for GL {code}")
        require(money(reversal_entry["amount"]) == money(original_entry["amount"]),
                f"reversal amount mismatch for GL {code}")
        require(reversal_entry.get("transactionDate") == original_entry.get("transactionDate"),
                f"reversal date mismatch for GL {code}")

    return {
        "originalMarkedReversed": True,
        "oppositeEntriesMatched": True,
        "originalTransactionId": str(original[0]["transactionId"]),
        "reversalTransactionId": str(reversal[0]["transactionId"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario-evidence", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()

    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    scenario = json.loads(args.scenario_evidence.read_text(encoding="utf-8"))
    validate_inputs(profile, contract, scenario)

    username = os.getenv("FINERACT_TEST_USERNAME", "mifos")
    password = os.getenv("FINERACT_TEST_PASSWORD", "password")
    api = Fineract(profile["baseUrl"], profile["tenant"], username, password)

    accounts = ensure_accounts(api, contract)
    posted: dict[str, dict[str, Any]] = {}
    posts: list[dict[str, Any]] = []

    def post_intent(intent: dict[str, Any]) -> dict[str, Any]:
        key = intent["syntheticBusinessTransactionId"]
        if key in posted:
            return {
                "syntheticBusinessTransactionId": key,
                "applied": False,
                "reason": "baudot-adapter-idempotent-replay",
                "transactionId": posted[key]["transactionId"],
            }

        request = make_journal_request(
            intent,
            accounts,
            int(profile["officeId"]),
            profile["currencyCode"],
        )
        _, response = api.request("POST", "/journalentries", request)
        transaction_id = response.get("transactionId")
        require(transaction_id, f"Fineract did not return transactionId for {key}")
        entries = read_transaction(api, str(transaction_id))
        reconciliation = reconcile_transaction(intent, entries)
        record = {
            "intent": intent,
            "request": request,
            "response": response,
            "entries": entries,
            **reconciliation,
        }
        posted[key] = record
        posts.append(record)
        return {
            "syntheticBusinessTransactionId": key,
            "applied": True,
            "transactionId": str(transaction_id),
        }

    first_pass = [post_intent(intent) for intent in scenario["journalIntents"]]
    require(all(item["applied"] for item in first_pass), "first journal pass was not fully applied")

    calls_before_replay = len(api.calls)
    replay = post_intent(scenario["journalIntents"][0])
    calls_after_replay = len(api.calls)
    require(replay["applied"] is False, "adapter replay was unexpectedly posted")
    require(calls_before_replay == calls_after_replay,
            "adapter idempotency replay reached Fineract")

    balances = scenario_balances(posts, contract)
    pre_reversal = verify_scenario_state(balances, scenario)

    claim_key = next(
        intent["syntheticBusinessTransactionId"]
        for intent in scenario["journalIntents"]
        if intent["eventType"] == "providerClaimApproved"
    )
    claim_tx = posted[claim_key]["transactionId"]
    reversal_path = contract["fineractApiSurface"]["reversal"].replace(
        "/api/v1", "", 1
    ).replace("{transactionId}", claim_tx)
    _, reversal_response = api.request(
        "POST",
        reversal_path,
        {"comments": "Baudot synthetic reversal evidence probe"},
    )
    reversal_tx = reversal_response.get("transactionId")
    require(reversal_tx, "Fineract reversal did not return transactionId")
    claim_original_after = read_transaction(api, claim_tx)
    reversal_entries = read_transaction(api, str(reversal_tx))
    reversal_result = verify_reversal(claim_original_after, reversal_entries)

    closure_date = profile["expected"]["closureDate"]
    _, closure_response = api.request(
        "POST",
        "/glclosures",
        {
            "officeId": int(profile["officeId"]),
            "closingDate": closure_date,
            "comments": "Baudot synthetic closed-period negative control",
            "locale": "en",
            "dateFormat": "uuuu-MM-dd",
        },
    )
    require(closure_response.get("resourceId") is not None,
            "Fineract closure did not return resourceId")

    late_request = {
        "officeId": int(profile["officeId"]),
        "transactionDate": closure_date,
        "currencyCode": profile["currencyCode"],
        "locale": "en",
        "dateFormat": "uuuu-MM-dd",
        "referenceNumber": "baudot-closed-period-negative",
        "comments": "Expected rejection: posting date is accounting-closed",
        "debits": [{"glAccountId": accounts["1100"], "amount": "1.00"}],
        "credits": [{"glAccountId": accounts["4100"], "amount": "1.00"}],
    }
    late_status, late_body = api.request(
        "POST",
        "/journalentries",
        late_request,
        expect_failure=True,
    )

    payment_key = next(
        intent["syntheticBusinessTransactionId"]
        for intent in scenario["journalIntents"]
        if intent["eventType"] == "providerDisbursement"
    )
    payment_tx = posted[payment_key]["transactionId"]
    closed_reversal_path = contract["fineractApiSurface"]["reversal"].replace(
        "/api/v1", "", 1
    ).replace("{transactionId}", payment_tx)
    reverse_status, reverse_body = api.request(
        "POST",
        closed_reversal_path,
        {"comments": "Expected rejection: reversal date is accounting-closed"},
        expect_failure=True,
    )

    evidence = {
        "schema": "baudot.trs-fund-fineract-live-evidence@1",
        "source": profile["source"],
        "profileSha256": sha256_file(args.profile),
        "journalContractSha256": sha256_file(args.contract),
        "scenarioEvidenceSha256": sha256_file(args.scenario_evidence),
        "scenarioId": scenario["scenarioId"],
        "authorityBindings": {
            "businessDecisionSource": "baudot.trs-fund-scenario-evidence@1",
            "journalVocabularySource": contract["schema"],
            "ledgerImplementation": "Apache Fineract 1.15.0",
            "fineractOwnsProgramAuthorization": False,
        },
        "chart": {
            "accountsByGlCode": accounts,
            "canonicalAccountCount": len(accounts),
        },
        "journalPosts": posts,
        "adapterIdempotency": {
            "replayApplied": replay["applied"],
            "replayReason": replay["reason"],
            "transactionIdStable": replay["transactionId"] == posts[0]["transactionId"],
            "fineractCallCountUnchanged": calls_before_replay == calls_after_replay,
        },
        "preReversalScenarioReconciliation": pre_reversal,
        "reversal": {
            **reversal_result,
            "response": reversal_response,
            "entries": reversal_entries,
        },
        "accountingClosure": {
            "closingDate": closure_date,
            "resourceId": closure_response["resourceId"],
            "response": closure_response,
        },
        "closedPeriodControls": {
            "newPostingRejected": late_status >= 400,
            "newPostingStatus": late_status,
            "newPostingResponse": late_body,
            "reversalRejected": reverse_status >= 400,
            "reversalStatus": reverse_status,
            "reversalResponse": reverse_body,
        },
        "apiCalls": api.calls,
        "claimBoundary": {
            "syntheticOnly": True,
            "liveFineractExecution": True,
            "fineractConformanceProven": False,
            "providerEligibilityProven": False,
            "contributorLiabilityProven": False,
            "fccPaymentAuthorizationProven": False,
            "productionAdministratorCompatibilityProven": False,
            "productionPaymentRailProven": False,
            "routingAuthorityProven": False,
            "accessibilityReadinessProven": False,
        },
    }

    require(evidence["adapterIdempotency"]["fineractCallCountUnchanged"],
            "adapter idempotency invariant failed")
    require(evidence["preReversalScenarioReconciliation"]["matched"],
            "scenario reconciliation invariant failed")
    require(evidence["closedPeriodControls"]["newPostingRejected"],
            "closed-period post was not rejected")
    require(evidence["closedPeriodControls"]["reversalRejected"],
            "closed-period reversal was not rejected")

    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "scenarioId": scenario["scenarioId"],
        "journalTransactions": [item["transactionId"] for item in posts],
        "reversalTransactionId": str(reversal_tx),
        "closureId": closure_response["resourceId"],
        "closedPeriodPostStatus": late_status,
        "closedPeriodReversalStatus": reverse_status,
    }, indent=2, sort_keys=True))
    print("TRS Fund live Fineract loop: PASS")


if __name__ == "__main__":
    main()
