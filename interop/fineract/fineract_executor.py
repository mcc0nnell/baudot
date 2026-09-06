from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
import base64
import json
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from testkit.fund.runtime.fund_runtime import FundEvent, FundState


FINERACT_ACCOUNT_TYPE_IDS = {
    "ASSET": 1,
    "LIABILITY": 2,
    "EQUITY": 3,
    "INCOME": 4,
    "EXPENSE": 5,
}

POSTING_EVENT_TO_CONTRACT_KEY = {
    "CONTRIBUTOR_ASSESSED": "contributorAssessment",
    "CONTRIBUTOR_RECEIPT_RECORDED": "contributorReceipt",
    "PROVIDER_CLAIM_APPROVED": "providerClaimApproved",
    "PROVIDER_DISBURSEMENT_POSTED": "providerDisbursement",
    "PROVIDER_CLAIM_ADJUSTED": "providerClaimApproved",
    "CONTRIBUTOR_ASSESSMENT_ADJUSTED": "contributorAssessment",
}

FUND_STATE_ACCOUNT_FIELDS = {
    "1100": "cash",
    "1200": "contributor_receivable",
    "2100": "provider_payable",
    "4100": "contribution_revenue",
    "5100": "provider_compensation_expense",
}


@dataclass(frozen=True)
class JsonResponse:
    status: int
    body: Any
    headers: Mapping[str, str] = field(default_factory=dict)


class JsonTransport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> JsonResponse: ...


class FineractHttpError(RuntimeError):
    def __init__(self, status: int, body: Any):
        super().__init__(f"Fineract request failed with HTTP {status}: {body}")
        self.status = status
        self.body = body


class UrllibJsonTransport:
    """Small standard-library JSON transport for an explicitly configured Fineract instance.

    TLS verification is left enabled. Callers provide tenant/authentication headers;
    this test harness does not weaken HTTPS or embed credentials in repository data.
    """

    def __init__(self, base_url: str, *, default_headers: Mapping[str, str] | None = None, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.default_headers = dict(default_headers or {})
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> JsonResponse:
        request_headers = {"Accept": "application/json", **self.default_headers, **dict(headers or {})}
        payload = None
        if json_body is not None:
            payload = json.dumps(json_body, separators=(",", ":")).encode("utf-8")
            request_headers["Content-Type"] = "application/json"

        request = Request(f"{self.base_url}{path}", data=payload, headers=request_headers, method=method.upper())
        try:
            with urlopen(request, timeout=self.timeout) as response:  # nosec B310 - caller explicitly supplies trusted Fineract URL
                raw = response.read().decode("utf-8")
                body = json.loads(raw) if raw else None
                return JsonResponse(response.status, body, dict(response.headers.items()))
        except HTTPError as error:
            raw = error.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                body = raw
            raise FineractHttpError(error.code, body) from error


def basic_auth_headers(username: str, password: str, *, tenant_id: str = "default") -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {token}",
        "Fineract-Platform-TenantId": tenant_id,
    }


@dataclass(frozen=True)
class FineractConfig:
    office_id: int = 1
    currency_code: str = "USD"
    locale: str = "en"
    date_format: str = "dd MMMM yyyy"
    idempotency_header: str = "Idempotency-Key"


@dataclass(frozen=True)
class JournalPlan:
    synthetic_transaction_id: str
    event_type: str
    posting_date: str
    amount: Decimal
    debit_code: str
    credit_code: str
    debit_id: int
    credit_id: int


@dataclass(frozen=True)
class TransactionInspection:
    transaction_id: str
    journal_entry_ids: tuple[int, ...]
    debit_total: Decimal
    credit_total: Decimal
    balanced: bool
    reconciled: bool


