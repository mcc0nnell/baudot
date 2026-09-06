#!/usr/bin/env python3
"""Validate the Part 64 VRS rate-result to synthetic Fund/Fineract handoff."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "testkit/fund/part64-vrs-claim-handoff-v1.json"
RATE_CASES = ROOT / "testkit/part64/fixtures/vrs-rate-cases.json"
JOURNAL = ROOT / "interop/fineract/journal-contract-v1.json"


def load(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def amount(value) -> Decimal:
    return Decimal(str(value))


def main() -> None:
    handoff = load(HANDOFF)
    rate_doc = load(RATE_CASES)
    journal = load(JOURNAL)

    require(handoff["schema"] == "baudot.part64-vrs-claim-handoff@1", "handoff schema mismatch")
    require(handoff["productionFundClaim"] is False and handoff["productionPayment"] is False,
            "public handoff fixture claims production financial activity")

    boundary = handoff["authorityBoundary"]
    require(boundary == {
        "regulatoryCompensabilityAuthority": "upstream-part64-external-determination-input",
        "rateAuthority": "upstream-64.643-rate-engine",
        "claimApprovalAuthority": "baudot-synthetic-fund-claim-decision",
        "accountingAuthority": "fineract-synthetic-accounting-adapter-only",
        "paymentAuthorizationAuthority": "separate-synthetic-payment-authorization",
    }, "handoff authority boundary changed unexpectedly")

    require(journal["authority"] == "synthetic-accounting-adapter-only",
            "Fineract journal contract was promoted into business authority")
    claim_event = journal["events"]["providerClaimApproved"]
    require(claim_event["debit"] == "5100" and claim_event["credit"] == "2100",
            "providerClaimApproved journal accounts changed")
    require(claim_event["businessAuthority"] == "baudot-synthetic-claim-reducer",
            "provider claim journal business authority changed")
    payment_event = journal["events"]["providerDisbursement"]
    require(payment_event["debit"] == "2100" and payment_event["credit"] == "1100",
            "providerDisbursement journal accounts changed")
    require(payment_event["businessAuthority"] == "baudot-synthetic-payment-authorization",
            "provider disbursement authority changed")
    require("fineract-ledger-success-does-not-imply-program-eligibility" in journal["invariants"],
            "Fineract authority invariant missing")

    rate_cases = {case["scenario"]: case for case in rate_doc["cases"]}
    cases = {case["scenario"]: case for case in handoff["cases"]}
    require(set(cases) == {
        "FUND-HANDOFF-APPROVED-001",
        "FUND-HANDOFF-COMP-PENDING-001",
        "FUND-HANDOFF-COMP-DENIED-001",
        "FUND-HANDOFF-COMP-SUSPENDED-001",
        "FUND-HANDOFF-CLAIM-PENDING-001",
        "FUND-HANDOFF-AMOUNT-MISMATCH-001",
        "FUND-HANDOFF-DUPLICATE-REPLAY-001",
        "FUND-HANDOFF-DISBURSEMENT-BLOCKED-001",
    }, "unexpected Part 64/Fund handoff scenario set")

    # Positive accrual: regulatory decision, rate result, and synthetic claim approval must all align.
    approved = cases["FUND-HANDOFF-APPROVED-001"]
    require(approved["regulatoryDecision"] == "externally-established-compensable",
            "approved handoff lacks terminal regulatory decision")
    source_rate = rate_cases[approved["rateEngineScenario"]]
    source_amount = amount(source_rate["expected"]["calculatedCompensationUsd"])
    require(source_rate["expected"]["payableFundClaimCreated"] is False,
            "rate source incorrectly creates a payable claim")
    require(amount(approved["rateCalculatedAmountUsd"]) == source_amount,
            "handoff rate amount diverges from rate-engine source")
    require(approved["claimDecision"] == "approved", "positive handoff claim not approved")
    require(amount(approved["approvedClaimAmountUsd"]) == source_amount,
            "approved claim amount does not match rate result")
    expected = approved["expected"]
    require(expected["journalEvent"] == "providerClaimApproved" and expected["postingAllowed"] is True,
            "approved claim does not produce providerClaimApproved accrual")
    require(expected["debitAccount"] == claim_event["debit"] and
            expected["creditAccount"] == claim_event["credit"],
            "approved claim journal accounts diverge from canonical contract")
    require(amount(expected["journalAmountUsd"]) == source_amount,
            "approved journal amount does not match approved claim")
    require(expected["providerPayableCreated"] is True,
            "approved claim did not create synthetic provider payable")
    require(expected["fundCashChanged"] is False,
            "claim accrual incorrectly changed Fund cash")
    require(approved["paymentAuthorization"] == "not-determined" and
            expected["disbursementAllowed"] is False,
            "claim approval incorrectly became payment authorization")

    # Regulatory states that are not terminal-positive cannot create payables.
    pending = cases["FUND-HANDOFF-COMP-PENDING-001"]
    require(pending["regulatoryDecision"] == "pending" and pending["rateEngineScenario"] is None,
            "regulatory-pending control malformed")
    require(pending["expected"]["postingAllowed"] is False and
            pending["expected"]["providerPayableCreated"] is False,
            "regulatory-pending state created a payable")

    denied = cases["FUND-HANDOFF-COMP-DENIED-001"]
    require(denied["regulatoryDecision"] == "denied",
            "regulatory-denied control malformed")
    require(denied["expected"]["postingAllowed"] is False and
            denied["expected"]["providerPayableCreated"] is False,
            "regulatory-denied state created a payable")

    suspended = cases["FUND-HANDOFF-COMP-SUSPENDED-001"]
    require(suspended["regulatoryDecision"] == "suspended",
            "regulatory-suspended control malformed")
    require(suspended["expected"]["postingAllowed"] is False and
            suspended["expected"]["providerPayableCreated"] is False,
            "regulatory payment suspension leaked into payable posting")

    # Terminal compensability + rate still does not post until a synthetic claim decision is approved.
    claim_pending = cases["FUND-HANDOFF-CLAIM-PENDING-001"]
    require(claim_pending["regulatoryDecision"] == "externally-established-compensable",
            "claim-pending arm lacks terminal regulatory decision")
    require(amount(claim_pending["rateCalculatedAmountUsd"]) ==
            amount(rate_cases[claim_pending["rateEngineScenario"]]["expected"]["calculatedCompensationUsd"]),
            "claim-pending arm rate result mismatch")
    require(claim_pending["claimDecision"] == "pending" and
            claim_pending["expected"]["postingAllowed"] is False,
            "pending synthetic claim created a journal posting")

    # One cent mismatch must fail closed rather than silently changing the approved regulatory amount.
    mismatch = cases["FUND-HANDOFF-AMOUNT-MISMATCH-001"]
    require(mismatch["regulatoryDecision"] == "externally-established-compensable" and
            mismatch["claimDecision"] == "approved",
            "amount-mismatch control missing otherwise-positive gates")
    require(amount(mismatch["rateCalculatedAmountUsd"]) != amount(mismatch["approvedClaimAmountUsd"]),
            "amount-mismatch negative control accidentally matches")
    require(abs(amount(mismatch["rateCalculatedAmountUsd"]) - amount(mismatch["approvedClaimAmountUsd"])) == Decimal("0.01"),
            "amount-mismatch negative control must remain exactly one cent")
    require(mismatch["expected"]["postingAllowed"] is False and
            mismatch["expected"]["providerPayableCreated"] is False,
            "mismatched approved claim amount created a payable")

    # The canonical synthetic business transaction ID is the adapter idempotency key.
    replay = cases["FUND-HANDOFF-DUPLICATE-REPLAY-001"]
    require(replay["replayOfScenario"] == approved["scenario"], "duplicate replay target mismatch")
    require(replay["syntheticBusinessTransactionId"] == approved["syntheticBusinessTransactionId"],
            "duplicate replay does not reuse canonical business transaction ID")
    require(replay["priorPostingObservedForBusinessTransactionId"] is True,
            "duplicate replay lacks prior-posting observation")
    require(replay["expected"]["postingAllowed"] is False and
            amount(replay["expected"]["additionalFinancialEffectUsd"]) == Decimal("0.00") and
            replay["expected"]["providerPayableCreatedAgain"] is False,
            "duplicate replay produced additional financial effect")

    # A payable accrual is not a payment authorization and cannot touch cash by itself.
    payment = cases["FUND-HANDOFF-DISBURSEMENT-BLOCKED-001"]
    require(payment["approvedClaimBusinessTransactionId"] == approved["syntheticBusinessTransactionId"],
            "blocked disbursement does not reference the approved claim")
    require(payment["providerPayableExists"] is True,
            "blocked disbursement must start from an existing payable")
    require(payment["paymentAuthorization"] == "not-determined",
            "blocked disbursement unexpectedly has payment authorization")
    require(amount(payment["requestedDisbursementAmountUsd"]) == source_amount,
            "blocked disbursement amount does not match approved payable")
    require(payment["expected"]["journalEvent"] == "providerDisbursement",
            "blocked disbursement references wrong journal event")
    require(payment["expected"]["postingAllowed"] is False and
            payment["expected"]["fundCashChanged"] is False,
            "unapproved disbursement changed Fund cash")

    print("Part 64 -> synthetic Fund/Fineract claim handoff: PASS")


if __name__ == "__main__":
    main()
