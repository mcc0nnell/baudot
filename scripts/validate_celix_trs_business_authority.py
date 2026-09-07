#!/usr/bin/env python3
"""Validate TRS business-authority composition as a boundary distinct from Ranger and Fund authority."""

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
    if len(observations) != 6:
        raise AssertionError(f"{path}: expected six observations, saw {len(observations)}")

    pairs = {(item["capability"], item["verdict"]) for item in observations}
    if pairs != expected:
        raise AssertionError(f"{path}: unexpected evidence set: {sorted(pairs)}")

    forbidden = {
        "COMPENSABLE",
        "FUND_ELIGIBLE",
        "REIMBURSABLE",
        "CLAIM_APPROVED",
        "PAYMENT_AUTHORIZED",
        "FCC_CERTIFIED",
        "COMPLIANT",
    }
    leaked = [item for item in observations if item.get("verdict") in forbidden]
    if leaked:
        raise AssertionError(f"{path}: business composition leaked downstream Fund/regulatory authority")

    return observations


def detail_for(observations: list[dict[str, str]], capability: str) -> str:
    matches = [item.get("detail", "") for item in observations if item.get("capability") == capability]
    if len(matches) != 1:
        raise AssertionError(f"expected one detail for {capability}, saw {len(matches)}")
    return matches[0]


def invariant_detail(observations: list[dict[str, str]], capability: str) -> str:
    return detail_for(observations, capability)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--good", type=Path, required=True)
    parser.add_argument("--validation-fail", type=Path, required=True)
    parser.add_argument("--authorization-deny", type=Path, required=True)
    args = parser.parse_args()

    common = {
        ("SignalingParser", "PJSIP_PARSE_ACCEPTED"),
        ("CallAdmission", "PJSIP_UAS_TEXT_PROFILE_ADMITTED"),
        ("ActorAuthentication", "SHIRO_CONTEXT_AUTHENTICATED"),
        ("FundAuthorityBoundary", "NOT_MODELED"),
    }

    good = require_profile(
        args.good,
        "business-good",
        common
        | {
            ("Authorization", "RANGER_ALLOW"),
            ("TrsBusinessAuthority", "TRS_ORDINARY_CALL_PLACEMENT_ALLOWED"),
        },
    )
    validation_fail = require_profile(
        args.validation_fail,
        "business-validation-fail",
        common
        | {
            ("Authorization", "RANGER_ALLOW"),
            ("TrsBusinessAuthority", "TRS_ORDINARY_CALL_PLACEMENT_DENIED_VALIDATION"),
        },
    )
    authorization_deny = require_profile(
        args.authorization_deny,
        "business-authorization-deny",
        common
        | {
            ("Authorization", "RANGER_DENY"),
            ("TrsBusinessAuthority", "TRS_BUSINESS_NOT_EVALUATED_AUTHORIZATION_REQUIRED"),
        },
    )

    for capability in ("SignalingParser", "CallAdmission", "ActorAuthentication"):
        details = {
            invariant_detail(good, capability),
            invariant_detail(validation_fail, capability),
            invariant_detail(authorization_deny, capability),
        }
        if len(details) != 1:
            raise AssertionError(f"{capability} evidence changed across business-authority controls")

    if "PR #126" not in detail_for(good, "TrsBusinessAuthority"):
        raise AssertionError("TRS business-authority evidence lost Part 64 contract lineage")
    if "per-call validation failed" not in detail_for(validation_fail, "TrsBusinessAuthority"):
        raise AssertionError("validation-fail profile did not preserve the per-call validation cause")
    if "authorization was not ALLOW" not in detail_for(authorization_deny, "TrsBusinessAuthority"):
        raise AssertionError("authorization-deny profile did not stop business authority before evaluation")

    downstream_terms = {
        "compensable=true",
        "reimbursable=true",
        "claimApproved=true",
        "paymentAuthorized=true",
        "fundEligible=true",
    }
    for observations in (good, validation_fail, authorization_deny):
        for item in observations:
            detail = item.get("detail", "")
            for term in downstream_terms:
                if term in detail:
                    raise AssertionError(f"business-authority evidence leaked downstream state {term}")

    summary = {
        "schema": "baudot.celix.trs-business-authority-summary.v1",
        "semanticSource": "PR #126 Part 64 registration/numbering/per-call validation contract",
        "parserSuccessImpliesAdmission": False,
        "admissionImpliesAuthentication": False,
        "authenticationImpliesAuthorization": False,
        "authorizationImpliesOrdinaryCallPlacement": False,
        "ordinaryCallPlacementImpliesCallConnection": False,
        "ordinaryCallPlacementImpliesCompensability": False,
        "ordinaryCallPlacementImpliesFundEligibility": False,
        "profiles": {
            "good": len(good),
            "validationFail": len(validation_fail),
            "authorizationDeny": len(authorization_deny),
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
