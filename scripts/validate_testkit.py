#!/usr/bin/env python3
"""Zero-dependency structural and baseline semantic validation for Baudot testkit artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "testkit" / "contracts"
SCENARIO_DIR = ROOT / "testkit" / "scenarios"
VECTOR_DIR = ROOT / "testkit" / "vectors"
ALLOWED_STATES = {"planned", "runnable", "proven", "regressed"}
REQUIRED_INVARIANTS = {
    "sessionEstablished does not imply iceReady",
    "iceReady does not imply videoRendered",
    "videoDecoded does not imply videoRendered",
    "videoRendered does not imply rttReady",
    "rttReady requires rttNegotiated and firstT140CharacterObserved",
}
REQUIRED_T140_VECTORS = {
    "irv-basic-text",
    "latin1-supplement-text",
    "backspace-erases-last-character",
    "preferred-line-separator",
    "crlf-supported-newline",
    "bell-alert-does-not-add-text",
    "missing-text-marker",
}
CODE_POINT = re.compile(r"^U\+[0-9A-F]{4,6}$")


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


def parse_code_points(values: object, label: str) -> list[int]:
    items = require_string_list(values, label)
    code_points: list[int] = []
    for value in items:
        if not CODE_POINT.fullmatch(value):
            raise ValueError(f"{label}: invalid code point {value}; expected U+XXXX")
        code_point = int(value[2:], 16)
        if code_point > 0x10FFFF or 0xD800 <= code_point <= 0xDFFF:
            raise ValueError(f"{label}: invalid Unicode scalar value {value}")
        code_points.append(code_point)
    return code_points


def render_t140_baseline(code_points: list[int]) -> dict[str, object]:
    display: list[str] = []
    alerts = 0
    missing = 0
    line_breaks = 0
    index = 0

    while index < len(code_points):
        code_point = code_points[index]

        if code_point == 0x0007:  # BEL
            alerts += 1
        elif code_point == 0x0008:  # BS
            if display:
                display.pop()
        elif code_point == 0x2028:  # LINE SEPARATOR
            display.append("\n")
            line_breaks += 1
        elif code_point == 0x000D:  # Supported CR LF new-line form.
            if index + 1 >= len(code_points) or code_points[index + 1] != 0x000A:
                raise ValueError("baseline vectors do not define isolated CR")
            display.append("\n")
            line_breaks += 1
            index += 1
        elif code_point == 0x000A:
            raise ValueError("baseline vectors do not define isolated LF")
        elif code_point == 0xFFFD:
            display.append("\uFFFD")
            missing += 1
        elif code_point < 0x0020 or 0x007F <= code_point <= 0x009F:
            raise ValueError(f"baseline vectors do not define control U+{code_point:04X}")
        else:
            display.append(chr(code_point))

        index += 1

    return {
        "displayText": "".join(display),
        "alerts": alerts,
        "missingTextMarkers": missing,
        "lineBreaks": line_breaks,
    }


def validate_t140_vector_suite(path: Path) -> None:
    suite = load(path)
    suite_id = require_non_empty_string(suite.get("id"), f"{path}: id")
    version = suite.get("version")
    if not isinstance(version, int) or version < 1:
        raise ValueError(f"{path}: version must be a positive integer")
    if suite.get("status") != "baseline":
        raise ValueError(f"{path}: T.140 bootstrap suite must remain status=baseline")
    scope = require_non_empty_string(suite.get("scope"), f"{path}: scope")
    if "full T.140 conformance" not in scope:
        raise ValueError(f"{path}: scope must explicitly avoid a full T.140 conformance claim")

    sources = suite.get("sources")
    if not isinstance(sources, list) or len(sources) < 2:
        raise ValueError(f"{path}: sources must identify T.140 and Addendum 1 grounding")
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise ValueError(f"{path}: source {index} must be an object")
        require_non_empty_string(source.get("specification"), f"{path}: source {index} specification")
        require_non_empty_string(source.get("url"), f"{path}: source {index} url")
        require_string_list(source.get("basis"), f"{path}: source {index} basis")

    vectors = suite.get("vectors")
    if not isinstance(vectors, list) or not vectors:
        raise ValueError(f"{path}: vectors must be a non-empty list")

    seen: set[str] = set()
    for index, vector in enumerate(vectors):
        if not isinstance(vector, dict):
            raise ValueError(f"{path}: vector {index} must be an object")
        vector_id = require_non_empty_string(vector.get("id"), f"{path}: vector {index} id")
        if vector_id in seen:
            raise ValueError(f"{path}: duplicate vector id {vector_id}")
        seen.add(vector_id)
        require_non_empty_string(vector.get("description"), f"{path}: {vector_id} description")
        code_points = parse_code_points(vector.get("inputCodePoints"), f"{path}: {vector_id} inputCodePoints")

        encoded = "".join(chr(code_point) for code_point in code_points).encode("utf-8")
        actual_hex = " ".join(f"{byte:02x}" for byte in encoded)
        expected_hex = require_non_empty_string(vector.get("utf8Hex"), f"{path}: {vector_id} utf8Hex").lower()
        if actual_hex != expected_hex:
            raise ValueError(
                f"{path}: {vector_id} UTF-8 mismatch: declared {expected_hex}, computed {actual_hex}"
            )

        expected = vector.get("expected")
        if not isinstance(expected, dict):
            raise ValueError(f"{path}: {vector_id} expected must be an object")
        actual = render_t140_baseline(code_points)
        if actual != expected:
            raise ValueError(f"{path}: {vector_id} presentation mismatch: expected {expected}, got {actual}")

    missing_vectors = REQUIRED_T140_VECTORS - seen
    if missing_vectors:
        raise ValueError(f"{path}: missing baseline T.140 vectors: {sorted(missing_vectors)}")

    deferred = set(require_string_list(suite.get("deferred"), f"{path}: deferred"))
    for boundary in {"RFC 2198 redundancy", "SIP offer/answer for text/t140", "WebRTC data-channel carriage"}:
        if boundary not in deferred:
            raise ValueError(f"{path}: deferred scope must preserve transport boundary: {boundary}")

    print(f"✓ T.140 vectors {suite_id}@{version}: {len(vectors)} baseline cases")


def main() -> None:
    contract_paths = sorted(CONTRACT_DIR.glob("*.json"))
    scenario_paths = sorted(SCENARIO_DIR.glob("*.json"))
    vector_paths = sorted(VECTOR_DIR.glob("*.json"))
    if not contract_paths:
        raise SystemExit("No testkit contracts found")
    if not scenario_paths:
        raise SystemExit("No testkit scenarios found")
    if not vector_paths:
        raise SystemExit("No testkit vector suites found")

    contracts: dict[str, set[str]] = {}
    for path in contract_paths:
        contract_id, version, observations = validate_contract(path)
        ref = f"{contract_id}@{version}"
        if ref in contracts:
            raise ValueError(f"duplicate contract reference: {ref}")
        contracts[ref] = observations

    for path in scenario_paths:
        validate_scenario(path, contracts)

    for path in vector_paths:
        validate_t140_vector_suite(path)

    print(
        f"Baudot testkit valid: {len(contracts)} contract(s), "
        f"{len(scenario_paths)} scenario(s), {len(vector_paths)} vector suite(s)."
    )


if __name__ == "__main__":
    main()
