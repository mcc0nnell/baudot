#!/usr/bin/env python3
"""Validate Celix payment-authorization and provider-disbursement intent boundaries."""

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
) -> list[dict[str, str]]:
    observations = load(path)
    profiles = {item.get("profile") for item in observations}
    if profiles != {profile}:
        raise AssertionError(f"{path}: expected profile {profile!r}, saw {profiles}")
    if len(observations) != 13:
        raise AssertionError(f"{path}: expected thirteen observations, saw {len(observations)}")

    pairs = {(item["capability"], item["verdict"]) for item in observations}
    if pairs != expected:
        raise AssertionError(f"{path}: unexpected evidence set: {sorted(pairs)}")

    forbidden = {
        "FUND_CASH_MOVED",
        "PAYMENT_EXECUTED",
        "FINERACT_DISBURSEMENT_POSTED",
        "BANK_INSTRUCTION_ACCEPTED",
        "SETTLED",
        "COMPLIANT",
        "FCC_CERTIFIED",
    }
    leaked = [item for item in observations if item.get("verdict") in forbidden]
    if leaked:
        raise AssertionError(f"{path}: payment composition leaked a downstream cash/settlement verdict")
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
        "FundClaimAuthority",
        "ProviderPayableIntent",
        "FineractJournalAdapter",
    ]
    return [
        (capability, next(item["verdict"] for item in observations if item["capability"] == capability))
        for capability in capabilities
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("--pending", type=Path, required=True)
    parser.add_argument("--amount-mismatch", type=Path, required=True)
    parser.add_argument("--mapping-mismatch", type=Path, required=True)
    parser.add_argument("--duplicate-replay", type=Path, required=True)
    args = parser.parse_args()

    common = {
        ("SignalingParser", "PJSIP_PARSE_ACCEPTED"),
        ("CallAdmission", "PJSIP_UAS_TEXT_PROFILE_ADMITTED"),
        ("ActorAuthentication", "SHIRO_CONTEXT_AUTHENTICATED"),
        ("Authorization", "RANGER_ALLOW"),
        ("TrsBusinessAuthority", "TRS_ORDINARY_CALL_PLACEMENT_ALLOWED"),
        ("VrsCompensability", "VRS_COMPENSABILITY_EXTERNALLY_ESTABLISHED"),
        ("VrsRateResult", "VRS_RATE_RESULT_AVAILABLE"),
        ("FundClaimAuthority", "FUND_CLAIM_APPROVED"),
        ("ProviderPayableIntent", "PROVIDER_PAYABLE_INTENT_READY"),
        ("FineractJournalAdapter", "FINERACT_JOURNAL_ACCEPTED_FIXTURE"),
        ("FundCashBoundary", "NOT_MODELED"),
    }

    ready = require_profile(
        args.ready,
        "payment-authorized-disbursement-ready",
        common
        | {
            ("PaymentAuthorization", "PAYMENT_AUTHORIZED"),
            ("ProviderDisbursementIntent", "PROVIDER_DISBURSEMENT_INTENT_READY"),
        },
    )
    pending = require_profile(
        args.pending,
        "payment-pending-ledger-posted",
        common
        | {
            ("PaymentAuthorization", "PAYMENT_AUTHORIZATION_PENDING"),
            ("ProviderDisbursementIntent", "PROVIDER_DISBURSEMENT_INTENT_NOT_EVALUATED_PAYMENT_AUTHORIZATION_REQUIRED"),
        },
    )
    amount_mismatch = require_profile(
        args.amount_mismatch,
        "payment-amount-mismatch",
        common
        | {
            ("PaymentAuthorization", "PAYMENT_AUTHORIZATION_REJECTED_AMOUNT_MISMATCH"),
            ("ProviderDisbursementIntent", "PROVIDER_DISBURSEMENT_INTENT_NOT_EVALUATED_PAYMENT_AUTHORIZATION_REQUIRED"),
        },
    )
    mapping_mismatch = require_profile(
        args.mapping_mismatch,
        "disbursement-mapping-mismatch",
        common
        | {
            ("PaymentAuthorization", "PAYMENT_AUTHORIZED"),
            ("ProviderDisbursementIntent", "PROVIDER_DISBURSEMENT_INTENT_REJECTED_JOURNAL_MAPPING"),
        },
    )
    duplicate_replay = require_profile(
        args.duplicate_replay,
        "disbursement-duplicate-replay",
        common
        | {
            ("PaymentAuthorization", "PAYMENT_AUTHORIZED"),
            ("ProviderDisbursementIntent", "PROVIDER_DISBURSEMENT_INTENT_REJECTED_IDEMPOTENT_REPLAY"),
        },
    )

    profiles = [ready, pending, amount_mismatch, mapping_mismatch, duplicate_replay]
    signatures = [upstream_signature(items) for items in profiles]
    if any(signature != signatures[0] for signature in signatures[1:]):
        raise AssertionError(
            "payment profiles rewrote upstream parser/admission/authentication/authorization/business/compensability/claim/accounting evidence"
        )

    ready_payment = detail_for(ready, "PaymentAuthorization")
    if "authorized=true" not in ready_payment or "authorizedAmountUsd=8830.00" not in ready_payment:
        raise AssertionError("ready profile lost exact payment authorization state/amount")
    if "does not post" not in ready_payment.lower():
        raise AssertionError("ready payment evidence lost the no-cash-execution boundary")

    ready_disbursement = detail_for(ready, "ProviderDisbursementIntent")
    for token in ("readyForPosting=true", "debit=2100", "credit=1100", "amountUsd=8830.00"):
        if token not in ready_disbursement:
            raise AssertionError(f"ready disbursement evidence missing {token}")

    if "remains pending" not in detail_for(pending, "PaymentAuthorization"):
        raise AssertionError("pending profile did not preserve explicit payment-decision boundary")
    if "must equal" not in detail_for(amount_mismatch, "PaymentAuthorization"):
        raise AssertionError("payment amount mismatch did not enforce exact payable/payment parity")
    if "Dr 2100" not in detail_for(mapping_mismatch, "ProviderDisbursementIntent"):
        raise AssertionError("disbursement mapping mismatch lost canonical journal mapping")
    if "second financial effect" not in detail_for(duplicate_replay, "ProviderDisbursementIntent"):
        raise AssertionError("disbursement replay profile lost idempotency boundary")

    for observations in profiles:
        cash_boundary = detail_for(observations, "FundCashBoundary").lower()
        for forbidden_term in (
            "cash moved",
            "payment executed",
            "bank instruction accepted",
            "settled",
        ):
            if forbidden_term in cash_boundary:
                raise AssertionError(f"Fund cash boundary accidentally asserted {forbidden_term}")

    summary = {
        "schema": "baudot.celix.payment-authorization-summary.v1",
        "semanticSource": "interop/fineract/journal-contract-v1.json providerDisbursement",
        "providerPayablePostedImpliesPaymentAuthorization": False,
        "fineractLedgerSuccessImpliesPaymentAuthorization": False,
        "paymentAuthorizationImpliesCashMovement": False,
        "disbursementIntentImpliesCashMovement": False,
        "bankOrPaymentNetworkUsed": False,
        "settlementClaimed": False,
        "profiles": {
            "ready": len(ready),
            "pending": len(pending),
            "amountMismatch": len(amount_mismatch),
            "mappingMismatch": len(mapping_mismatch),
            "duplicateReplay": len(duplicate_replay),
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
