#!/usr/bin/env python3
"""Validate provider-payable accounting intent and Fineract execution boundaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

TYPE = "baudot.celix.observation"


def load(path: Path) -> list[dict[str, str]]:
    observations: list[dict[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("type") == TYPE:
            observations.append(item)
    if not observations:
        raise AssertionError(f"no Celix observations found in {path}")
    return observations


def require_profile(
    path: Path,
    profile: str,
    expected: set[tuple[str, str]],
    expected_count: int,
) -> list[dict[str, str]]:
    observations = load(path)
    profiles = {item.get("profile") for item in observations}
    if profiles != {profile}:
        raise AssertionError(f"{path}: expected profile {profile!r}, saw {profiles}")
    if len(observations) != expected_count:
        raise AssertionError(f"{path}: expected {expected_count} observations, saw {len(observations)}")

    pairs = {(item["capability"], item["verdict"]) for item in observations}
    if pairs != expected:
        raise AssertionError(f"{path}: unexpected evidence set: {sorted(pairs)}")

    forbidden = {
        "PAYMENT_AUTHORIZED",
        "PROVIDER_DISBURSEMENT_AUTHORIZED",
        "FUND_CASH_MOVED",
        "SETTLED",
        "COMPLIANT",
        "FCC_CERTIFIED",
    }
    leaked = [item for item in observations if item.get("verdict") in forbidden]
    if leaked:
        raise AssertionError(f"{path}: provider-payable composition leaked downstream authority")
    return observations


def detail_for(observations: list[dict[str, str]], capability: str) -> str:
    matches = [item.get("detail", "") for item in observations if item.get("capability") == capability]
    if len(matches) != 1:
        raise AssertionError(f"expected one detail for {capability}, saw {len(matches)}")
    return matches[0]


def upstream_signature(observations: list[dict[str, str]]) -> list[tuple[str, str]]:
    capabilities = [
        "SignalingParser",
        "CallAdmission",
        "ActorAuthentication",
        "Authorization",
        "TrsBusinessAuthority",
        "VrsCompensability",
        "VrsRateResult",
    ]
    return [
        (capability, next(item["verdict"] for item in observations if item["capability"] == capability))
        for capability in capabilities
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("--claim-pending-ledger-accepted", type=Path, required=True)
    parser.add_argument("--mapping-mismatch", type=Path, required=True)
    parser.add_argument("--duplicate-replay", type=Path, required=True)
    parser.add_argument("--closed-period", type=Path, required=True)
    args = parser.parse_args()

    common = {
        ("SignalingParser", "PJSIP_PARSE_ACCEPTED"),
        ("CallAdmission", "PJSIP_UAS_TEXT_PROFILE_ADMITTED"),
        ("ActorAuthentication", "SHIRO_CONTEXT_AUTHENTICATED"),
        ("Authorization", "RANGER_ALLOW"),
        ("TrsBusinessAuthority", "TRS_ORDINARY_CALL_PLACEMENT_ALLOWED"),
        ("VrsCompensability", "VRS_COMPENSABILITY_EXTERNALLY_ESTABLISHED"),
        ("VrsRateResult", "VRS_RATE_RESULT_AVAILABLE"),
        ("PaymentAuthorizationBoundary", "NOT_MODELED"),
        ("FundCashBoundary", "NOT_MODELED"),
    }

    ready = require_profile(
        args.ready,
        "provider-payable-ready",
        common
        | {
            ("FundClaimAuthority", "FUND_CLAIM_APPROVED"),
            ("ProviderPayableIntent", "PROVIDER_PAYABLE_INTENT_READY"),
            ("FineractJournalAdapter", "FINERACT_JOURNAL_ACCEPTED_FIXTURE"),
        },
        12,
    )

    claim_pending = require_profile(
        args.claim_pending_ledger_accepted,
        "provider-payable-claim-pending-ledger-accepted",
        common
        | {
            ("FundClaimAuthority", "FUND_CLAIM_PENDING_DECISION"),
            ("RawFineractLedgerObservation", "FINERACT_LEDGER_ACCEPTED_FIXTURE"),
            ("ProviderPayableIntent", "PROVIDER_PAYABLE_INTENT_NOT_EVALUATED_CLAIM_APPROVAL_REQUIRED"),
            ("FineractJournalAdapter", "FINERACT_POST_NOT_ATTEMPTED_INTENT_REQUIRED"),
        },
        13,
    )

    mapping = require_profile(
        args.mapping_mismatch,
        "provider-payable-mapping-mismatch",
        common
        | {
            ("FundClaimAuthority", "FUND_CLAIM_APPROVED"),
            ("ProviderPayableIntent", "PROVIDER_PAYABLE_INTENT_REJECTED_JOURNAL_MAPPING"),
            ("FineractJournalAdapter", "FINERACT_POST_NOT_ATTEMPTED_INTENT_REQUIRED"),
        },
        12,
    )

    duplicate = require_profile(
        args.duplicate_replay,
        "provider-payable-duplicate-replay",
        common
        | {
            ("FundClaimAuthority", "FUND_CLAIM_APPROVED"),
            ("ProviderPayableIntent", "PROVIDER_PAYABLE_INTENT_REJECTED_IDEMPOTENT_REPLAY"),
            ("FineractJournalAdapter", "FINERACT_POST_NOT_ATTEMPTED_INTENT_REQUIRED"),
        },
        12,
    )

    closed = require_profile(
        args.closed_period,
        "provider-payable-closed-period",
        common
        | {
            ("FundClaimAuthority", "FUND_CLAIM_APPROVED"),
            ("ProviderPayableIntent", "PROVIDER_PAYABLE_INTENT_REJECTED_ACCOUNTING_CLOSURE"),
            ("FineractJournalAdapter", "FINERACT_POST_NOT_ATTEMPTED_INTENT_REQUIRED"),
        },
        12,
    )

    profiles = [ready, claim_pending, mapping, duplicate, closed]
    signatures = [upstream_signature(items) for items in profiles]
    if any(signature != signatures[0] for signature in signatures[1:]):
        raise AssertionError(
            "provider-payable profiles rewrote upstream parser/admission/authentication/authorization/business/compensability/rate evidence"
        )

    ready_intent = detail_for(ready, "ProviderPayableIntent")
    for token in ("readyForPosting=true", "eventType=providerClaimApproved", "debit=5100", "credit=2100", "amountUsd=8830.00"):
        if token not in ready_intent:
            raise AssertionError(f"ready provider-payable intent lost canonical token {token}")

    ready_fineract = detail_for(ready, "FineractJournalAdapter")
    if "posted=true" not in ready_fineract:
        raise AssertionError("ready profile did not record synthetic Fineract ledger acceptance")
    if "does not imply" not in ready_fineract.lower():
        raise AssertionError("Fineract execution evidence lost its non-authority boundary")

    raw = detail_for(claim_pending, "RawFineractLedgerObservation")
    if "no claim or payment authority" not in raw.lower():
        raise AssertionError("hostile ledger-success observation lost explicit non-authority marking")
    if "claim decision remains pending" not in detail_for(claim_pending, "FundClaimAuthority"):
        raise AssertionError("hostile ledger-success profile did not preserve pending Fund claim")
    if "claim approval" not in detail_for(claim_pending, "ProviderPayableIntent").lower():
        raise AssertionError("provider-payable service did not fail closed on missing claim approval")

    if "Dr 5100" not in detail_for(mapping, "ProviderPayableIntent"):
        raise AssertionError("mapping mismatch did not preserve canonical Dr 5100 / Cr 2100 contract")
    if "idempotency key" not in detail_for(duplicate, "ProviderPayableIntent"):
        raise AssertionError("duplicate replay did not preserve adapter idempotency semantics")
    if "accounting closure" not in detail_for(closed, "ProviderPayableIntent"):
        raise AssertionError("closed-period profile did not enforce accounting closure")

    for observations in profiles:
        payment = detail_for(observations, "PaymentAuthorizationBoundary")
        cash = detail_for(observations, "FundCashBoundary")
        if "do not authorize" not in payment.lower():
            raise AssertionError("payment boundary lost explicit non-authorization statement")
        if "no providerDisbursement".lower() not in cash.lower():
            raise AssertionError("cash boundary lost providerDisbursement separation")

    summary = {
        "schema": "baudot.celix.provider-payable-intent-summary.v1",
        "journalContract": "interop/fineract/journal-contract-v1.json",
        "providerClaimApprovedDebit": "5100",
        "providerClaimApprovedCredit": "2100",
        "providerDisbursementModeled": False,
        "liveFineractClaimed": False,
        "ledgerSuccessImpliesClaimApproval": False,
        "ledgerSuccessImpliesPaymentAuthorization": False,
        "providerPayableImpliesFundCashMovement": False,
        "idempotencyEnforced": True,
        "accountingClosureEnforced": True,
        "profiles": {
            "ready": len(ready),
            "claimPendingLedgerAccepted": len(claim_pending),
            "mappingMismatch": len(mapping),
            "duplicateReplay": len(duplicate),
            "closedPeriod": len(closed),
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
