#!/usr/bin/env python3
"""Validate versioned cross-transport gateway contracts without overclaiming proof."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "testkit" / "gateways"
EXPECTED_VERSIONS = {1: "planned", 2: "runnable"}
REQUIRED_INVARIANTS = {
    "normal T.140 content is preserved across the transport boundary",
    "RFC 2198 redundancy metadata never becomes T.140 application content on the data-channel side",
    "an unrecovered missing T140block is represented by U+FFFD before forwarding to the opposite transport",
    "an empty T140block is not converted into a missing-text marker",
    "text transmission direction is preserved across the gateway",
    "presentation semantics are compared after transport-specific recovery and before transport-specific re-encoding",
    "transport packet or message boundaries are not required to remain identical when presentation semantics are equivalent",
}
REQUIRED_TRIALS = {
    "normal-rtp-to-datachannel",
    "normal-datachannel-to-rtp",
    "recovered-rtp-loss-does-not-leak-marker",
    "unrecovered-rtp-loss-becomes-marker",
    "datachannel-reestablishment-suspected-loss",
    "empty-block-is-not-loss",
}
REQUIRED_BOUNDARIES = {
    "full T.140 conformance",
    "full RFC 4103 conformance",
    "full RFC 8865 conformance",
    "production gateway readiness",
}


def load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def require_strings(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label}: must be a non-empty list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{label}: every item must be a non-empty string")
    return value


def validate_execution(path: Path, contract: dict) -> None:
    execution = contract.get("execution")
    if not isinstance(execution, dict):
        raise ValueError(f"{path}: runnable contract must declare execution metadata")
    expected = {
        "kind": "deterministic-reference-harness",
        "harness": "baudot_reference.gateway.run_gateway_contract",
        "runner": "python -m scripts.run_gateway_trials",
        "network": "none",
    }
    for key, value in expected.items():
        if execution.get(key) != value:
            raise ValueError(f"{path}: execution.{key} must be {value!r}")
    adapters = execution.get("adapters")
    if not isinstance(adapters, dict) or not adapters.get("rfc4103") or not adapters.get("rfc8865"):
        raise ValueError(f"{path}: runnable contract must bind both executable transport adapters")
    emits = set(require_strings(execution.get("emits"), f"{path}: execution.emits"))
    for required in {
        "source transport trace",
        "normalized T.140 trace",
        "target transport trace",
        "terminal trial verdict",
    }:
        if required not in emits:
            raise ValueError(f"{path}: runnable execution must emit {required}")


def main() -> None:
    paths = sorted(CONTRACT_DIR.glob("*.json"))
    if not paths:
        raise SystemExit("No gateway contracts found")

    seen_versions: set[int] = set()
    for path in paths:
        contract = load(path)
        if contract.get("id") != "BAUDOT-INTEROP-002":
            raise ValueError(f"{path}: unexpected gateway contract id")
        version = contract.get("version")
        if version not in EXPECTED_VERSIONS:
            raise ValueError(f"{path}: unexpected BAUDOT-INTEROP-002 version {version}")
        if version in seen_versions:
            raise ValueError(f"{path}: duplicate BAUDOT-INTEROP-002 version {version}")
        seen_versions.add(version)
        expected_status = EXPECTED_VERSIONS[version]
        if contract.get("status") != expected_status:
            raise ValueError(f"{path}: version {version} must remain status={expected_status}")

        invariants = set(require_strings(contract.get("invariants"), f"{path}: invariants"))
        missing_invariants = REQUIRED_INVARIANTS - invariants
        if missing_invariants:
            raise ValueError(f"{path}: missing gateway invariants: {sorted(missing_invariants)}")

        adapters = set(require_strings(contract.get("requiredAdapters"), f"{path}: requiredAdapters"))
        if not any("rfc4103" in item for item in adapters) or not any("rfc8865" in item for item in adapters):
            raise ValueError(f"{path}: contract must require both RFC 4103 and RFC 8865 adapters")

        trials = contract.get("trials")
        if not isinstance(trials, list) or not trials:
            raise ValueError(f"{path}: trials must be a non-empty list")
        seen: set[str] = set()
        for trial in trials:
            if not isinstance(trial, dict):
                raise ValueError(f"{path}: trial must be an object")
            trial_id = trial.get("id")
            if not isinstance(trial_id, str) or not trial_id:
                raise ValueError(f"{path}: trial id must be a non-empty string")
            if trial_id in seen:
                raise ValueError(f"{path}: duplicate trial id {trial_id}")
            seen.add(trial_id)
            if {trial.get("sourceTransport"), trial.get("targetTransport")} != {"rfc4103", "rfc8865"}:
                raise ValueError(f"{path}: {trial_id} must cross the RFC 4103/RFC 8865 boundary")
            markers = trial.get("expectedMissingMarkers")
            if not isinstance(markers, int) or markers < 0:
                raise ValueError(f"{path}: {trial_id} expectedMissingMarkers must be non-negative")

        missing_trials = REQUIRED_TRIALS - seen
        if missing_trials:
            raise ValueError(f"{path}: missing gateway trials: {sorted(missing_trials)}")

        recovered = next(item for item in trials if item["id"] == "recovered-rtp-loss-does-not-leak-marker")
        if recovered["expectedMissingMarkers"] != 0:
            raise ValueError(f"{path}: recovered RTP loss must not create a missing-text marker")
        unrecovered = next(item for item in trials if item["id"] == "unrecovered-rtp-loss-becomes-marker")
        if unrecovered["expectedMissingMarkers"] != 1 or "�" not in unrecovered.get("expectedPresentation", ""):
            raise ValueError(f"{path}: unrecovered RTP loss must preserve one explicit missing-text marker")
        empty = next(item for item in trials if item["id"] == "empty-block-is-not-loss")
        if empty["expectedMissingMarkers"] != 0:
            raise ValueError(f"{path}: empty T140block must not be treated as text loss")

        boundaries = set(
            require_strings(
                contract.get("claimBoundary", {}).get("doesNotEstablish"),
                f"{path}: claimBoundary.doesNotEstablish",
            )
        )
        missing_boundaries = REQUIRED_BOUNDARIES - boundaries
        if missing_boundaries:
            raise ValueError(f"{path}: missing claim boundaries: {sorted(missing_boundaries)}")

        if expected_status == "planned":
            require_strings(contract.get("evidenceRequiredBeforeRunnable"), f"{path}: evidenceRequiredBeforeRunnable")
        else:
            validate_execution(path, contract)
        require_strings(contract.get("evidenceRequiredBeforeProven"), f"{path}: evidenceRequiredBeforeProven")
        print(f"✓ gateway contract {contract['id']}@{version}: {expected_status} ({len(trials)} trials)")

    missing_versions = set(EXPECTED_VERSIONS) - seen_versions
    if missing_versions:
        raise ValueError(f"Missing BAUDOT-INTEROP-002 contract versions: {sorted(missing_versions)}")
    print(f"Baudot gateway contracts valid: {len(paths)} version(s).")


if __name__ == "__main__":
    main()