@dataclass(frozen=True)
class ExecutionRecord:
    synthetic_business_transaction_id: str
    event_type: str
    posting_date: str
    operation: str
    amount: Decimal = Decimal("0")
    expected_debit_account: str | None = None
    expected_credit_account: str | None = None
    fineract_transaction_id: str | None = None
    fineract_journal_entry_ids: tuple[int, ...] = ()
    fineract_resource_id: int | None = None
    balanced: bool = True
    reconciled: bool = True
    served_from_cache: bool = False
    target_transaction_id: str | None = None

    def to_evidence(self) -> dict[str, Any]:
        return {
            "syntheticBusinessTransactionId": self.synthetic_business_transaction_id,
            "eventType": self.event_type,
            "postingDate": self.posting_date,
            "operation": self.operation,
            "amount": format(self.amount, "f"),
            "expectedDebitAccount": self.expected_debit_account,
            "expectedCreditAccount": self.expected_credit_account,
            "fineractTransactionId": self.fineract_transaction_id,
            "fineractJournalEntryIds": list(self.fineract_journal_entry_ids),
            "fineractResourceId": self.fineract_resource_id,
            "balanced": self.balanced,
            "reconciled": self.reconciled,
            "servedFromCache": self.served_from_cache,
            "targetTransactionId": self.target_transaction_id,
        }


@dataclass
class ExecutionLedger:
    records: dict[str, ExecutionRecord] = field(default_factory=dict)

    def get(self, transaction_id: str) -> ExecutionRecord | None:
        return self.records.get(transaction_id)

    def require(self, transaction_id: str) -> ExecutionRecord:
        record = self.get(transaction_id)
        if record is None:
            raise ValueError(f"no Fineract execution evidence for target transaction {transaction_id}")
        return record

    def add(self, record: ExecutionRecord) -> None:
        existing = self.records.get(record.synthetic_business_transaction_id)
        if existing is not None and existing != record:
            raise ValueError(f"conflicting Fineract execution evidence for {record.synthetic_business_transaction_id}")
        self.records[record.synthetic_business_transaction_id] = record

    def to_json(self) -> str:
        ordered = [self.records[key].to_evidence() for key in sorted(self.records)]
        return json.dumps({"schema": "baudot.fineract-execution-evidence@1", "records": ordered}, indent=2, sort_keys=True)


@dataclass(frozen=True)
class FundReconciliation:
    expected: Mapping[str, Decimal]
    actual: Mapping[str, Decimal]
    account_entry_ids: Mapping[str, tuple[int, ...]]
    reconciled: bool


