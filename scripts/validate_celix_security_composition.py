#!/usr/bin/env python3
"""Validate Celix composition of signaling, Shiro-derived actor context, and Ranger-shaped authorization."""

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
    if len(observations) != 5:
        raise AssertionError(f"{path}: expected five observations, saw {len(observations)}")

    pairs = {(item["capability"], item["verdict"]) for item in observations}
    if pairs != expected:
        raise AssertionError(f"{path}: unexpected evidence set: {sorted(pairs)}")

    forbidden = {
        "TRS_BUSINESS_AUTHORIZED",
        "FUND_ELIGIBLE",
        "FCC_CERTIFIED",
        "COMPLIANT",
        "PROTOCOL_CONFORMANT",
    }
    leaked = [item for item in observations if item.get("verdict") in forbidden]
    if leaked:
        raise AssertionError(f"{path}: composition leaked a business/regulatory authority verdict")

    return observations


def detail_for(observations: list[dict[str, str]], capability: str) -> str:
    matches = [item.get("detail", "") for item in observations if item.get("capability") == capability]
    if len(matches) != 1:
        raise AssertionError(f"expected one detail for {capability}, saw {len(matches)}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--good", type=Path, required=True)
    parser.add_argument("--deny", type=Path, required=True)
    parser.add_argument("--remembered", type=Path, required=True)
    args = parser.parse_args()

    common = {
        ("SignalingParser", "PJSIP_PARSE_ACCEPTED"),
        ("CallAdmission", "PJSIP_UAS_TEXT_PROFILE_ADMITTED"),
        ("AuthorityBoundary", "NOT_MODELED"),
    }

    good = require_profile(
        args.good,
        "security-good",
        common
        | {
            ("ActorAuthentication", "SHIRO_CONTEXT_AUTHENTICATED"),
            ("Authorization", "RANGER_ALLOW"),
        },
    )
    deny = require_profile(
        args.deny,
        "security-authorization-deny",
        common
        | {
            ("ActorAuthentication", "SHIRO_CONTEXT_AUTHENTICATED"),
            ("Authorization", "RANGER_DENY"),
        },
    )
    remembered = require_profile(
        args.remembered,
        "security-remembered-only",
        common
        | {
            ("ActorAuthentication", "SHIRO_CONTEXT_REMEMBERED_NOT_AUTHENTICATED"),
            ("Authorization", "AUTHORIZATION_NOT_EVALUATED_AUTHENTICATION_REQUIRED"),
        },
    )

    if "PR #127" not in detail_for(good, "ActorAuthentication"):
        raise AssertionError("authenticated actor evidence lost its Shiro contract lineage")
    if "PR #114" not in detail_for(good, "Authorization"):
        raise AssertionError("authorization evidence lost its Ranger contract lineage")
    if "explicit synthetic DENY" not in detail_for(deny, "Authorization"):
        raise AssertionError("DENY profile did not preserve the explicit authorization decision")
    if "not authenticated" not in detail_for(remembered, "Authorization"):
        raise AssertionError("remembered-only profile did not stop before policy evaluation")

    prohibited_actor_detail_terms = {
        "password=",
        "token=",
        "telephoneNumber=",
        "subscriberName=",
        "subscriberAddress=",
        "eligibilityApproved=",
        "compensable=",
        "claimApproved=",
        "paymentAuthorized=",
    }
    for observations in (good, deny, remembered):
        actor_detail = detail_for(observations, "ActorAuthentication")
        for term in prohibited_actor_detail_terms:
            if term in actor_detail:
                raise AssertionError(f"actor-context evidence leaked forbidden field {term}")

    summary = {
        "schema": "baudot.celix.security-composition-summary.v1",
        "shiroSemanticSource": "PR #127 bounded actor/session contract",
        "rangerSemanticSource": "PR #114 iTRS PDP contract",
        "liveShiroRuntimeClaimed": False,
        "liveRangerRuntimeClaimed": False,
        "parserSuccessImpliesAdmission": False,
        "admissionImpliesAuthentication": False,
        "authenticationImpliesAuthorization": False,
        "authorizationImpliesTrsBusinessAuthority": False,
        "profiles": {
            "good": len(good),
            "authorizationDeny": len(deny),
            "rememberedOnly": len(remembered),
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
