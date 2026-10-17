#!/usr/bin/env python3
"""Validate Baudot's first observe-only failed-call analysis slice."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYZER = ROOT / "scripts" / "analyze_call_evidence.py"
CONTRACT = ROOT / "interop" / "pjsip" / "call-evidence-bundle-v1.json"
GOOD = ROOT / "testkit" / "call-evidence" / "known-good-v1.json"
FAILED = ROOT / "testkit" / "call-evidence" / "downstream-503-v1.json"


def require(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS {name}")


def load_analyzer():
    spec = importlib.util.spec_from_file_location(
        "baudot_call_evidence_analyzer",
        ANALYZER,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load call evidence analyzer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    analyzer = load_analyzer()
    contract = analyzer.load_json(CONTRACT)
    good = analyzer.load_json(GOOD)
    failed = analyzer.load_json(FAILED)

    analyzer.validate_bundle(contract, good)
    analyzer.validate_bundle(contract, failed)

    require("contract stays OBSERVE-only", contract["authority"]["mode"] == "OBSERVE")
    require(
        "analyzer has no live-call mutation authority",
        all(
            contract["authority"][key] is False
            for key in (
                "mayMutateLiveCallState",
                "mayRetryCall",
                "mayTerminateCall",
                "maySelectRoute",
                "mayUpdateRegistration",
                "mayUpdateNumbering",
            )
        ),
    )

    good_result = analyzer.analyze(contract, good)
    failed_result = analyzer.analyze(contract, failed)
    diff = analyzer.diff_against_baseline(good, failed)

    require("known-good fixture derives no failure", good_result["verdict"] == "NO_FAILURE_DERIVED")
    require(
        "503 fixture derives the explicit downstream observation",
        failed_result["verdict"] == "DOWNSTREAM_FINAL_503_OBSERVED",
    )
    require(
        "503 finding is bounded to downstream signaling",
        failed_result["failureBoundary"] == "downstream-signaling-boundary",
    )
    require(
        "root cause is deliberately not inferred",
        failed_result["rootCause"] == "NOT_DERIVED",
    )
    require(
        "provider fault is deliberately not claimed",
        failed_result["claimBoundary"]["providerFaultClaimed"] is False,
    )
    require(
        "analysis cannot mutate the live call",
        failed_result["claimBoundary"]["liveCallStateMutated"] is False,
    )
    require(
        "good and failed calls share ingress, iTRS, route selection, and egress INVITE",
        diff["commonPrefixObservations"] == 4,
    )
    require(
        "first failed-call divergence is the 503 final response",
        diff["targetFirstDivergence"]
        == ("signaling.downstream.final", "RECEIVED", 503),
    )
    require(
        "privacy contract requires synthetic or tokenized identity",
        contract["privacy"]["requiredIdentityMode"] == "synthetic-or-tokenized",
    )

    print("Observe-only failed-call analysis slice: PASS")


if __name__ == "__main__":
    main()
