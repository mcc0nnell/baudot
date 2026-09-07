#!/usr/bin/env python3
"""Validate the narrow Apache Celix capability-composition proving lane."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

PJSIP_IDENTITY = "pjsip/pjproject-2.17@5a457451fa2712ba18e12b01738e8ff3af2b26fd"


def load_observations(path: Path) -> list[dict[str, str]]:
    observations: list[dict[str, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if candidate.get("type") == "baudot.celix.observation":
            observations.append(candidate)
    if not observations:
        raise AssertionError(f"no Baudot Celix observations found in {path}")
    return observations


def observed_pairs(observations: Iterable[dict[str, str]]) -> set[tuple[str, str]]:
    return {(item["capability"], item["verdict"]) for item in observations}


def require_profile(path: Path, profile: str, required: set[tuple[str, str]]) -> list[dict[str, str]]:
    observations = load_observations(path)
    profiles = {item.get("profile") for item in observations}
    if profiles != {profile}:
        raise AssertionError(f"{path}: expected only profile {profile!r}, saw {sorted(profiles)}")

    pairs = observed_pairs(observations)
    missing = sorted(required - pairs)
    if missing:
        raise AssertionError(f"{path}: missing required observations: {missing}")

    forbidden_authority_verdicts = {
        "AUTHORIZED",
        "COMPLIANT",
        "FCC_CERTIFIED",
        "FUND_ELIGIBLE",
        "PROTOCOL_CONFORMANT",
    }
    leaked = sorted(
        (item["capability"], item["verdict"])
        for item in observations
        if item.get("verdict") in forbidden_authority_verdicts
    )
    if leaked:
        raise AssertionError(f"{path}: runtime capability evidence leaked an authority verdict: {leaked}")

    return observations


def require_pjsip_identity(
    observations: Iterable[dict[str, str]],
    capability: str,
    verdict: str,
) -> None:
    matches = [
        item
        for item in observations
        if item.get("capability") == capability and item.get("verdict") == verdict
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"expected exactly one {capability}/{verdict} observation, saw {len(matches)}"
        )
    if PJSIP_IDENTITY not in matches[0].get("detail", ""):
        raise AssertionError(f"{capability}/{verdict} did not preserve the pinned PJSIP identity")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--good", required=True, type=Path)
    parser.add_argument("--fault-injected", required=True, type=Path)
    parser.add_argument("--missing-rtt", required=True, type=Path)
    parser.add_argument("--parsed-not-admitted", required=True, type=Path)
    args = parser.parse_args()

    good = require_profile(
        args.good,
        "good",
        {
            ("SignalingParser", "PJSIP_PARSE_ACCEPTED"),
            ("CallAdmission", "PJSIP_UAS_TEXT_PROFILE_ADMITTED"),
            ("RealtimeTextTransport", "RTT_FIXTURE_ACCEPTED"),
            ("AuthorityBoundary", "NOT_MODELED"),
        },
    )
    require_pjsip_identity(good, "SignalingParser", "PJSIP_PARSE_ACCEPTED")
    require_pjsip_identity(good, "CallAdmission", "PJSIP_UAS_TEXT_PROFILE_ADMITTED")

    fault_injected = require_profile(
        args.fault_injected,
        "fault-injected",
        {
            ("SignalingParser", "CAPABILITY_MISSING"),
            ("CallAdmission", "FAULT_INJECTED_FAIL_OPEN"),
            ("RealtimeTextTransport", "FAULT_INJECTED_FAIL_OPEN"),
            ("AuthorityBoundary", "NOT_MODELED"),
        },
    )

    missing_rtt = require_profile(
        args.missing_rtt,
        "missing-rtt",
        {
            ("SignalingParser", "PJSIP_PARSE_ACCEPTED"),
            ("CallAdmission", "PJSIP_UAS_TEXT_PROFILE_ADMITTED"),
            ("RealtimeTextTransport", "CAPABILITY_MISSING"),
            ("AuthorityBoundary", "NOT_MODELED"),
        },
    )
    require_pjsip_identity(missing_rtt, "SignalingParser", "PJSIP_PARSE_ACCEPTED")
    require_pjsip_identity(missing_rtt, "CallAdmission", "PJSIP_UAS_TEXT_PROFILE_ADMITTED")

    parsed_not_admitted = require_profile(
        args.parsed_not_admitted,
        "parsed-not-admitted",
        {
            ("SignalingParser", "PJSIP_PARSE_ACCEPTED"),
            ("CallAdmission", "PJSIP_UAS_TEXT_PROFILE_NOT_ADMITTED"),
            ("RealtimeTextTransport", "RTT_FIXTURE_ACCEPTED"),
            ("AuthorityBoundary", "NOT_MODELED"),
        },
    )
    require_pjsip_identity(
        parsed_not_admitted,
        "SignalingParser",
        "PJSIP_PARSE_ACCEPTED",
    )
    require_pjsip_identity(
        parsed_not_admitted,
        "CallAdmission",
        "PJSIP_UAS_TEXT_PROFILE_NOT_ADMITTED",
    )

    if ("SignalingParser", "PJSIP_PARSE_ACCEPTED") not in observed_pairs(parsed_not_admitted):
        raise AssertionError("parsed-not-admitted control lost parser success")
    if ("CallAdmission", "PJSIP_UAS_TEXT_PROFILE_NOT_ADMITTED") not in observed_pairs(parsed_not_admitted):
        raise AssertionError("parsed-not-admitted control failed to preserve the admission boundary")

    summary = {
        "schema": "baudot.celix.capability-runtime-summary.v3",
        "celixRuntimeClaim": "dynamic native capability composition with parser/admission separation only",
        "pjsipImplementation": PJSIP_IDENTITY,
        "parserSuccessImpliesAdmission": False,
        "authorizationClaimed": False,
        "protocolConformanceClaimed": False,
        "profiles": {
            "good": len(good),
            "faultInjected": len(fault_injected),
            "missingRtt": len(missing_rtt),
            "parsedNotAdmitted": len(parsed_not_admitted),
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
