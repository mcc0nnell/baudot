from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import sys
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "interop" / "fineract"))

from fineract_executor import ExecutionLedger, FineractExecutor, JsonResponse, load_contract  # noqa: E402
from testkit.fund.runtime.fund_runtime import FundEvent, fold_events  # noqa: E402


CONTRACT_PATH = ROOT / "interop" / "fineract" / "journal-contract-v1.json"
FIVE_YEAR_PATH = ROOT / "testkit" / "fund" / "runtime" / "five-year-synthetic.json"


class FakeFineractTransport:
    def __init__(self, *, omit_account_code: str | None = None):
        codes = ["1100", "1200", "2100", "4100", "5100", "5200", "5300"]
        self.accounts = {
            code: 100 + index
            for index, code in enumerate(codes, start=1)
            if code != omit_account_code
        }
        self.calls: list[tuple[str, str, Mapping[str, Any] | None, Mapping[str, str]]] = []
        self.rows: list[dict[str, Any]] = []
        self.next_entry_id = 1
        self.next_transaction = 1
        self.next_resource_id = 900
        self.idempotent_responses: dict[str, JsonResponse] = {}

    def request(self, method, path, *, json_body=None, headers=None):
        headers = dict(headers or {})
        self.calls.append((method, path, json_body, headers))
        idem = headers.get("Idempotency-Key")
        if method == "POST" and idem and idem in self.idempotent_responses:
            cached = self.idempotent_responses[idem]
            return JsonResponse(cached.status, cached.body, {"x-served-from-cache": "true"})

        parsed = urlparse(path)
        query = parse_qs(parsed.query)

        if method == "GET" and parsed.path.endswith("/glaccounts"):
            return JsonResponse(
                200,
                [
                    {"id": account_id, "glCode": code, "name": f"Account {code}"}
                    for code, account_id in self.accounts.items()
                ],
            )

        if method == "POST" and parsed.path.endswith("/glaccounts"):
            assert json_body is not None
            code = str(json_body["glCode"])
            resource_id = max(self.accounts.values(), default=100) + 1
            self.accounts[code] = resource_id
            response = JsonResponse(200, {"resourceId": resource_id})
            if idem:
                self.idempotent_responses[idem] = response
            return response

        if method == "POST" and parsed.path.endswith("/glclosures"):
            self.next_resource_id += 1
            response = JsonResponse(200, {"officeId": 1, "resourceId": self.next_resource_id})
            if idem:
                self.idempotent_responses[idem] = response
            return response

        if method == "POST" and parsed.path.endswith("/journalentries"):
            assert json_body is not None
            transaction_id = self._post_lines(json_body["debits"], json_body["credits"])
            response = JsonResponse(200, {"officeId": 1, "transactionId": transaction_id})
            if idem:
                self.idempotent_responses[idem] = response
            return response

        if method == "POST" and "/journalentries/" in parsed.path and query.get("command") == ["reverse"]:
            target_transaction_id = parsed.path.rsplit("/", 1)[-1]
            target_rows = [row for row in self.rows if row["transactionId"] == target_transaction_id]
            if not target_rows:
                raise AssertionError(f"unknown reversal target {target_transaction_id}")
            debits = [
                {"glAccountId": row["glAccountId"], "amount": row["amount"]}
                for row in target_rows
                if row["entryType"]["id"] == 1
            ]
            credits = [
                {"glAccountId": row["glAccountId"], "amount": row["amount"]}
                for row in target_rows
                if row["entryType"]["id"] == 2
            ]
            transaction_id = self._post_lines(debits, credits)
            response = JsonResponse(200, {"transactionId": transaction_id})
            if idem:
                self.idempotent_responses[idem] = response
            return response

        if method == "GET" and parsed.path.endswith("/journalentries"):
            rows = list(self.rows)
            if "transactionId" in query:
                wanted = query["transactionId"][0]
                rows = [row for row in rows if row["transactionId"] == wanted]
            if "glAccountId" in query:
                wanted_id = int(query["glAccountId"][0])
                rows = [row for row in rows if row["glAccountId"] == wanted_id]
            return JsonResponse(200, {"totalFilteredRecords": len(rows), "pageItems": rows})

        raise AssertionError(f"unhandled fake Fineract request: {method} {path}")

    def _post_lines(self, debits, credits):
        transaction_id = f"FJ{self.next_transaction:04d}"
        self.next_transaction += 1
        for side_id, side_name, lines in ((2, "DEBIT", debits), (1, "CREDIT", credits)):
            for line in lines:
                self.rows.append(
                    {
                        "id": self.next_entry_id,
                        "glAccountId": int(line["glAccountId"]),
                        "transactionId": transaction_id,
                        "entryType": {
                            "id": side_id,
                            "code": f"journalEntryType.{side_name.lower()}",
                            "value": side_name,
                        },
                        "amount": str(line["amount"]),
                        "manualEntry": True,
                        "reversed": False,
                    }
                )
                self.next_entry_id += 1
        return transaction_id


