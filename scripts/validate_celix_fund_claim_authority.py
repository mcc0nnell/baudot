#!/usr/bin/env python3
"""Validate Celix composition through the synthetic Fund claim authority boundary."""

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
    if len(observations) != 9:
        raise AssertionError(f"{path}: expected nine observations, saw {len(observations)}")

    pairs = {(item["capability"], item["verdict"]) for item in observations}
    if pairs != expected:
        raise AssertionError(f"{path}: unexpected evidence set: {sorted(pairs)}")

    forbidden = {
        "PROVIDER_PAYABLE_CREATED",
        "FINERACT_POSTED",
        "PAYMENT_AUTHORIZED",
        "FUND_CASH_MOVED",
        "SETTLED",
        "COMPLIANT",
        "FCC_CERTIFIED",
    }
    leaked = [item for item in observations if item.get("verdict") in forbidden]
    if leaked:
        raise AssertionError(f"{path}: claim composition leaked a downstream authority verdict")
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
    ]
    return [
        (capability, next(item["verdict"] for item in observations if item["capability"] == capability))
        for capability in capabilities
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approved", type=Path, required=True)
    parser.add_argument("--compensability-pending", type=Path, required=True)
    parser.add_argument("--rate-missing", type=Path, required=True)
    parser.add_argument("--claim-pending", type=Path, required=True)
    parser.add_argument("--amount-mismatch", type=Path, required=True)
    args = parser.parse_args()

    common = {
        ("SignalingParser", "PJSIP_PARSE_ACCEPTED"),
        ("CallAdmission", "PJSIP_UAS_TEXT_PROFILE_ADMITTED"),
        ("ActorAuthentication", "SHIRO_CONTEXT_AUTHENTICATED"),
        ("Authorization", "RANGER_ALLOW"),
        ("TrsBusinessAuthority", "TRS_ORDINARY_CALL_PLACEMENT_ALLOWED"),
        ("ProviderPayableBoundary", "NOT_MODELED"),
    }

    approved = require_profile(
        args.approved,
        "fund-claim-approved",
        common
        | {
            ("VrsCompensability", "VRS_COMPENSABILITY_EXTERNALLY_ESTABLISHED"),
            ("VrsRateResult", "VRS_RATE_RESULT_AVAILABLE"),
            ("FundClaimAuthority", "FUND_CLAIM_APPROVED"),
        },
    )
    comp_pending = require_profile(
        args.compensability_pending,
        "fund-claim-compensability-pending",
        common
        | {
            ("VrsCompensability", "VRS_COMPENSABILITY_PENDING_EXTERNAL_DETERMINATION"),
            ("VrsRateResult", "VRS_RATE_RESULT_AVAILABLE"),
            ("FundClaimAuthority", "FUND_CLAIM_NOT_EVALUATED_COMPENSABILITY_REQUIRED"),
        },
    )
    rate_missing = require_profile(
        args.rate_missing,
        "fund-claim-rate-missing",
        common
        | {
            ("VrsCompensability", "VRS_COMPENSABILITY_EXTERNALLY_ESTABLISHED"),
            ("VrsRateResult", "VRS_RATE_RESULT_MISSING"),
            ("FundClaimAuthority", "FUND_CLAIM_NOT_EVALUATED_RATE_REQUIRED"),
        },
    )
    claim_pending = require_profile(
        args.claim_pending,
        "fund-claim-pending",
        common
        | {
            ("VrsCompensability", "VRS_COMPENSABILITY_EXTERNALLY_ESTABLISHED"),
            ("VrsRateResult", "VRS_RATE_RESULT_AVAILABLE"),
            ("FundClaimAuthority", "FUND_CLAIM_PENDING_DECISION"),
        },
    )
    amount_mismatch = require_profile(
        args.amount_mismatch,
        "fund-claim-amount-mismatch",
        common
        | {
            ("VrsCompensability", "VRS_COMPENSABILITY_EXTERNALLY_ESTABLISHED"),
            ("VrsRateResult", "VRS_RATE_RESULT_AVAILABLE"),
            ("FundClaimAuthority", "FUND_CLAIM_REJECTED_AMOUNT_MISMATCH"),
        },
    )

    profiles = [approved, comp_pending, rate_missing, claim_pending, amount_mismatch]
    signatures = [upstream_signature(items) for items in profiles]
    if any(signature != signatures[0] for signature in signatures[1:]):
        raise AssertionError("Fund claim profiles rewrote upstream parser/admission/authentication/authorization/business evidence")

    if "establishedCompensable=true" not in detail_for(approved, "VrsCompensability"):
        raise AssertionError("approved profile lost terminal compensability evidence")
    if "PR #136" not in detail_for(approved, "VrsRateResult"):
        raise AssertionError("typed rate result lost PR #136 lineage")
    approved_detail = detail_for(approved, "FundClaimAuthority")
    if "approved=true" not in approved_detail or "approvedAmountUsd=8830.00" not in approved_detail:
        raise AssertionError("approved claim evidence lost exact approved state/amount")
    if "provider payable" not in approved_detail.lower():
        raise AssertionError("approved claim evidence lost downstream provider-payable boundary")

    if "establishedCompensable=false" not in detail_for(comp_pending, "VrsCompensability"):
        raise AssertionError("compensability-pending profile did not preserve non-terminal state")
    if "terminal externally established compensability" not in detail_for(comp_pending, "FundClaimAuthority"):
        raise AssertionError("claim authority did not fail closed on non-terminal compensability")
    if "claim authority must fail closed" not in detail_for(rate_missing, "VrsRateResult"):
        raise AssertionError("missing-rate profile lost fail-closed rate boundary")
    if "claim decision remains pending" not in detail_for(claim_pending, "FundClaimAuthority"):
        raise AssertionError("claim-pending profile did not preserve explicit claim-decision boundary")
    if "exact-amount integrity failed" not in detail_for(amount_mismatch, "FundClaimAuthority"):
        raise AssertionError("amount-mismatch profile did not enforce exact rate/claim parity")

    for observations in profiles:
        boundary = detail_for(observations, "ProviderPayableBoundary")
        for forbidden_term in ("provider payable created", "Fineract posted", "payment authorized", "cash moved", "settled"):
            if forbidden_term in boundary.lower():
                raise AssertionError(f"provider-payable boundary accidentally asserted {forbidden_term}")

    summary = {
        "schema": "baudot.celix.fund-claim-authority-summary.v1",
        "compensabilitySemanticSource": "PR #131",
        "rateSemanticSource": "PR #136 typed contract result",
        "claimSemanticSource": "PR #137 synthetic Fund claim handoff",
        "liveRateRuntimeClaimed": False,
        "liveFundAdministratorClaimed": False,
        "compensabilityImpliesClaimApproval": False,
        "rateResultImpliesClaimApproval": False,
        "claimApprovalImpliesProviderPayable": False,
        "providerPayableImpliesPaymentAuthorization": False,
        "profiles": {
            "approved": len(approved),
            "compensabilityPending": len(comp_pending),
            "rateMissing": len(rate_missing),
            "claimPending": len(claim_pending),
            "amountMismatch": len(amount_mismatch),
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
