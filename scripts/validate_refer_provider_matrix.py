#!/usr/bin/env python3
"""Validate BAUDOT-INTEROP-004's provider-neutral REFER transfer matrix.

This is deliberately a deterministic evidence reducer, not a SIP stack.  It
keeps REFER acceptance, NOTIFY outcome, replacement-dialog establishment,
target correlation, old-leg continuity, and RTT readiness as separate facts.
"""

from __future__ import annotations

import json
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "testkit" / "refer" / "provider-transfer-matrix.json"

EXPECTED_FAILURES = {
    "FAIL_SIGNALING",
    "FAIL_CORRELATION",
    "FAIL_CONTINUITY",
    "FAIL_ACCESSIBILITY",
}


def load_fixture() -> dict:
    with FIXTURE.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("provider transfer fixture root must be an object")
    return value


def require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def is_2xx(value: object) -> bool:
    return isinstance(value, int) and 200 <= value < 300


def reduce_case(case: dict) -> tuple[str, dict[str, bool]]:
    refer_accepted = is_2xx(case.get("referFinalStatus"))
    notify_successful = is_2xx(case.get("notifyFinalStatus"))
    replacement_established = case.get("replacementDialogEstablished") is True
    target_correlated = (
        replacement_established
        and case.get("replacementInviteTarget") == case.get("declaredReferTarget")
        and case.get("declaredReferTarget") == case.get("target")
    )
    rtt_ready = (
        case.get("rttNegotiated") is True
        and case.get("firstT140CharacterObserved") is True
    )
    continuity_preserved = (
        case.get("oldLegTerminated") is not True
        or case.get("oldLegTerminatedAfterReplacementReady") is True
    )

    facts = {
        "referAccepted": refer_accepted,
        "notifySuccessful": notify_successful,
        "replacementDialogEstablished": replacement_established,
        "targetCorrelated": target_correlated,
        "rttReady": rtt_ready,
        "continuityPreserved": continuity_preserved,
    }

    if not (refer_accepted and notify_successful and replacement_established):
        return "FAIL_SIGNALING", facts
    if not target_correlated:
        return "FAIL_CORRELATION", facts
    if not continuity_preserved:
        return "FAIL_CONTINUITY", facts
    if not rtt_ready:
        return "FAIL_ACCESSIBILITY", facts
    return "PASS", facts


def validate_matrix(fixture: dict) -> None:
    fixture_id = require_string(fixture.get("id"), "id")
    if fixture.get("version") != 1:
        raise ValueError("provider transfer matrix version must be 1")

    providers = fixture.get("providers")
    if not isinstance(providers, list) or len(providers) < 2:
        raise ValueError("providers must contain at least two identities")
    if len(set(providers)) != len(providers):
        raise ValueError("provider identities must be unique")
    for provider in providers:
        require_string(provider, "provider identity")

    modes = fixture.get("transferModes")
    if modes != ["blind", "warm"]:
        raise ValueError("transferModes must preserve blind and warm as separate dimensions")

    expected_pairs = {(source, target) for source in providers for target in providers if source != target}
    declared_pairs_raw = fixture.get("pairs")
    if not isinstance(declared_pairs_raw, list):
        raise ValueError("pairs must be a list")
    declared_pairs = set()
    for pair in declared_pairs_raw:
        if not isinstance(pair, dict):
            raise ValueError("every pair must be an object")
        source = require_string(pair.get("source"), "pair source")
        target = require_string(pair.get("target"), "pair target")
        if source == target:
            raise ValueError("provider matrix must not contain self-transfer pairs")
        declared_pairs.add((source, target))
    if declared_pairs != expected_pairs:
        missing = sorted(expected_pairs - declared_pairs)
        extra = sorted(declared_pairs - expected_pairs)
        raise ValueError(f"directed provider-pair matrix mismatch: missing={missing} extra={extra}")

    matrix_cells = {(source, target, mode) for source, target in declared_pairs for mode in modes}
    expected_cells = len(expected_pairs) * len(modes)
    if len(matrix_cells) != expected_cells:
        raise ValueError("provider/mode matrix cells are not unique")

    required_phases = fixture.get("requiredPhases")
    expected_phases = [
        "original-dialog",
        "refer",
        "notify",
        "replacement-dialog",
        "replacement-readiness",
        "old-leg-teardown",
    ]
    if required_phases != expected_phases:
        raise ValueError("required transfer evidence phases changed unexpectedly")

    cases = fixture.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a non-empty list")

    seen_ids: set[str] = set()
    observed_verdicts: set[str] = set()
    positive_modes: set[str] = set()

    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("every case must be an object")
        case_id = require_string(case.get("id"), "case id")
        if case_id in seen_ids:
            raise ValueError(f"duplicate case id: {case_id}")
        seen_ids.add(case_id)

        source = require_string(case.get("source"), f"{case_id}: source")
        target = require_string(case.get("target"), f"{case_id}: target")
        mode = require_string(case.get("mode"), f"{case_id}: mode")
        if (source, target, mode) not in matrix_cells:
            raise ValueError(f"{case_id}: case is outside declared provider/mode matrix")

        declared_target = require_string(case.get("declaredReferTarget"), f"{case_id}: declaredReferTarget")
        if declared_target != target:
            raise ValueError(f"{case_id}: declared REFER target must equal configured target")

        expected = require_string(case.get("expectedVerdict"), f"{case_id}: expectedVerdict")
        actual, facts = reduce_case(case)
        if actual != expected:
            raise ValueError(f"{case_id}: expected {expected}, reduced {actual}; facts={facts}")

        observed_verdicts.add(actual)
        if actual == "PASS":
            positive_modes.add(mode)

        fact_summary = ", ".join(f"{key}={str(value).lower()}" for key, value in facts.items())
        print(f"✓ {case_id}: {actual} ({fact_summary})")

    if positive_modes != {"blind", "warm"}:
        raise ValueError("positive fixtures must exercise both blind and warm transfer modes")
    if not EXPECTED_FAILURES.issubset(observed_verdicts):
        missing = sorted(EXPECTED_FAILURES - observed_verdicts)
        raise ValueError(f"missing required negative verdict classes: {missing}")

    boundary = fixture.get("claimBoundary")
    if not isinstance(boundary, list):
        raise ValueError("claimBoundary must be a list")
    for required in {
        "synthetic provider identities only",
        "no live SIP exchange",
        "no provider support claim",
        "no SIP or REFER conformance claim",
        "no production VRS readiness claim",
    }:
        if required not in boundary:
            raise ValueError(f"missing claim boundary: {required}")

    print(
        f"{fixture_id}@1 valid: {len(providers)} providers, "
        f"{len(expected_pairs)} directed pairs, {expected_cells} provider/mode cells, "
        f"{len(cases)} reducer cases"
    )


def main() -> None:
    validate_matrix(load_fixture())


if __name__ == "__main__":
    main()
