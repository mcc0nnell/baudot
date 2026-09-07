#!/usr/bin/env python3
"""Validate controlled PJSIP parser/admission stop/start evidence in Apache Celix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PJSIP_IDENTITY = "pjsip/pjproject-2.17@5a457451fa2712ba18e12b01738e8ff3af2b26fd"
TYPE = "baudot.celix.lifecycle-observation"


def load(path: Path) -> list[dict[str, str]]:
    observations: list[dict[str, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if candidate.get("type") == TYPE:
            observations.append(candidate)
    if not observations:
        raise AssertionError(f"no lifecycle observations found in {path}")
    return observations


def one(
    observations: list[dict[str, str]],
    phase: str,
    capability: str,
    verdict: str,
) -> dict[str, str]:
    matches = [
        item
        for item in observations
        if item.get("phase") == phase
        and item.get("capability") == capability
        and item.get("verdict") == verdict
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"expected exactly one {phase}/{capability}/{verdict} observation, saw {len(matches)}"
        )
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()

    observations = load(args.log)
    if len(observations) != 9:
        raise AssertionError(f"expected exactly nine lifecycle observations, saw {len(observations)}")

    active_parser = one(observations, "active", "SignalingParser", "PJSIP_PARSE_ACCEPTED")
    active_admission = one(
        observations,
        "active",
        "CallAdmission",
        "PJSIP_UAS_TEXT_PROFILE_ADMITTED",
    )
    one(observations, "active", "AuthorityBoundary", "NOT_MODELED")

    stopped_parser = one(observations, "stopped", "SignalingParser", "CAPABILITY_MISSING")
    stopped_admission = one(observations, "stopped", "CallAdmission", "CAPABILITY_MISSING")
    one(observations, "stopped", "AuthorityBoundary", "NOT_MODELED")

    restored_parser = one(observations, "restored", "SignalingParser", "PJSIP_PARSE_ACCEPTED")
    restored_admission = one(
        observations,
        "restored",
        "CallAdmission",
        "PJSIP_UAS_TEXT_PROFILE_ADMITTED",
    )
    one(observations, "restored", "AuthorityBoundary", "NOT_MODELED")

    for label, item in (
        ("active parser", active_parser),
        ("active admission", active_admission),
        ("restored parser", restored_parser),
        ("restored admission", restored_admission),
    ):
        if PJSIP_IDENTITY not in item.get("detail", ""):
            raise AssertionError(f"{label}: missing pinned PJSIP implementation identity")

    for label, item in (
        ("stopped parser", stopped_parser),
        ("stopped admission", stopped_admission),
    ):
        if "stopped" not in item.get("detail", ""):
            raise AssertionError(f"{label} observation does not preserve the lifecycle cause")

    forbidden = {
        "AUTHORIZED",
        "COMPLIANT",
        "FCC_CERTIFIED",
        "FUND_ELIGIBLE",
        "PROTOCOL_CONFORMANT",
    }
    leaked = [
        (item.get("phase"), item.get("capability"), item.get("verdict"))
        for item in observations
        if item.get("verdict") in forbidden
    ]
    if leaked:
        raise AssertionError(f"lifecycle evidence leaked authority/conformance verdicts: {leaked}")

    summary = {
        "schema": "baudot.celix.pjsip-lifecycle-summary.v2",
        "pjsipImplementation": PJSIP_IDENTITY,
        "parserSequence": [
            "PJSIP_PARSE_ACCEPTED",
            "CAPABILITY_MISSING",
            "PJSIP_PARSE_ACCEPTED",
        ],
        "admissionSequence": [
            "PJSIP_UAS_TEXT_PROFILE_ADMITTED",
            "CAPABILITY_MISSING",
            "PJSIP_UAS_TEXT_PROFILE_ADMITTED",
        ],
        "authorizationClaimed": False,
        "protocolConformanceClaimed": False,
        "trsBusinessAuthorityClaimed": False,
        "observations": len(observations),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