def fund_event(seq: int, event_type: str, transaction_id: str, **kwargs) -> FundEvent:
    return FundEvent(
        seq=seq,
        event_type=event_type,  # type: ignore[arg-type]
        transaction_id=transaction_id,
        actor_id=kwargs.pop("actor_id", "fineract-test"),
        effective_date=kwargs.pop("effective_date", "2026-07-01"),
        **kwargs,
    )


def load_five_year_events() -> list[FundEvent]:
    raw = json.loads(FIVE_YEAR_PATH.read_text(encoding="utf-8"))
    events: list[FundEvent] = []
    for item in raw["events"]:
        events.append(
            FundEvent(
                seq=int(item["seq"]),
                event_type=item["eventType"],  # type: ignore[arg-type]
                transaction_id=item["transactionId"],
                actor_id="five-year-synthetic-runner",
                effective_date=item["effectiveDate"],
                amount=Decimal(item.get("amount", "0")),
                entity_id=item.get("entityId"),
                policy_hash=item.get("policyHash"),
                target_transaction_id=item.get("targetTransactionId"),
                adjustment_direction=item.get("adjustmentDirection"),
                note=item.get("note"),
            )
        )
    return events


class FineractExecutorTests(unittest.TestCase):
    def setUp(self):
        self.contract = load_contract(str(CONTRACT_PATH))
        self.transport = FakeFineractTransport()
        self.executor = FineractExecutor(self.transport, self.contract, account_ids=self.transport.accounts)
        self.ledger = ExecutionLedger()

    def test_journal_post_uses_native_fineract_idempotency_and_reconciles(self):
        event = fund_event(
            1,
            "PROVIDER_CLAIM_APPROVED",
            "claim-1",
            entity_id="provider-a",
            amount=Decimal("600.00"),
        )

        record = self.executor.execute_event(event, self.ledger)

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.expected_debit_account, "5100")
        self.assertEqual(record.expected_credit_account, "2100")
        self.assertTrue(record.balanced)
        self.assertTrue(record.reconciled)
        post = next(call for call in self.transport.calls if call[0] == "POST" and call[1] == "/api/v1/journalentries")
        self.assertEqual(post[3]["Idempotency-Key"], "claim-1")
        self.assertEqual(post[2]["referenceNumber"], "claim-1")

    def test_duplicate_executor_delivery_does_not_post_twice(self):
        event = fund_event(
            1,
            "CONTRIBUTOR_ASSESSED",
            "assessment-1",
            entity_id="contributor-a",
            amount=Decimal("100.00"),
        )

        first = self.executor.execute_event(event, self.ledger)
        post_count = len([call for call in self.transport.calls if call[0] == "POST"])
        second = self.executor.execute_event(event, self.ledger)

        self.assertEqual(first, second)
        self.assertEqual(len([call for call in self.transport.calls if call[0] == "POST"]), post_count)

    def test_decrease_adjustment_swaps_debit_and_credit(self):
        adjustment = fund_event(
            1,
            "PROVIDER_CLAIM_ADJUSTED",
            "claim-adjust-down",
            entity_id="provider-a",
            target_transaction_id="claim-original",
            adjustment_direction="decrease",
            amount=Decimal("30.00"),
        )

        plan = self.executor.plan_journal(adjustment)

        self.assertEqual(plan.debit_code, "2100")
        self.assertEqual(plan.credit_code, "5100")

    def test_reversal_uses_target_fineract_transaction_and_reconciles_inverse(self):
        claim = fund_event(
            1,
            "PROVIDER_CLAIM_APPROVED",
            "claim-1",
            entity_id="provider-a",
            amount=Decimal("600.00"),
        )
        claim_record = self.executor.execute_event(claim, self.ledger)
        assert claim_record is not None
        reversal = fund_event(
            2,
            "TRANSACTION_REVERSED",
            "reverse-claim-1",
            target_transaction_id="claim-1",
        )

        record = self.executor.execute_event(reversal, self.ledger)

        assert record is not None
        self.assertTrue(record.reconciled)
        self.assertEqual(record.posting_date, claim_record.posting_date)
        self.assertEqual(record.expected_debit_account, "2100")
        self.assertEqual(record.expected_credit_account, "5100")
        reversal_post = next(
            call
            for call in self.transport.calls
            if call[0] == "POST" and f"/journalentries/{claim_record.fineract_transaction_id}?command=reverse" in call[1]
        )
        self.assertEqual(reversal_post[3]["Idempotency-Key"], "reverse-claim-1")

    def test_reversal_rejects_effective_date_that_fineract_would_ignore(self):
        claim = fund_event(
            1,
            "PROVIDER_CLAIM_APPROVED",
            "claim-1",
            entity_id="provider-a",
            amount=Decimal("600.00"),
            effective_date="2026-07-15",
        )
        self.executor.execute_event(claim, self.ledger)
        reversal = fund_event(
            2,
            "TRANSACTION_REVERSED",
            "reverse-claim-1",
            target_transaction_id="claim-1",
            effective_date="2026-08-01",
        )

        with self.assertRaisesRegex(ValueError, "original journal date"):
            self.executor.execute_event(reversal, self.ledger)

    def test_accounting_closure_posts_explicit_closing_date(self):
        closure = fund_event(
            1,
            "ACCOUNTING_PERIOD_CLOSED",
            "close-y1",
            entity_id="2027-06-30",
            effective_date="2027-07-01",
        )

        record = self.executor.execute_event(closure, self.ledger)

        assert record is not None
        self.assertEqual(record.operation, "closure")
        post = next(call for call in self.transport.calls if call[0] == "POST" and call[1] == "/api/v1/glclosures")
        self.assertEqual(post[2]["closingDate"], "30 June 2027")
        self.assertEqual(post[3]["Idempotency-Key"], "close-y1")

    def test_resolve_accounts_can_bootstrap_missing_synthetic_account(self):
        transport = FakeFineractTransport(omit_account_code="5300")
        executor = FineractExecutor(transport, self.contract)

        resolved = executor.resolve_accounts(create_missing=True)

        self.assertIn("5300", resolved)
        create = next(call for call in transport.calls if call[0] == "POST" and call[1] == "/api/v1/glaccounts")
        self.assertEqual(create[2]["glCode"], "5300")
        self.assertEqual(create[2]["type"], 5)
        self.assertEqual(create[3]["Idempotency-Key"], "baudot-gl-5300")

    def test_five_year_scenario_executes_and_reconciles_back_to_baudot(self):
        events = load_five_year_events()
        expected_state = fold_events(events)

        for event in events:
            self.executor.execute_event(event, self.ledger)

        reconciliation = self.executor.reconcile_fund_state(expected_state)

        self.assertEqual(len(self.ledger.records), 30)
        self.assertTrue(all(record.reconciled for record in self.ledger.records.values()))
        self.assertTrue(reconciliation.reconciled)
        self.assertEqual(reconciliation.actual["1100"], Decimal("530000.00"))
        self.assertEqual(reconciliation.actual["1200"], Decimal("0.00"))
        self.assertEqual(reconciliation.actual["2100"], Decimal("0.00"))
        self.assertEqual(reconciliation.actual["4100"], Decimal("1675000.00"))
        self.assertEqual(reconciliation.actual["5100"], Decimal("1145000.00"))


if __name__ == "__main__":
    unittest.main()
