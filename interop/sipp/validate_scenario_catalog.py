#!/usr/bin/env python3
"""Validate Baudot's SIPp hostile signaling scenario contract."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "scenario-catalog.json"

REQUIRED_IDS = {f"SIPP-HOSTILE-{number:03d}" for number in range(1, 9)}
FORBIDDEN_AUTHORITIES = {
    "rttReady",
    "replacementRttReady",
    "firstT140CharacterObserved",
    "accessibilityReady",
    "safeToReleaseOldLeg",
    "sdpFresh",
    "rttNegotiated",
}


def main() -> int:
    document = json.loads(CATALOG.read_text(encoding="utf-8"))

    generator = document["generator"]
    if generator["oracleAdmitted"] is not False:
        raise AssertionError("SIPp must not be admitted as an oracle")
    if generator["terminalVerdictAuthority"] is not False:
        raise AssertionError("SIPp must not own terminal verdict authority")
    if any(document["claimBoundary"].values()):
        raise AssertionError("hostile signaling catalog must contain no conformance claim")

    supported = set(document["supportedPrimitives"])
    scenarios = document["scenarios"]
    observed_ids = {scenario["id"] for scenario in scenarios}
    if observed_ids != REQUIRED_IDS:
        raise AssertionError(
            f"scenario ids drifted: expected {sorted(REQUIRED_IDS)}, observed {sorted(observed_ids)}"
        )
    if len(observed_ids) != len(scenarios):
        raise AssertionError("duplicate hostile scenario id")

    names: set[str] = set()
    targets: set[str] = set()
    forbidden_covered: set[str] = set()

    for scenario in scenarios:
        name = scenario["name"]
        if name in names:
            raise AssertionError(f"duplicate hostile scenario name: {name}")
        names.add(name)
        targets.add(scenario["target"])

        primitives = set(scenario["primitives"])
        unknown = primitives - supported
        if unknown:
            raise AssertionError(f"{scenario['id']}: unknown SIPp primitives: {sorted(unknown)}")
        if not primitives:
            raise AssertionError(f"{scenario['id']}: scenario has no stimulus primitive")

        observations = scenario["requiredObservations"]
        if len(observations) < 3:
            raise AssertionError(f"{scenario['id']}: evidence surface is too weak")
        if len(set(observations)) != len(observations):
            raise AssertionError(f"{scenario['id']}: duplicate required observation")

        withheld = set(scenario["mustRemainFalseFromGeneratorAlone"])
        if not withheld:
            raise AssertionError(f"{scenario['id']}: missing generator authority boundary")
        if not withheld <= FORBIDDEN_AUTHORITIES:
            unexpected = withheld - FORBIDDEN_AUTHORITIES
            raise AssertionError(
                f"{scenario['id']}: unrecognized authority boundary: {sorted(unexpected)}"
            )
        forbidden_covered.update(withheld)

    for required_target in {"BAUDOT-INTEROP-003", "BAUDOT-INTEROP-004"}:
        if required_target not in targets:
            raise AssertionError(f"catalog lost required target {required_target}")

    if "rttReady" not in forbidden_covered:
        raise AssertionError("catalog no longer explicitly withholds rttReady from SIPp")

    print(f"validated {len(scenarios)} SIPp hostile signaling scenarios")
    print("terminal verdict authority remains outside SIPp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
