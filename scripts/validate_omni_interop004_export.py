#!/usr/bin/env python3
"""Validate the Baudot-side BAUDOT-INTEROP-004 ACE Omni bridge export.

This validator checks source binding, fact vocabulary, timestamps, replay-key
uniqueness, and preserved artifact hashes. It intentionally does not create or
validate Omni ObservationEnvelope authority; that must happen inside ACE Omni.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ID = "BAUDOT-INTEROP-004"
EXPORT = ROOT / "target" / "evidence" / SCENARIO_ID / "omni-bridge-v1"
CONTRACT = ROOT / "testkit" / "bridges" / "omni-emulytics-bridge-v1.json"
STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")
REQUIRED_PAYLOAD = {"baudotScenarioId", "factType", "factValue", "claimScope"}


def sha256(path: Path) -> str:
    if not path.exists():
        raise ValueError(f"missing file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_iso(value: str, label: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} is not ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"missing JSON file: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def load_inputs(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"missing observation inputs: {path}")
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        row = json.loads(raw)
        if not isinstance(row, dict):
            raise ValueError(f"expected object in {path}:{line_number}")
        rows.append(row)
    if not rows:
        raise ValueError("observation input export is empty")
    return rows


def validate_manifest(path: Path, expected: dict[str, str]) -> None:
    if not path.exists():
        raise ValueError(f"missing export manifest: {path}")
    actual: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        digest, sep, filename = raw.partition("  ")
        if not sep:
            raise ValueError(f"malformed manifest line: {raw!r}")
        actual[filename] = digest
    if actual != expected:
        raise ValueError(f"export manifest mismatch: expected {expected!r}, got {actual!r}")


def main() -> None:
    bridge = load_json(CONTRACT)
    metadata_path = EXPORT / "bridge-export.json"
    inputs_path = EXPORT / "observation-inputs.jsonl"
    metadata = load_json(metadata_path)
    inputs = load_inputs(inputs_path)

    if metadata.get("version") != 1 or metadata.get("kind") != "baudot.omni.observation-inputs":
        raise ValueError("unexpected bridge export format")
    if metadata.get("authority") != "candidate-input":
        raise ValueError("Baudot bridge export must remain candidate-input authority")
    if metadata.get("scenarioId") != SCENARIO_ID:
        raise ValueError("bridge export scenario identity mismatch")
    if metadata.get("bridgeContract") != bridge.get("id"):
        raise ValueError("bridge export protocol identity mismatch")
    if metadata.get("observationCount") != len(inputs):
        raise ValueError("bridge export observation count mismatch")

    run_binding = metadata.get("runBinding")
    if not isinstance(run_binding, dict):
        raise ValueError("missing runBinding")
    run_id = run_binding.get("runId")
    adapter_id = run_binding.get("adapterId")
    if not isinstance(run_id, str) or not STABLE_ID.fullmatch(run_id):
        raise ValueError("invalid runBinding.runId")
    if not isinstance(adapter_id, str) or not STABLE_ID.fullmatch(adapter_id):
        raise ValueError("invalid runBinding.adapterId")
    if run_binding.get("adapterKind") != "baudot-testkit" or run_binding.get("capability") != "communications":
        raise ValueError("unexpected Baudot adapter descriptor")

    portable = bridge.get("portableFactTypes")
    if not isinstance(portable, list) or not all(isinstance(value, str) for value in portable):
        raise ValueError("bridge protocol portableFactTypes is malformed")
    allowed_fact_types = set(portable)

    replay_keys: set[tuple[str, str, str, str]] = set()
    facts: dict[tuple[str, str, str], Any] = {}

    for index, row in enumerate(inputs, 1):
        if "payloadSha256" in row or "version" in row:
            raise ValueError(f"input {index} improperly claims Omni envelope fields")

        observation_id = row.get("observationId")
        source_id = row.get("sourceId")
        if not isinstance(observation_id, str) or not STABLE_ID.fullmatch(observation_id):
            raise ValueError(f"input {index} has invalid observationId")
        if not isinstance(source_id, str) or not STABLE_ID.fullmatch(source_id):
            raise ValueError(f"input {index} has invalid sourceId")
        if row.get("runId") != run_id or row.get("adapterId") != adapter_id:
            raise ValueError(f"input {index} is not bound to the declared run/adapter")

        observed_at = row.get("observedAt")
        if not isinstance(observed_at, str):
            raise ValueError(f"input {index} lacks observedAt")
        parse_iso(observed_at, f"input {index}.observedAt")

        payload = row.get("payload")
        if not isinstance(payload, dict):
            raise ValueError(f"input {index} payload must be an object")
        missing = REQUIRED_PAYLOAD - set(payload)
        if missing:
            raise ValueError(f"input {index} payload missing {sorted(missing)}")
        if payload.get("baudotScenarioId") != SCENARIO_ID:
            raise ValueError(f"input {index} scenario identity mismatch")
        fact_type = payload.get("factType")
        if fact_type not in allowed_fact_types:
            raise ValueError(f"input {index} uses non-portable factType {fact_type!r}")

        source_artifact = payload.get("sourceArtifact")
        source_digest = payload.get("sourceArtifactSha256")
        if not isinstance(source_artifact, str) or not isinstance(source_digest, str):
            raise ValueError(f"input {index} lacks source artifact binding")
        source_path = ROOT / source_artifact
        if sha256(source_path) != source_digest:
            raise ValueError(f"input {index} source artifact digest mismatch")

        replay_key = (run_id, adapter_id, source_id, observation_id)
        if replay_key in replay_keys:
            raise ValueError(f"duplicate candidate replay key: {replay_key}")
        replay_keys.add(replay_key)

        arm_id = payload.get("armId")
        if not isinstance(arm_id, str):
            raise ValueError(f"input {index} lacks armId")
        facts[(arm_id, source_id, str(fact_type))] = payload.get("factValue")

    expected_facts = {
        ("live-transfer", "jain-sip.live-refer-transfer", "referAccepted"): True,
        ("live-transfer", "jain-sip.live-refer-transfer", "notifyProgressObserved"): True,
        ("live-transfer", "jain-sip.live-refer-transfer", "replacementDialogEstablished"): True,
        ("live-transfer", "jain-sip.live-refer-transfer", "replacementTargetCorrelated"): True,
        ("control", "baudot-reference.rfc4103-control", "firstT140CharacterObserved"): True,
        ("control", "baudot-reference.rfc4103-control", "rttReady"): True,
        ("signaling-only", "baudot-reference.rfc4103-signaling-only", "firstT140CharacterObserved"): False,
        ("signaling-only", "baudot-reference.rfc4103-signaling-only", "rttReady"): False,
        ("signaling-only", "jain-sip.rtt-signaling-only", "oldLegPreserved"): True,
    }
    for key, expected in expected_facts.items():
        actual = facts.get(key)
        if actual is not expected:
            raise ValueError(f"missing or incorrect bridge fact {key}: expected {expected!r}, got {actual!r}")

    source_artifacts = metadata.get("sourceArtifacts")
    if not isinstance(source_artifacts, list):
        raise ValueError("bridge export sourceArtifacts must be a list")
    for binding in source_artifacts:
        if not isinstance(binding, dict):
            raise ValueError("malformed source artifact binding")
        path = binding.get("path")
        digest = binding.get("sha256")
        if not isinstance(path, str) or not isinstance(digest, str):
            raise ValueError("malformed source artifact binding")
        if sha256(ROOT / path) != digest:
            raise ValueError(f"source artifact changed after export: {path}")

    validate_manifest(
        EXPORT / "manifest.sha256",
        {
            "bridge-export.json": sha256(metadata_path),
            "observation-inputs.jsonl": sha256(inputs_path),
        },
    )

    print(f"✓ {SCENARIO_ID} Omni bridge export: {len(inputs)} source-bound ObservationInput candidates")
    print("✓ authoritative ObservationEnvelope fields remain absent until Omni ingestion")
    print("✓ control rttReady=true and signaling-only rttReady=false remain source-distinct")


if __name__ == "__main__":
    main()
