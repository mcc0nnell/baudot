#!/usr/bin/env python3
"""Validate the narrow Apache Celix capability-composition proving lane."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


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

    forbidden_authority_verdicts = {"AUTHORIZED", "COMPLIANT", "FCC_CERTIFIED", "FUND_ELIGIBLE"}
    leaked = sorted(
        (item["capability"], item["verdict"])
        for item in observations
        if item.get("verdict") in forbidden_authority_verdicts
    )
    if leaked:
        raise AssertionError(f"{path}: runtime capability evidence leaked an authority verdict: {leaked}")

    return observations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--good", required=True, type=Path)
    parser.add_argument("--fault-injected", required=True, type=Path)
    parser.add_argument("--missing-rtt", required=True, type=Path)
    args = parser.parse_args()

    good = require_profile(
        args.good,
        "good",
        {
            ("CallAdmission", "ADMISSION_FIXTURE_ACCEPTED"),
            ("RealtimeTextTransport", "RTT_FIXTURE_ACCEPTED"),
            ("AuthorityBoundary", "NOT_MODELED"),
        },
    )
    fault_injected = require_profile(
        args.fault_injected,
        "fault-injected",
        {
            ("CallAdmission", "FAULT_INJECTED_FAIL_OPEN"),
            ("RealtimeTextTransport", "FAULT_INJECTED_FAIL_OPEN"),
            ("AuthorityBoundary", "NOT_MODELED"),
        },
    )
    missing_rtt = require_profile(
        args.missing_rtt,
        "missing-rtt",
        {
            ("CallAdmission", "ADMISSION_FIXTURE_ACCEPTED"),
            ("RealtimeTextTransport", "CAPABILITY_MISSING"),
            ("AuthorityBoundary", "NOT_MODELED"),
        },
    )

    summary = {
        "schema": "baudot.celix.capability-runtime-summary.v1",
        "celixRuntimeClaim": "dynamic native capability composition only",
        "authorizationClaimed": False,
        "protocolConformanceClaimed": False,
        "profiles": {
            "good": len(good),
            "faultInjected": len(fault_injected),
            "missingRtt": len(missing_rtt),
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
