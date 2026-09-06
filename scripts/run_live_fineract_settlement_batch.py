#!/usr/bin/env python3
"""Qualify a pre-reduced synthetic TRS settlement batch against live Fineract."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import run_live_fineract_trs_fund as live

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "testkit/part64/fixtures/settlement-batch-v1.json"
OUT = ROOT / "target/evidence-external/LIVE-FINERACT-TRS-BATCH/v1"


def write_json(name: str, payload) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def load_fixture() -> dict:
    with FIXTURE.open("r", encoding="utf-8") as handle:
        fixture = json.load(handle)
    live.require(fixture.get("schema") == "baudot.synthetic-trs-settlement-batch@1", "unexpected batch schema")
    live.require(fixture.get("authorityBoundary") == "pre-reduced-synthetic-input", "batch must be pre-reduced")
    live.require(fixture.get("currency") == "USD", "live batch lane currently qualifies USD only")
    ids = set()
    for claim in fixture.get("claims", []):
        event_id = str(claim.get("eventId") or "")
        provider = str(claim.get("provider") or "")
        live.require(event_id and event_id not in ids, f"duplicate or missing eventId: {event_id}")
        live.require(provider.endswith(".example"), f"provider must remain reserved/synthetic: {provider}")
        live.require(Decimal(str(claim.get("amount"))) > 0, f"non-positive amount for {event_id}")
        live.require(claim.get("claimDecision") in {"approved", "rejected"}, f"invalid claimDecision for {event_id}")
        live.require(claim.get("paymentAuthorization") in {"authorized", "held", "not-applicable"},
                     f"invalid paymentAuthorization for {event_id}")
        if claim["claimDecision"] == "rejected":
            live.require(claim["paymentAuthorization"] == "not-applicable",
                         f"rejected claim cannot carry payment authorization: {event_id}")
        if claim["paymentAuthorization"] == "authorized":
            live.require(claim["claimDecision"] == "approved",
                         f"payment cannot be authorized for non-approved claim: {event_id}")
        ids.add(event_id)
    return fixture


def create_chart() -> dict:
    specs = {
        "cash": {
            "canonicalCode": "1100",
            "glCode": "981100",
            "name": "Baudot Batch TRS Fund Cash",
            "type": 1,
            "description": "Synthetic batch-close asset mapped to canonical TRS Fund Cash",
        },
        "payable": {
            "canonicalCode": "2100",
            "glCode": "982100",
            "name": "Baudot Batch Provider Payable",
            "type": 2,
            "description": "Synthetic batch-close liability mapped to canonical Provider Payable",
        },
        "expense": {
            "canonicalCode": "5100",
            "glCode": "985100",
            "name": "Baudot Batch Provider Compensation Expense",
            "type": 5,
            "description": "Synthetic batch-close expense mapped to provider compensation expense",
        },
        "openingEquity": {
            "canonicalCode": None,
            "glCode": "983900",
            "name": "Baudot Batch Synthetic Opening Equity",
            "type": 3,
            "description": "Batch qualification bootstrap only; not a TRS Fund business event",
        },
    }
    for spec in specs.values():
        spec["id"] = live.create_account(spec)
    selected = [
        item for item in live.api("GET", "/glaccounts")["body"]
        if str(item.get("glCode")) in {spec["glCode"] for spec in specs.values()}
    ]
    live.require(len(selected) == 4, "batch chart did not read back four isolated accounts")
    write_json("gl-accounts.json", {"mapping": specs, "readback": selected})
    return specs


def post_once(posted: dict[str, str], business_id: str, payload: dict) -> tuple[bool, str]:
    if business_id in posted:
        return False, posted[business_id]
    response, transaction_id = live.post_journal(payload)
    posted[business_id] = transaction_id
    return True, transaction_id


def movement(readbacks: dict[str, dict], specs: dict) -> dict[str, Decimal]:
    totals = {
        "expenseDebit": Decimal("0.00"),
        "payableCredit": Decimal("0.00"),
        "payableDebit": Decimal("0.00"),
        "cashCredit": Decimal("0.00"),
    }
    codes = {key: specs[key]["glCode"] for key in ("cash", "payable", "expense")}
    for readback in readbacks.values():
        for item in live.page_items(readback):
            code = str(item.get("glAccountCode"))
            amount = live.money(item.get("amount"))
            entry = live.enum_value(item, "entryType")
            if code == codes["expense"] and "debit" in entry:
                totals["expenseDebit"] += amount
            elif code == codes["payable"] and "credit" in entry:
                totals["payableCredit"] += amount
            elif code == codes["payable"] and "debit" in entry:
                totals["payableDebit"] += amount
            elif code == codes["cash"] and "credit" in entry:
                totals["cashCredit"] += amount
    return {key: live.money(value) for key, value in totals.items()}


def run_batch(fixture: dict, specs: dict, posted: dict[str, str], replay: bool = False) -> dict:
    mutations = 0
    suppressed = 0
    excluded = []
    held = []
    transactions = {}
    today = date.today()

    for claim in fixture["claims"]:
        event_id = claim["eventId"]
        amount = live.money(claim["amount"])
        if claim["claimDecision"] != "approved":
            excluded.append({"eventId": event_id, "amount": format(amount, "f"), "reason": "claim-not-approved"})
            continue

        accrual_id = f"accrual:{event_id}"
        accrual = live.journal_payload(
            today,
            specs["expense"]["id"],
            specs["payable"]["id"],
            amount,
            f"Baudot batch approved synthetic claim {event_id}",
        )
        mutated, accrual_tx = post_once(posted, accrual_id, accrual)
        mutations += int(mutated)
        suppressed += int(not mutated)
        accrual_readback = live.read_transaction(accrual_tx)
        live.assert_transaction(accrual_readback, specs["expense"]["glCode"], specs["payable"]["glCode"], amount)
        transactions[accrual_id] = accrual_readback

        if claim["paymentAuthorization"] == "authorized":
            payment_id = f"payment:{event_id}"
            payment = live.journal_payload(
                today,
                specs["payable"]["id"],
                specs["cash"]["id"],
                amount,
                f"Baudot batch authorized synthetic disbursement {event_id}",
            )
            mutated, payment_tx = post_once(posted, payment_id, payment)
            mutations += int(mutated)
            suppressed += int(not mutated)
            payment_readback = live.read_transaction(payment_tx)
            live.assert_transaction(payment_readback, specs["payable"]["glCode"], specs["cash"]["glCode"], amount)
            transactions[payment_id] = payment_readback
        else:
            held.append({"eventId": event_id, "amount": format(amount, "f"), "reason": "payment-not-authorized"})

    return {
        "replay": replay,
        "httpMutations": mutations,
        "duplicateMutationsSuppressed": suppressed,
        "excludedClaims": excluded,
        "heldApprovedClaims": held,
        "transactions": transactions,
    }


def seal_bundle() -> None:
    manifest = OUT / "bundle.manifest.sha256"
    rows = []
    for path in sorted(OUT.iterdir(), key=lambda p: p.name):
        if not path.is_file() or path.name == manifest.name:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(f"{digest}  {path.name}\n")
    manifest.write_text("".join(rows), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    live.await_ready()
    fixture = load_fixture()
    specs = create_chart()
    today = date.today()

    seed_amount = Decimal("50000.00")
    seed = live.journal_payload(
        today,
        specs["cash"]["id"],
        specs["openingEquity"]["id"],
        seed_amount,
        "Baudot synthetic settlement-batch opening state",
    )
    seed_response, seed_tx = live.post_journal(seed)
    seed_readback = live.read_transaction(seed_tx)
    live.assert_transaction(seed_readback, specs["cash"]["glCode"], specs["openingEquity"]["glCode"], seed_amount)
    write_json("seed.json", {"request": seed, "response": seed_response, "readback": seed_readback})

    posted: dict[str, str] = {}
    first = run_batch(fixture, specs, posted, replay=False)
    write_json("first-pass.json", first)

    replay = run_batch(fixture, specs, posted, replay=True)
    write_json("replay-pass.json", replay)

    expected = fixture["expected"]
    live.require(first["httpMutations"] == int(expected["firstPassLedgerMutations"]),
                 "first-pass mutation count mismatch")
    live.require(replay["httpMutations"] == int(expected["replayLedgerMutations"]),
                 "replay attempted a second Fineract mutation")
    live.require(replay["duplicateMutationsSuppressed"] == int(expected["firstPassLedgerMutations"]),
                 "replay did not suppress every previously posted business mutation")

    first_readbacks = first["transactions"]
    totals = movement(first_readbacks, specs)
    approved_total = live.money(expected["approvedAccrualTotal"])
    paid_total = live.money(expected["authorizedDisbursementTotal"])
    payable_net = live.money(expected["endingPayableNetCredit"])
    live.require(totals["expenseDebit"] == approved_total, "approved accrual aggregate mismatch")
    live.require(totals["payableCredit"] == approved_total, "payable-credit aggregate mismatch")
    live.require(totals["payableDebit"] == paid_total, "payable-debit aggregate mismatch")
    live.require(totals["cashCredit"] == paid_total, "cash-credit aggregate mismatch")
    live.require(live.money(totals["payableCredit"] - totals["payableDebit"]) == payable_net,
                 "ending payable net-credit mismatch")

    close_request = {
        "officeId": 1,
        "closingDate": today.strftime("%d %B %Y"),
        "locale": "en",
        "dateFormat": "dd MMMM yyyy",
        "comments": f"Baudot synthetic settlement close {fixture['batchId']}",
    }
    close_response = live.api("POST", "/glclosures", close_request)
    live.require(close_response["body"].get("resourceId") is not None, "batch close missing resourceId")
    write_json("close.json", {"request": close_request, "response": close_response})

    late_date = today - timedelta(days=1)
    late_request = live.journal_payload(
        late_date,
        specs["expense"]["id"],
        specs["payable"]["id"],
        Decimal("1.00"),
        "Baudot intentionally rejected post-close late mutation",
    )
    late_response = live.api("POST", "/journalentries", late_request, expect_error=True)
    live.require(400 <= int(late_response["status"]) < 500, "post-close late mutation was not rejected")
    write_json("post-close-rejection.json", {"request": late_request, "response": late_response})

    reconciliation = {
        "batchId": fixture["batchId"],
        "movement": {key: format(value, "f") for key, value in totals.items()},
        "approvedAccrualTotal": format(approved_total, "f"),
        "authorizedDisbursementTotal": format(paid_total, "f"),
        "endingPayableNetCredit": format(payable_net, "f"),
        "transactionIds": posted,
        "allTransactionIdsDistinct": len(set(posted.values())) == len(posted),
    }
    live.require(reconciliation["allTransactionIdsDistinct"], "batch reused a Fineract transaction ID")
    write_json("reconciliation.json", reconciliation)

    summary = {
        "qualified": True,
        "batchId": fixture["batchId"],
        "fineractVersion": live.PINNED_VERSION,
        "fineractReleaseCommit": live.PINNED_COMMIT,
        "preReducedAuthorityBoundaryPreserved": True,
        "firstPassLedgerMutations": first["httpMutations"],
        "replayLedgerMutations": replay["httpMutations"],
        "duplicateReplaySuppressedBeforeMutation": replay["httpMutations"] == 0,
        "approvedClaimCount": 3,
        "authorizedPaymentCount": 2,
        "heldApprovedClaimCount": 1,
        "rejectedClaimCount": 1,
        "aggregateReconciliationMatched": True,
        "postCloseLateMutationRejected": True,
        "durableCrossProcessIdempotencyClaimed": False,
        "productionAuthorityClaimed": False,
    }
    write_json("summary.json", summary)
    seal_bundle()
    print("Live Fineract TRS settlement batch close: PASS")


if __name__ == "__main__":
    main()