class FineractExecutor:
    """Execute synthetic Fund accounting effects against Fineract and verify them independently."""

    def __init__(
        self,
        transport: JsonTransport,
        contract: Mapping[str, Any],
        *,
        account_ids: Mapping[str, int] | None = None,
        config: FineractConfig | None = None,
    ):
        self.transport = transport
        self.contract = contract
        self.account_ids = dict(account_ids or {})
        self.config = config or FineractConfig()

    def _surface(self, name: str, fallback: str) -> str:
        return str(self.contract.get("fineractApiSurface", {}).get(name, fallback))

    def _idempotency_headers(self, transaction_id: str) -> dict[str, str]:
        return {self.config.idempotency_header: transaction_id}

    def resolve_accounts(self, *, create_missing: bool = False) -> dict[str, int]:
        path = self._surface("glAccounts", "/api/v1/glaccounts")
        response = self.transport.request("GET", path)
        rows = _rows(response.body)
        resolved = {
            str(row["glCode"]): int(row["id"])
            for row in rows
            if isinstance(row, Mapping) and row.get("glCode") is not None and row.get("id") is not None
        }

        for code, account in self.contract["accounts"].items():
            if code in resolved:
                continue
            if not create_missing:
                raise ValueError(f"Fineract GL account {code} ({account['name']}) is missing")
            account_type = str(account["type"])
            if account_type not in FINERACT_ACCOUNT_TYPE_IDS:
                raise ValueError(f"unsupported Fineract GL account type {account_type}")
            payload = {
                "name": account["name"],
                "glCode": code,
                "manualEntriesAllowed": True,
                "type": FINERACT_ACCOUNT_TYPE_IDS[account_type],
                "usage": 1,
                "description": "Baudot synthetic TRS Fund proving-ground account",
            }
            created = self.transport.request(
                "POST",
                path,
                json_body=payload,
                headers=self._idempotency_headers(f"baudot-gl-{code}"),
            )
            resource_id = _required_int(created.body, "resourceId")
            resolved[code] = resource_id

        self.account_ids = {code: resolved[code] for code in self.contract["accounts"]}
        return dict(self.account_ids)

    def plan_journal(self, event: FundEvent) -> JournalPlan:
        key = POSTING_EVENT_TO_CONTRACT_KEY.get(event.event_type)
        if key is None:
            raise ValueError(f"event {event.event_type} is not a direct journal posting")
        if event.amount <= 0:
            raise ValueError("journal posting requires a positive amount")
        definition = self.contract["events"][key]
        debit_code = str(definition["debit"])
        credit_code = str(definition["credit"])

        if event.event_type in {"PROVIDER_CLAIM_ADJUSTED", "CONTRIBUTOR_ASSESSMENT_ADJUSTED"}:
            if event.adjustment_direction == "decrease":
                debit_code, credit_code = credit_code, debit_code
            elif event.adjustment_direction != "increase":
                raise ValueError(f"{event.event_type} requires adjustment_direction")

        try:
            debit_id = self.account_ids[debit_code]
            credit_id = self.account_ids[credit_code]
        except KeyError as error:
            raise ValueError(f"unresolved Fineract GL account {error.args[0]}; call resolve_accounts first") from error

        return JournalPlan(
            synthetic_transaction_id=event.transaction_id,
            event_type=event.event_type,
            posting_date=event.effective_date,
            amount=event.amount,
            debit_code=debit_code,
            credit_code=credit_code,
            debit_id=debit_id,
            credit_id=credit_id,
        )

    def execute_event(self, event: FundEvent, ledger: ExecutionLedger) -> ExecutionRecord | None:
        existing = ledger.get(event.transaction_id)
        if existing is not None:
            return existing

        if event.event_type in {"RUN_CONFIGURED", "PROGRAM_YEAR_ADVANCED"}:
            return None
        if event.event_type == "ACCOUNTING_PERIOD_CLOSED":
            record = self._execute_closure(event)
        elif event.event_type == "TRANSACTION_REVERSED":
            record = self._execute_reversal(event, ledger)
        elif event.event_type in POSTING_EVENT_TO_CONTRACT_KEY:
            record = self._execute_journal(event)
        else:
            raise ValueError(f"unsupported synthetic Fund event for Fineract execution: {event.event_type}")

        ledger.add(record)
        return record

    def _execute_journal(self, event: FundEvent) -> ExecutionRecord:
        plan = self.plan_journal(event)
        payload = {
            "officeId": self.config.office_id,
            "transactionDate": _fineract_date(plan.posting_date),
            "comments": f"Baudot synthetic Fund {plan.event_type}: {plan.synthetic_transaction_id}",
            "referenceNumber": plan.synthetic_transaction_id,
            "locale": self.config.locale,
            "currencyCode": self.config.currency_code,
            "dateFormat": self.config.date_format,
            "debits": [{"glAccountId": plan.debit_id, "amount": format(plan.amount, "f")}],
            "credits": [{"glAccountId": plan.credit_id, "amount": format(plan.amount, "f")}],
        }
        response = self.transport.request(
            "POST",
            self._surface("journalEntries", "/api/v1/journalentries"),
            json_body=payload,
            headers=self._idempotency_headers(plan.synthetic_transaction_id),
        )
        fineract_transaction_id = _required_str(response.body, "transactionId")
        inspection = self.inspect_transaction(
            fineract_transaction_id,
            expected_debit_id=plan.debit_id,
            expected_credit_id=plan.credit_id,
            expected_amount=plan.amount,
        )
        return ExecutionRecord(
            synthetic_business_transaction_id=event.transaction_id,
            event_type=event.event_type,
            posting_date=event.effective_date,
            operation="journal",
            amount=event.amount,
            expected_debit_account=plan.debit_code,
            expected_credit_account=plan.credit_code,
            fineract_transaction_id=fineract_transaction_id,
            fineract_journal_entry_ids=inspection.journal_entry_ids,
            balanced=inspection.balanced,
            reconciled=inspection.reconciled,
            served_from_cache=_served_from_cache(response.headers),
            target_transaction_id=event.target_transaction_id,
        )

    def _execute_reversal(self, event: FundEvent, ledger: ExecutionLedger) -> ExecutionRecord:
        target_id = event.target_transaction_id
        if not target_id:
            raise ValueError("TRANSACTION_REVERSED requires target_transaction_id")
        target = ledger.require(target_id)
        if not target.fineract_transaction_id or not target.expected_debit_account or not target.expected_credit_account:
            raise ValueError(f"target transaction {target_id} is not a reversible Fineract journal")
        if event.effective_date != target.posting_date:
            raise ValueError(
                "TRANSACTION_REVERSED effective_date must equal target posting date; Fineract reverses on the original journal date"
            )

        reversal_template = self._surface(
            "reversal",
            "/api/v1/journalentries/{transactionId}?command=reverse",
        )
        reversal_path = reversal_template.replace("{transactionId}", quote(target.fineract_transaction_id, safe=""))
        response = self.transport.request(
            "POST",
            reversal_path,
            json_body={"comments": f"Baudot synthetic reversal: {event.transaction_id} -> {target_id}"},
            headers=self._idempotency_headers(event.transaction_id),
        )
        fineract_transaction_id = _required_str(response.body, "transactionId")
        expected_debit_code = target.expected_credit_account
        expected_credit_code = target.expected_debit_account
        expected_debit_id = self.account_ids[expected_debit_code]
        expected_credit_id = self.account_ids[expected_credit_code]
        inspection = self.inspect_transaction(
            fineract_transaction_id,
            expected_debit_id=expected_debit_id,
            expected_credit_id=expected_credit_id,
            expected_amount=target.amount,
        )
        return ExecutionRecord(
            synthetic_business_transaction_id=event.transaction_id,
            event_type=event.event_type,
            posting_date=target.posting_date,
            operation="reversal",
            amount=target.amount,
            expected_debit_account=expected_debit_code,
            expected_credit_account=expected_credit_code,
            fineract_transaction_id=fineract_transaction_id,
            fineract_journal_entry_ids=inspection.journal_entry_ids,
            balanced=inspection.balanced,
            reconciled=inspection.reconciled,
            served_from_cache=_served_from_cache(response.headers),
            target_transaction_id=target_id,
        )

    def _execute_closure(self, event: FundEvent) -> ExecutionRecord:
        if not event.entity_id:
            raise ValueError("ACCOUNTING_PERIOD_CLOSED requires close date in entity_id")
        response = self.transport.request(
            "POST",
            self._surface("accountingClosures", "/api/v1/glclosures"),
            json_body={
                "officeId": self.config.office_id,
                "closingDate": _fineract_date(event.entity_id),
                "comments": f"Baudot synthetic Fund close: {event.transaction_id}",
                "locale": self.config.locale,
                "dateFormat": self.config.date_format,
            },
            headers=self._idempotency_headers(event.transaction_id),
        )
        return ExecutionRecord(
            synthetic_business_transaction_id=event.transaction_id,
            event_type=event.event_type,
            posting_date=event.effective_date,
            operation="closure",
            fineract_resource_id=_optional_int(response.body, "resourceId"),
            served_from_cache=_served_from_cache(response.headers),
        )

    def inspect_transaction(
        self,
        transaction_id: str,
        *,
        expected_debit_id: int,
        expected_credit_id: int,
        expected_amount: Decimal,
    ) -> TransactionInspection:
        query = urlencode({"transactionId": transaction_id, "limit": 0})
        response = self.transport.request("GET", f"{self._surface('journalEntries', '/api/v1/journalentries')}?{query}")
        rows = [row for row in _rows(response.body) if isinstance(row, Mapping) and str(row.get("transactionId")) == transaction_id]
        debit_rows = [row for row in rows if _entry_side(row) == "debit"]
        credit_rows = [row for row in rows if _entry_side(row) == "credit"]
        debit_total = sum((_as_decimal(row.get("amount")) for row in debit_rows), Decimal("0"))
        credit_total = sum((_as_decimal(row.get("amount")) for row in credit_rows), Decimal("0"))
        balanced = debit_total == credit_total
        debit_match = (
            len(debit_rows) == 1
            and int(debit_rows[0].get("glAccountId", -1)) == expected_debit_id
            and _as_decimal(debit_rows[0].get("amount")) == expected_amount
        )
        credit_match = (
            len(credit_rows) == 1
            and int(credit_rows[0].get("glAccountId", -1)) == expected_credit_id
            and _as_decimal(credit_rows[0].get("amount")) == expected_amount
        )
        entry_ids = tuple(int(row["id"]) for row in rows if row.get("id") is not None)
        return TransactionInspection(
            transaction_id=transaction_id,
            journal_entry_ids=entry_ids,
            debit_total=debit_total,
            credit_total=credit_total,
            balanced=balanced,
            reconciled=balanced and debit_match and credit_match,
        )

    def reconcile_fund_state(self, expected_state: FundState) -> FundReconciliation:
        expected: dict[str, Decimal] = {}
        actual: dict[str, Decimal] = {}
        entry_ids: dict[str, tuple[int, ...]] = {}

        journal_path = self._surface("journalEntries", "/api/v1/journalentries")
        for code, field_name in FUND_STATE_ACCOUNT_FIELDS.items():
            if code not in self.account_ids:
                raise ValueError(f"unresolved Fineract GL account {code}")
            account_id = self.account_ids[code]
            query = urlencode({"glAccountId": account_id, "limit": 0})
            response = self.transport.request("GET", f"{journal_path}?{query}")
            rows = [row for row in _rows(response.body) if isinstance(row, Mapping) and int(row.get("glAccountId", -1)) == account_id]
            debit_total = sum((_as_decimal(row.get("amount")) for row in rows if _entry_side(row) == "debit"), Decimal("0"))
            credit_total = sum((_as_decimal(row.get("amount")) for row in rows if _entry_side(row) == "credit"), Decimal("0"))
            account_type = str(self.contract["accounts"][code]["type"])
            natural_balance = debit_total - credit_total if account_type in {"ASSET", "EXPENSE"} else credit_total - debit_total
            expected[code] = getattr(expected_state, field_name)
            actual[code] = natural_balance
            entry_ids[code] = tuple(int(row["id"]) for row in rows if row.get("id") is not None)

        return FundReconciliation(
            expected=expected,
            actual=actual,
            account_entry_ids=entry_ids,
            reconciled=expected == actual,
        )


