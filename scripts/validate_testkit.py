#!/usr/bin/env python3
"""Zero-dependency structural validation for Baudot testkit artifacts."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "testkit" / "contracts"
SCENARIO_DIR = ROOT / "testkit" / "scenarios"
ALLOWED_STATES = {"planned", "runnable", "proven", "regressed"}
REQUIRED_INVARIANTS = {
    "sessionEstablished does not imply iceReady",
    "iceReady does not imply videoRendered",
    "videoDecoded does not imply videoRendered",
    "videoRendered does not imply rttReady",
    "rttReady requires rttNegotiated and firstT140CharacterObserved",
}


def load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def require_non_empty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: must be a non-empty string")
    return value


def require_string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label}: must be a non-empty list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{label}: every item must be a non-empty string")
    return value


def validate_contract(path: Path) -> tuple[str, int, set[str]]:
    contract = load(path)
    contract_id = require_non_empty_string(contract.get("id"), f"{path}: id")
    version = contract.get("version")
    if not isinstance(version, int) or version < 1:
        raise ValueError(f"{path}: version must be a positive integer")

    states = set(require_string_list(contract.get("readinessStates"), f"{path}: readinessStates"))
    if states != {"unknown", "pending", "ready", "failed"}:
        raise ValueError(f"{path}: readinessStates must preserve the four-state readiness model")

    observations = set(require_string_list(contract.get("observations"), f"{path}: observations"))
    invariants = set(require_string_list(contract.get("invariants"), f"{path}: invariants"))
    missing = REQUIRED_INVARIANTS - invariants
    if missing:
        raise ValueError(f"{path}: missing required invariants: {sorted(missing)}")

    rtt_ready = contract.get("derived", {}).get("rttReady", {}).get("allOf")
    if rtt_ready != ["rttNegotiated", "firstT140CharacterObserved"]:
        raise ValueError(
            f"{path}: rttReady must require rttNegotiated and firstT140CharacterObserved"
        )

    print(f"✓ contract {contract_id}@{version}")
    return contract_id, version, observations


def validate_scenario(path: Path, contracts: dict[str, set[str]]) -> None:
    scenario = load(path)
    scenario_id = require_non_empty_string(scenario.get("id"), f"{path}: id")
    require_non_empty_string(scenario.get("title"), f"{path}: title")
    status = require_non_empty_string(scenario.get("status"), f"{path}: status")
    if status not in ALLOWED_STATES:
        raise ValueError(f"{path}: invalid status {status}")

    contract_ref = require_non_empty_string(scenario.get("contract"), f"{path}: contract")
    if contract_ref not in contracts:
        raise ValueError(f"{path}: unknown contract {contract_ref}")

    observations = set(require_string_list(scenario.get("observations"), f"{path}: observations"))
    unknown = observations - contracts[contract_ref]
    if unknown:
        raise ValueError(f"{path}: observations not defined by {contract_ref}: {sorted(unknown)}")

    assertions = set(require_string_list(scenario.get("assertions"), f"{path}: assertions"))
    missing = REQUIRED_INVARIANTS - assertions
    if missing:
        raise ValueError(f"{path}: scenario drops required readiness assertions: {sorted(missing)}")

    arms = scenario.get("arms")
    if not isinstance(arms, list) or len(arms) < 2:
        raise ValueError(f"{path}: scenario must include a control and at least one manipulated arm")
    arm_ids = set()
    for index, arm in enumerate(arms):
        if not isinstance(arm, dict):
            raise ValueError(f"{path}: arm {index} must be an object")
        arm_id = require_non_empty_string(arm.get("id"), f"{path}: arm {index} id")
        require_non_empty_string(arm.get("condition"), f"{path}: arm {index} condition")
        if arm_id in arm_ids:
            raise ValueError(f"{path}: duplicate arm id {arm_id}")
        arm_ids.add(arm_id)
    if "control" not in arm_ids:
        raise ValueError(f"{path}: scenario must include a control arm")

    claim_boundary = scenario.get("claimBoundary", {}).get("doesNotEstablish")
    boundaries = set(require_string_list(claim_boundary, f"{path}: claimBoundary.doesNotEstablish"))
    for required in {"T.140 conformance", "RFC 4103 conformance"}:
        if required not in boundaries:
            raise ValueError(f"{path}: must explicitly preserve claim boundary: {required}")

    if status == "proven":
        evidence = scenario.get("evidence")
        if not isinstance(evidence, dict) or not evidence:
            raise ValueError(f"{path}: proven scenario must include evidence metadata")

    print(f"✓ scenario {scenario_id}: {status}")


def main() -> None:
    contract_paths = sorted(CONTRACT_DIR.glob("*.json"))
    scenario_paths = sorted(SCENARIO_DIR.glob("*.json"))
    if not contract_paths:
        raise SystemExit("No testkit contracts found")
    if not scenario_paths:
        raise SystemExit("No testkit scenarios found")

    contracts: dict[str, set[str]] = {}
    for path in contract_paths:
        contract_id, version, observations = validate_contract(path)
        ref = f"{contract_id}@{version}"
        if ref in contracts:
            raise ValueError(f"duplicate contract reference: {ref}")
        contracts[ref] = observations

    for path in scenario_paths:
        validate_scenario(path, contracts)

    print(f"Baudot testkit valid: {len(contracts)} contract(s), {len(scenario_paths)} scenario(s).")


if __name__ == "__main__":
    main()
