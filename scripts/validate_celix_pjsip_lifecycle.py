#!/usr/bin/env python3
"""Validate controlled PJSIP capability stop/start evidence in Apache Celix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PJSIP_IDENTITY = "pjsip/pjproject-2.17@5a457451fa2712ba18e12b01738e8ff3af2b26fd"
ADMISSION_VERDICT = "PJSIP_UAS_TEXT_ANSWER_SELECTED"
TYPE = "baudot.celix.lifecycle-observation"
DETAIL_MARKERS = (
    "parser=PJSIP_PARSE_ACCEPTED",
    "statusCode=200",
    "audioCount=0",
    "videoCount=0",
    "textCount=1",
)


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
    if len(observations) != 6:
        raise AssertionError(f"expected exactly six lifecycle observations, saw {len(observations)}")

    active = one(observations, "active", "CallAdmission", ADMISSION_VERDICT)
    one(observations, "active", "AuthorityBoundary", "NOT_MODELED")

    stopped = one(observations, "stopped", "CallAdmission", "CAPABILITY_MISSING")
    one(observations, "stopped", "AuthorityBoundary", "NOT_MODELED")

    restored = one(observations, "restored", "CallAdmission", ADMISSION_VERDICT)
    one(observations, "restored", "AuthorityBoundary", "NOT_MODELED")

    for label, item in (("active", active), ("restored", restored)):
        detail = item.get("detail", "")
        if PJSIP_IDENTITY not in detail:
            raise AssertionError(f"{label}: missing pinned PJSIP implementation identity")
        missing = [marker for marker in DETAIL_MARKERS if marker not in detail]
        if missing:
            raise AssertionError(f"{label}: missing parser/UAS answer-profile evidence: {missing}")

    if "stopped" not in stopped.get("detail", ""):
        raise AssertionError("stopped observation does not preserve the lifecycle cause")

    forbidden = {"AUTHORIZED", "COMPLIANT", "FCC_CERTIFIED", "FUND_ELIGIBLE", "PROTOCOL_CONFORMANT"}
    leaked = [
        (item.get("phase"), item.get("capability"), item.get("verdict"))
        for item in observations
        if item.get("verdict") in forbidden
    ]
    if leaked:
        raise AssertionError(f"lifecycle evidence leaked authority/conformance verdicts: {leaked}")

    summary = {
        "schema": "baudot.celix.pjsip-lifecycle-summary.v2",
        "callAdmissionImplementation": PJSIP_IDENTITY,
        "sequence": [ADMISSION_VERDICT, "CAPABILITY_MISSING", ADMISSION_VERDICT],
        "parserEvidence": "PJSIP_PARSE_ACCEPTED",
        "nativeUasAnswerProfile": {
            "statusCode": 200,
            "audioCount": 0,
            "videoCount": 0,
            "textCount": 1,
        },
        "authorizationClaimed": False,
        "protocolConformanceClaimed": False,
        "trsBusinessAuthorityClaimed": False,
        "observations": len(observations),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
