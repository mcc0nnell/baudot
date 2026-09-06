#!/usr/bin/env python3
"""Validate the Part 64/Fund provider-payment settlement and reconciliation contract."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYMENTS = ROOT / "testkit/fund/part64-vrs-payment-settlement-v1.json"
HANDOFF = ROOT / "testkit/fund/part64-vrs-claim-handoff-v1.json"
JOURNAL = ROOT / "interop/fineract/journal-contract-v1.json"


def load(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def money(value) -> Decimal:
    return Decimal(str(value))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def delta(before: dict, after: dict, key: str) -> Decimal:
    return money(after[key]) - money(before[key])


def main() -> None:
    payments = load(PAYMENTS)
    handoff = load(HANDOFF)
    journal = load(JOURNAL)

    require(payments["schema"] == "baudot.part64-vrs-payment-settlement@1", "payment schema mismatch")
    require(payments["safety"], "payment safety declarations missing")
    require(all(value is False for value in payments["safety"].values()),
            "public payment corpus enables production financial activity")

    require(payments["authorityBoundary"] == {
        "claimAccrualAuthority": "upstream-part64-fund-claim-handoff",
        "paymentAuthorizationAuthority": "baudot-synthetic-payment-authorization",
        "settlementAuthority": "baudot-synthetic-external-payment-rail-fixture",
        "accountingAuthority": "fineract-synthetic-accounting-adapter-only",
        "reconciliationAuthority": "baudot-independent-reducer",
    }, "payment authority boundary changed")

    require(journal["authority"] == "synthetic-accounting-adapter-only",
            "Fineract promoted into payment/program authority")
    require(journal["fineractApiSurface"]["reversal"].endswith("/reversal"),
            "canonical Fineract reversal surface missing")
    require("posting-after-accounting-closure-must-fail-or-use-an-authorized-open-date" in journal["invariants"],
            "canonical accounting-closure invariant missing")

    claim_event = journal["events"]["providerClaimApproved"]
    payment_event = journal["events"]["providerDisbursement"]
    require(claim_event["debit"] == "5100" and claim_event["credit"] == "2100",
            "provider claim accrual accounts changed")
    require(payment_event["debit"] == "2100" and payment_event["credit"] == "1100",
            "provider disbursement accounts changed")
    require(payment_event["businessAuthority"] == "baudot-synthetic-payment-authorization",
            "provider disbursement business authority changed")

    # The payment slice starts from the approved upstream handoff, not an invented second payable.
    handoff_cases = {case["scenario"]: case for case in handoff["cases"]}
    approved_handoff = handoff_cases["FUND-HANDOFF-APPROVED-001"]
    require(approved_handoff["claimDecision"] == "approved", "upstream handoff not approved")
    upstream_amount = money(approved_handoff["approvedClaimAmountUsd"])
    require(upstream_amount == Decimal("8830.00"), "unexpected upstream approved amount")

    cases = {case["scenario"]: case for case in payments["cases"]}
    require(set(cases) == {
        "FUND-PAY-SETTLE-001",
        "FUND-PAY-AUTH-BLOCK-001",
        "FUND-PAY-SETTLE-FAIL-001",
        "FUND-PAY-PARTIAL-001",
        "FUND-PAY-DUPLICATE-001",
        "FUND-PAY-READBACK-MISMATCH-001",
        "FUND-PAY-REVERSAL-001",
        "FUND-PAY-CLOSED-PERIOD-001",
    }, "unexpected payment scenario set")

    # Happy path: authorized amount, settlement, journal and independent readback all agree.
    full = cases["FUND-PAY-SETTLE-001"]
    require(full["providerPayableExists"] is True, "full-settlement arm lacks payable")
    require(money(full["payableAmountUsd"]) == upstream_amount, "full-settlement payable diverges upstream")
    require(full["paymentAuthorization"] == "approved", "full-settlement payment not authorized")
    require(money(full["authorizedAmountUsd"]) == upstream_amount, "authorized amount mismatch")
    require(full["paymentInstruction"]["created"] is True, "authorized payment lacks instruction")
    require(money(full["paymentInstruction"]["amountUsd"]) == upstream_amount,
            "payment instruction amount mismatch")
    require(full["settlement"]["status"] == "succeeded", "full settlement did not succeed")
    settled = money(full["settlement"]["settledAmountUsd"])
    require(settled == upstream_amount, "full settlement amount mismatch")

    obs = full["ledgerObservation"]
    require(obs["journalEvent"] == "providerDisbursement", "wrong full-settlement journal event")
    require(obs["debitAccount"] == payment_event["debit"] and obs["creditAccount"] == payment_event["credit"],
            "full-settlement journal accounts diverge canonical contract")
    require(money(obs["amountUsd"]) == settled, "full-settlement journal amount mismatch")
    require(delta(obs["before"], obs["after"], "providerPayableUsd") == -settled,
            "provider payable readback delta mismatch")
    require(delta(obs["before"], obs["after"], "fundCashUsd") == -settled,
            "Fund cash readback delta mismatch")
    require(full["expected"]["reconciled"] is True and money(full["expected"]["residualProviderPayableUsd"]) == 0,
            "full settlement expected result malformed")

    # Payable does not authorize payment.
    blocked = cases["FUND-PAY-AUTH-BLOCK-001"]
    require(blocked["providerPayableExists"] is True, "authorization-block arm lacks payable")
    require(blocked["paymentAuthorization"] == "not-determined", "authorization-block arm improperly authorized")
    require(blocked["paymentInstruction"]["created"] is False, "instruction created without payment authorization")
    require(blocked["settlement"]["status"] == "not-attempted", "settlement attempted without payment authorization")
    require(blocked["ledgerObservation"]["journalEvent"] is None, "cash journal posted without payment authorization")
    require(money(blocked["expected"]["cashMovementUsd"]) == 0, "blocked payment moved cash")

    # Failed rail settlement preserves the payable and cash state.
    failed = cases["FUND-PAY-SETTLE-FAIL-001"]
    require(failed["paymentAuthorization"] == "approved", "settlement-failure arm not authorized")
    require(failed["settlement"]["status"] == "failed" and money(failed["settlement"]["settledAmountUsd"]) == 0,
            "failed settlement carries non-zero settled amount")
    require(failed["ledgerObservation"]["journalEvent"] is None, "failed settlement posted disbursement")
    require(delta(failed["ledgerObservation"]["before"], failed["ledgerObservation"]["after"], "providerPayableUsd") == 0,
            "failed settlement changed provider payable")
    require(delta(failed["ledgerObservation"]["before"], failed["ledgerObservation"]["after"], "fundCashUsd") == 0,
            "failed settlement changed Fund cash")

    # Partial settlement is bounded to the externally settled amount and leaves residual payable.
    partial = cases["FUND-PAY-PARTIAL-001"]
    require(partial["settlement"]["status"] == "partial", "partial arm is not partial")
    partial_amount = money(partial["settlement"]["settledAmountUsd"])
    require(Decimal("0") < partial_amount < money(partial["authorizedAmountUsd"]),
            "partial settlement amount not strictly between zero and authorization")
    pob = partial["ledgerObservation"]
    require(money(pob["amountUsd"]) == partial_amount, "partial journal exceeds/differs from settlement")
    require(delta(pob["before"], pob["after"], "providerPayableUsd") == -partial_amount,
            "partial payable delta mismatch")
    require(delta(pob["before"], pob["after"], "fundCashUsd") == -partial_amount,
            "partial cash delta mismatch")
    residual = money(partial["authorizedAmountUsd"]) - partial_amount
    require(money(partial["expected"]["residualProviderPayableUsd"]) == residual,
            "partial residual payable mismatch")
    require(partial["expected"]["paymentFullySettled"] is False,
            "partial settlement incorrectly marked fully settled")

    # Duplicate external settlement identity has no second effect.
    duplicate = cases["FUND-PAY-DUPLICATE-001"]
    require(duplicate["settlementEventId"] == full["settlement"]["eventId"],
            "duplicate control does not replay the original settlement ID")
    require(duplicate["alreadyObserved"] is True, "duplicate control not marked previously observed")
    require(duplicate["expected"]["additionalJournalAllowed"] is False,
            "duplicate settlement permits additional journal")
    require(money(duplicate["expected"]["additionalFinancialEffectUsd"]) == 0,
            "duplicate settlement has financial effect")

    # One-cent readback mismatch fails reconciliation even though journal intent/settlement nominally agree.
    mismatch = cases["FUND-PAY-READBACK-MISMATCH-001"]
    require(mismatch["settlement"]["status"] == "succeeded", "readback mismatch control needs successful settlement")
    mobs = mismatch["ledgerObservation"]
    msettled = money(mismatch["settlement"]["settledAmountUsd"])
    payable_delta = delta(mobs["before"], mobs["after"], "providerPayableUsd")
    cash_delta = delta(mobs["before"], mobs["after"], "fundCashUsd")
    require(payable_delta != -msettled or cash_delta != -msettled,
            "readback mismatch control accidentally reconciles")
    require(mismatch["expected"]["reconciled"] is False and mismatch["expected"]["failClosed"] is True,
            "readback mismatch did not fail closed")

    # Reversal is equal-and-opposite, preserves identity, and restores balances.
    reversal = cases["FUND-PAY-REVERSAL-001"]
    original = reversal["original"]
    reverse = reversal["reversal"]
    require(reversal["reversalAuthorization"] == "approved", "reversal lacks authorization")
    require(reverse["referencesOriginalTransactionId"] == original["transactionId"],
            "reversal does not reference original transaction")
    require(original["transactionId"] != reverse["transactionId"], "reversal overwrites original transaction ID")
    require(original["debitAccount"] == "2100" and original["creditAccount"] == "1100",
            "original reversal case accounts malformed")
    require(reverse["debitAccount"] == original["creditAccount"] and reverse["creditAccount"] == original["debitAccount"],
            "reversal is not equal-and-opposite")
    require(money(reverse["amountUsd"]) == money(original["amountUsd"]), "reversal amount mismatch")
    rb = reversal["ledgerReadback"]
    require(rb["beforeOriginal"] == rb["afterReversal"], "post-reversal balances not restored")
    require(reversal["expected"]["historyPreserved"] is True and reversal["expected"]["reconciled"] is True,
            "reversal expected result malformed")

    # Closed period must fail rather than silently backdate/re-date.
    closed = cases["FUND-PAY-CLOSED-PERIOD-001"]
    require(closed["accountingPeriod"]["closed"] is True, "closed-period control is open")
    require(closed["accountingPeriod"]["authorizedOpenPostingDate"] is None,
            "closed-period control unexpectedly has authorized open date")
    require(closed["expected"]["journalAllowed"] is False,
            "closed accounting period allows journal posting")
    require(closed["expected"]["silentBackdatingAllowed"] is False,
            "closed-period control allows silent backdating")
    require(closed["expected"]["requiresAccountingControlResolution"] is True,
            "closed period does not require explicit control resolution")

    print("Part 64 Fund payment/settlement/reconciliation contract: PASS")


if __name__ == "__main__":
    main()
