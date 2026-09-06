#!/usr/bin/env python3
"""Validate the bounded Teams/Zoom application-ingest contract."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.normalize_application_ingest import (
    NEVER_ESTABLISHES,
    NormalizationError,
    normalize,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "testkit" / "applications" / "application-ingest-contract-v1.json"
EXPECTED_CASE_IDS = {
    "APP-INGEST-ZOOM-001",
    "APP-INGEST-ZOOM-002",
    "APP-INGEST-TEAMS-001",
    "APP-INGEST-TEAMS-002",
}
EXPECTED_SOURCES = {"zoom-rtms", "teams-graph-media"}


def load_object(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be a JSON object")
    return value


def expect_fails(document: dict, label: str) -> None:
    try:
        normalize(document)
    except NormalizationError:
        return
    raise ValueError(f"{label}: normalizer must fail closed")


def main() -> int:
    contract = load_object(CONTRACT_PATH)
    if contract.get("schema") != "baudot.application-ingest-contract@1":
        raise ValueError("unexpected application-ingest contract schema")
    if contract.get("status") != "experimental":
        raise ValueError("application-ingest contract must remain experimental")
    if contract.get("canonicalObservationSchema") != "baudot.session-observation@1":
        raise ValueError("canonical session observation schema drift")

    source_families = contract.get("sourceFamilies")
    if not isinstance(source_families, list):
        raise ValueError("sourceFamilies must be a list")
    source_ids = {entry.get("id") for entry in source_families if isinstance(entry, dict)}
    if source_ids != EXPECTED_SOURCES:
        raise ValueError(f"source family drift: {sorted(source_ids)}")

    if contract.get("doesNotEstablish") != NEVER_ESTABLISHES:
        raise ValueError("terminal authority exclusions must match the normalizer")

    cases = contract.get("cases")
    if not isinstance(cases, list):
        raise ValueError("cases must be a list")
    case_ids = {case.get("id") for case in cases if isinstance(case, dict)}
    if case_ids != EXPECTED_CASE_IDS:
        raise ValueError(f"case set drift: {sorted(case_ids)}")

    seen_event_types: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("case must be an object")
        document = case.get("input")
        expected = case.get("expected")
        if not isinstance(document, dict) or not isinstance(expected, dict):
            raise ValueError(f"{case.get('id')}: input/expected must be objects")
        if document.get("synthetic") is not True:
            raise ValueError(f"{case.get('id')}: committed source input must remain synthetic")

        actual = normalize(document)
        if actual != expected:
            raise ValueError(f"{case.get('id')}: normalized output differs from expected contract")

        expected_event_type = case.get("eventType")
        if actual.get("eventType") != expected_event_type:
            raise ValueError(f"{case.get('id')}: event type mismatch")
        seen_event_types.add(str(expected_event_type))

        authority = actual.get("authority")
        if not isinstance(authority, dict):
            raise ValueError(f"{case.get('id')}: authority must be present")
        if authority.get("classification") != "source-observation-only":
            raise ValueError(f"{case.get('id')}: source observation cannot become terminal authority")
        if authority.get("doesNotEstablish") != NEVER_ESTABLISHES:
            raise ValueError(f"{case.get('id')}: terminal authority exclusions missing")

        # The public Zoom source includes user_name. Canonical output deliberately
        # retains only the opaque source participant identifier.
        if document.get("sourceFamily") == "zoom-rtms" and "user_name" in json.dumps(actual):
            raise ValueError(f"{case.get('id')}: display name leaked into canonical output")

    if not {"signaling.connected", "media.audio.observed", "text.transcript.observed"} <= seen_event_types:
        raise ValueError("minimum normalized observation families are missing")

    zoom_unknown = copy.deepcopy(next(c["input"] for c in cases if c["id"] == "APP-INGEST-ZOOM-001"))
    zoom_unknown["message"]["msg_type"] = 999
    expect_fails(zoom_unknown, "unknown Zoom RTMS message")

    teams_unknown = copy.deepcopy(next(c["input"] for c in cases if c["id"] == "APP-INGEST-TEAMS-002"))
    teams_unknown["adapterObservation"]["kind"] = "magic-ready"
    expect_fails(teams_unknown, "unknown Teams adapter observation")

    print(f"✓ application ingest: {len(cases)} deterministic source->canonical cases")
    print("✓ Zoom transcript remains transcript, not RTT/T.140 readiness")
    print("✓ Teams/Zoom media remains source observation, not accessibility verdict")
    print("✓ unknown source events fail closed")
    print("application ingest contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
