#!/usr/bin/env python3
"""Validate the Celix VRS compensability boundary derived from PR #131."""

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
    compensability_verdict: str,
) -> list[dict[str, str]]:
    observations = load(path)
    profiles = {item.get("profile") for item in observations}
    if profiles != {profile}:
        raise AssertionError(f"{path}: expected profile {profile!r}, saw {profiles}")
    if len(observations) != 7:
        raise AssertionError(f"{path}: expected seven observations, saw {len(observations)}")

    expected = {
        ("SignalingParser", "PJSIP_PARSE_ACCEPTED"),
        ("CallAdmission", "PJSIP_UAS_TEXT_PROFILE_ADMITTED"),
        ("ActorAuthentication", "SHIRO_CONTEXT_AUTHENTICATED"),
        ("Authorization", "RANGER_ALLOW"),
        ("TrsBusinessAuthority", "TRS_ORDINARY_CALL_PLACEMENT_ALLOWED"),
        ("VrsCompensability", compensability_verdict),
        ("PayableClaimBoundary", "NOT_MODELED"),
    }
    pairs = {(item["capability"], item["verdict"]) for item in observations}
    if pairs != expected:
        raise AssertionError(f"{path}: unexpected evidence set: {sorted(pairs)}")

    forbidden_verdicts = {
        "PAYABLE_CLAIM_CREATED",
        "RATE_CALCULATED",
        "JOURNAL_POSTED",
        "PAYMENT_AUTHORIZED",
        "SETTLED",
        "FCC_COMPLIANT",
        "FCC_CERTIFIED",
    }
    leaked = [item for item in observations if item.get("verdict") in forbidden_verdicts]
    if leaked:
        raise AssertionError(f"{path}: compensability composition leaked downstream authority")

    return observations


def detail_for(observations: list[dict[str, str]], capability: str) -> str:
    matches = [item.get("detail", "") for item in observations if item.get("capability") == capability]
    if len(matches) != 1:
        raise AssertionError(f"expected one detail for {capability}, saw {len(matches)}")
    return matches[0]


def require_upstream_identical(groups: list[list[dict[str, str]]]) -> None:
    for capability in (
        "SignalingParser",
        "CallAdmission",
        "ActorAuthentication",
        "Authorization",
        "TrsBusinessAuthority",
    ):
        details = {detail_for(group, capability) for group in groups}
        if len(details) != 1:
            raise AssertionError(f"{capability} evidence changed across compensability controls")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--established", type=Path, required=True)
    parser.add_argument("--pending", type=Path, required=True)
    parser.add_argument("--placement-only", type=Path, required=True)
    args = parser.parse_args()

    established = require_profile(
        args.established,
        "compensability-externally-established",
        "VRS_COMPENSABILITY_EXTERNALLY_ESTABLISHED",
    )
    pending = require_profile(
        args.pending,
        "compensability-pending",
        "VRS_COMPENSABILITY_PENDING_EXTERNAL_DETERMINATION",
    )
    placement_only = require_profile(
        args.placement_only,
        "compensability-placement-only",
        "VRS_COMPENSABILITY_INELIGIBLE_CALL_NOT_COMPLETED",
    )

    require_upstream_identical([established, pending, placement_only])

    established_detail = detail_for(established, "VrsCompensability")
    if "PR #131" not in established_detail:
        raise AssertionError("established compensability evidence lost PR #131 lineage")
    if "eligibleToSeekCompensation=true" not in established_detail:
        raise AssertionError("established profile lost candidate eligibility state")
    if "establishedCompensable=true" not in established_detail:
        raise AssertionError("established profile did not preserve terminal compensability state")

    pending_detail = detail_for(pending, "VrsCompensability")
    if "eligibleToSeekCompensation=true" not in pending_detail:
        raise AssertionError("pending profile should remain eligible to seek compensation")
    if "establishedCompensable=false" not in pending_detail:
        raise AssertionError("pending profile incorrectly established compensability")
    if "no final external compensability determination exists" not in pending_detail:
        raise AssertionError("pending profile lost the external-determination boundary")

    placement_detail = detail_for(placement_only, "VrsCompensability")
    if "eligibleToSeekCompensation=false" not in placement_detail:
        raise AssertionError("placement-only profile incorrectly became compensation-eligible")
    if "establishedCompensable=false" not in placement_detail:
        raise AssertionError("placement-only profile incorrectly became compensable")
    if "call placement authority is not call completion" not in placement_detail:
        raise AssertionError("placement-only profile lost the call-completion boundary")

    for observations in (established, pending, placement_only):
        for item in observations:
            detail = item.get("detail", "")
            for forbidden_state in (
                "payableClaimCreated=true",
                "rateCalculated=true",
                "journalPosted=true",
                "paymentAuthorized=true",
                "settled=true",
            ):
                if forbidden_state in detail:
                    raise AssertionError(f"evidence leaked downstream state {forbidden_state}")

    summary = {
        "schema": "baudot.celix.vrs-compensability-summary.v1",
        "semanticSource": "PR #131 Part 64 VRS compensability and Fund claim gate contract",
        "ordinaryCallPlacementImpliesCompletedCall": False,
        "completedCallImpliesCompensability": False,
        "eligibleToSeekCompensationImpliesEstablishedCompensable": False,
        "establishedCompensableImpliesPayableClaim": False,
        "establishedCompensableImpliesRateCalculation": False,
        "establishedCompensableImpliesJournal": False,
        "profiles": {
            "externallyEstablished": len(established),
            "pending": len(pending),
            "placementOnly": len(placement_only),
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