def load_contract(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _fineract_date(value: str) -> str:
    parsed = date.fromisoformat(value)
    return parsed.strftime("%d %B %Y")


def _rows(body: Any) -> list[Any]:
    if isinstance(body, list):
        return body
    if isinstance(body, Mapping):
        page_items = body.get("pageItems")
        if isinstance(page_items, list):
            return page_items
    return []


def _entry_side(row: Mapping[str, Any]) -> str | None:
    entry_type = row.get("entryType")
    if isinstance(entry_type, Mapping):
        value = str(entry_type.get("value", "")).lower()
        code = str(entry_type.get("code", "")).lower()
        entry_id = entry_type.get("id")
        if value == "debit" or code.endswith(".debit") or entry_id == 2:
            return "debit"
        if value == "credit" or code.endswith(".credit") or entry_id == 1:
            return "credit"
    return None


def _as_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _required_str(body: Any, key: str) -> str:
    if not isinstance(body, Mapping) or body.get(key) in {None, ""}:
        raise ValueError(f"Fineract response missing {key}: {body}")
    return str(body[key])


def _required_int(body: Any, key: str) -> int:
    if not isinstance(body, Mapping) or body.get(key) is None:
        raise ValueError(f"Fineract response missing {key}: {body}")
    return int(body[key])


def _optional_int(body: Any, key: str) -> int | None:
    if not isinstance(body, Mapping) or body.get(key) is None:
        return None
    return int(body[key])


def _served_from_cache(headers: Mapping[str, str]) -> bool:
    return any(key.lower() == "x-served-from-cache" and str(value).lower() == "true" for key, value in headers.items())
