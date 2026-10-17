#!/usr/bin/env python3
"""Deterministically analyze observe-only Baudot call evidence bundles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "interop" / "pjsip" / "call-evidence-bundle-v1.json"

PHASE_BY_KIND = {
    "signaling.ingress.invite": "ingress-signaling",
    "routing.itrs.lookup": "itrs-lookup",
    "routing.provider.selection": "provider-route-selection",
    "signaling.downstream.invite": "downstream-invite",
    "signaling.downstream.provisional": "downstream-provisional-response",
    "signaling.downstream.final": "downstream-final-response",
    "signaling.dialog.established": "dialog-established",
}


def require(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def walk(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def validate_bundle(contract: dict[str, Any], bundle: dict[str, Any]) -> None:
    require("bundle schema", bundle.get("schema") == contract["bundleSchema"])
    require(
        "required top-level fields",
        set(contract["requiredTopLevelFields"]).issubset(bundle),
    )
    require(
        "privacy mode",
        bundle["privacy"].get("identityMode")
        == contract["privacy"]["requiredIdentityMode"],
    )

    forbidden = set(contract["privacy"]["forbiddenFieldsAnywhere"])
    present = {key for key, _ in walk(bundle)}
    require(
        "forbidden identity/credential fields absent",
        forbidden.isdisjoint(present),
    )

    observations = bundle["observations"]
    require(
        "observations non-empty",
        isinstance(observations, list) and len(observations) > 0,
    )

    required = set(contract["observation"]["requiredFields"])
    allowed_kinds = set(contract["observation"]["allowedKinds"])
    allowed_statuses = set(contract["observation"]["allowedStatuses"])
    sequences: list[int] = []
    ids: list[str] = []

    for observation in observations:
        require("observation required fields", required.issubset(observation))
        require("observation kind allowed", observation["kind"] in allowed_kinds)
        require(
            "observation status allowed",
            observation["status"] in allowed_statuses,
        )
        sequences.append(observation["sequence"])
        ids.append(observation["id"])

    require("observation ids unique", len(ids) == len(set(ids)))
    require(
        "observation sequence unique",
        len(sequences) == len(set(sequences)),
    )
    require(
        "observation sequence strictly ordered",
        sequences == sorted(sequences),
    )

    authority = contract["authority"]
    require("contract is observe-only", authority["mode"] == "OBSERVE")
    for key in (
        "mayMutateLiveCallState",
        "mayRetryCall",
        "mayTerminateCall",
        "maySelectRoute",
        "mayUpdateRegistration",
        "mayUpdateNumbering",
    ):
        require(f"observe-only authority {key}=false", authority[key] is False)


def nested_match(
    observation: dict[str, Any],
    key: str,
    expected: Any,
) -> bool:
    current: Any = observation
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return current == expected


def rule_matches(
    observation: dict[str, Any],
    match: dict[str, Any],
) -> bool:
    return all(
        nested_match(observation, key, expected)
        for key, expected in match.items()
    )


def completed_stage(item: dict[str, Any]) -> bool:
    return item["status"] in {
        "OBSERVED",
        "SUCCEEDED",
        "SELECTED",
        "SENT",
        "RECEIVED",
        "ESTABLISHED",
    }


def analyze(
    contract: dict[str, Any],
    bundle: dict[str, Any],
) -> dict[str, Any]:
    validate_bundle(contract, bundle)
    observations = bundle["observations"]
    observed_phases = [PHASE_BY_KIND[item["kind"]] for item in observations]

    matched_rule = None
    matched_observation = None

    for observation in observations:
        for rule in contract["rules"]:
            if rule_matches(observation, rule["match"]):
                matched_rule = rule
                matched_observation = observation
                break
        if matched_rule is not None:
            break

    if matched_rule is None:
        dialog = next(
            (
                item
                for item in observations
                if item["kind"] == "signaling.dialog.established"
            ),
            None,
        )
        verdict = (
            "NO_FAILURE_DERIVED"
            if dialog is not None
            else "INSUFFICIENT_RULED_EVIDENCE"
        )
        evidence = dialog if dialog is not None else observations[-1]

        return {
            "schema": "baudot.call-evidence-diagnosis@1",
            "callId": bundle["callId"],
            "verdict": verdict,
            "failureBoundary": None,
            "failurePhase": None,
            "rootCause": "NOT_DERIVED",
            "primaryEvidenceIds": [evidence["id"]],
            "observedPhases": observed_phases,
            "priorCompletedStages": [
                PHASE_BY_KIND[item["kind"]]
                for item in observations
                if completed_stage(item)
            ],
            "authority": "OBSERVE_ONLY",
            "claimBoundary": {
                "productionRootCauseClaimed": False,
                "providerFaultClaimed": False,
                "liveCallStateMutated": False,
            },
        }

    index = observations.index(matched_observation)
    prior = observations[:index]

    return {
        "schema": "baudot.call-evidence-diagnosis@1",
        "callId": bundle["callId"],
        "verdict": matched_rule["verdict"],
        "failureBoundary": matched_rule["failureBoundary"],
        "failurePhase": matched_rule["failurePhase"],
        "rootCause": "NOT_DERIVED",
        "primaryEvidenceIds": [matched_observation["id"]],
        "observedPhases": observed_phases,
        "priorCompletedStages": [
            PHASE_BY_KIND[item["kind"]]
            for item in prior
            if completed_stage(item)
        ],
        "authority": "OBSERVE_ONLY",
        "claimBoundary": {
            "productionRootCauseClaimed": False,
            "providerFaultClaimed": False,
            "liveCallStateMutated": False,
        },
    }


def signature(
    bundle: dict[str, Any],
) -> list[tuple[str, str, Any]]:
    rows = []
    for item in bundle["observations"]:
        rows.append(
            (
                item["kind"],
                item["status"],
                item.get("attributes", {}).get("sipStatus"),
            )
        )
    return rows


def diff_against_baseline(
    baseline: dict[str, Any],
    target: dict[str, Any],
) -> dict[str, Any]:
    base_sig = signature(baseline)
    target_sig = signature(target)
    common = 0

    for left, right in zip(base_sig, target_sig):
        if left != right:
            break
        common += 1

    return {
        "schema": "baudot.call-evidence-diff@1",
        "baselineCallId": baseline["callId"],
        "targetCallId": target["callId"],
        "commonPrefixObservations": common,
        "baselineFirstDivergence": (
            base_sig[common] if common < len(base_sig) else None
        ),
        "targetFirstDivergence": (
            target_sig[common] if common < len(target_sig) else None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()

    contract = load_json(CONTRACT_PATH)
    bundle = load_json(args.bundle)
    diagnosis = analyze(contract, bundle)
    output: dict[str, Any] = {"diagnosis": diagnosis}

    if args.baseline is not None:
        baseline = load_json(args.baseline)
        validate_bundle(contract, baseline)
        output["diff"] = diff_against_baseline(baseline, bundle)

    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
