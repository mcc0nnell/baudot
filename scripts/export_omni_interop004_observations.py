#!/usr/bin/env python3
"""Export BAUDOT-INTEROP-004 live evidence as ACE Omni ObservationInput records.

This module deliberately does *not* create Omni ObservationEnvelope records. Baudot
owns the portable scenario semantics and source evidence; Omni owns authoritative
run identity, envelope creation, canonical payload digests, replay conflict
handling, ledger sequencing, and export.

The output of this script is therefore an ingestion candidate. It becomes Omni
ledger evidence only after an ACE Omni runtime accepts and envelopes it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ID = "BAUDOT-INTEROP-004"
EVIDENCE = ROOT / "target" / "evidence" / SCENARIO_ID
LIVE_DIR = EVIDENCE / "jain-live-refer-v1" / "live-refer-transfer"
RTT_ROOT = EVIDENCE / "jain-live-refer-rtt-v1"
CONTROL_DIR = RTT_ROOT / "control"
SIGNALING_ONLY_DIR = RTT_ROOT / "signaling-only"
RTT_RESULT = RTT_ROOT / "terminal" / "refer-rtt-readiness.json"
TERMINAL_RESULT = EVIDENCE / "terminal" / "result.json"
SCENARIO = ROOT / "testkit" / "scenarios" / "BAUDOT-INTEROP-004-cross-provider-refer.json"
CONTRACT = ROOT / "testkit" / "bridges" / "omni-emulytics-bridge-v1.json"
DEFAULT_OUTPUT = EVIDENCE / "omni-bridge-v1"
STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")


def sha256(path: Path) -> str:
    if not path.exists():
        raise ValueError(f"missing evidence: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def load_properties(path: Path) -> dict[str, str]:
    if not path.exists():
        raise ValueError(f"missing evidence: {path}")
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        key, sep, value = raw.partition("=")
        if not sep:
            raise ValueError(f"malformed properties line in {path}: {raw!r}")
        values[key] = value
    return values


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"missing evidence: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"missing evidence: {path}")
    events: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        event = json.loads(raw)
        if not isinstance(event, dict):
            raise ValueError(f"expected event object in {path}:{line_number}")
        at = event.get("at")
        if not isinstance(at, str):
            raise ValueError(f"event lacks timestamp in {path}:{line_number}")
        parse_iso(at, f"{path}:{line_number}.at")
        events.append(event)
    if not events:
        raise ValueError(f"no timestamped events in {path}")
    return events


def parse_iso(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} is not an ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone: {value!r}")
    return parsed


def latest_event_time(path: Path) -> str:
    events = load_events(path)
    latest = max(events, key=lambda event: parse_iso(str(event["at"]), f"{path}.at"))
    return str(latest["at"])


def bool_property(values: dict[str, str], key: str, label: str) -> bool:
    raw = values.get(key)
    if raw == "true":
        return True
    if raw == "false":
        return False
    raise ValueError(f"{label}: expected Boolean property {key}, got {raw!r}")


def bool_json(values: dict[str, Any], key: str, label: str) -> bool:
    value = values.get(key)
    if type(value) is not bool:
        raise ValueError(f"{label}: expected Boolean JSON fact {key}, got {value!r}")
    return value


def provider_metadata(values: dict[str, str], label: str) -> dict[str, str]:
    source = values.get("provider.source")
    target = values.get("provider.target")
    if not source or not target:
        raise ValueError(f"{label}: missing explicit provider source/target identity")
    return {"providerSource": source, "providerTarget": target}


def require_stable_id(value: str, label: str) -> None:
    if not STABLE_ID.fullmatch(value):
        raise ValueError(f"{label} must satisfy the Omni stable-id grammar")


def observation_input(
    *,
    run_id: str,
    adapter_id: str,
    observation_id: str,
    source_id: str,
    observed_at: str,
    arm_id: str,
    fact_type: str,
    fact_value: Any,
    claim_scope: str,
    source_artifact: Path,
    correlation_id: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    require_stable_id(observation_id, "observationId")
    require_stable_id(source_id, "sourceId")
    parse_iso(observed_at, "observedAt")
    payload: dict[str, Any] = {
        "baudotScenarioId": SCENARIO_ID,
        "factType": fact_type,
        "factValue": fact_value,
        "claimScope": claim_scope,
        "armId": arm_id,
        "correlationId": correlation_id,
        "sourceArtifact": relative(source_artifact),
        "sourceArtifactSha256": sha256(source_artifact),
    }
    if extra:
        payload.update(extra)
    return {
        "observationId": observation_id,
        "runId": run_id,
        "adapterId": adapter_id,
        "sourceId": source_id,
        "observedAt": observed_at,
        "payload": payload,
    }


def build_observations(run_id: str, adapter_id: str) -> tuple[list[dict[str, Any]], list[Path]]:
    require_stable_id(run_id, "runId")
    require_stable_id(adapter_id, "adapterId")

    live_result_path = LIVE_DIR / "result.properties"
    live_events_path = LIVE_DIR / "events.jsonl"
    control_result_path = CONTROL_DIR / "result.properties"
    control_events_path = CONTROL_DIR / "events.jsonl"
    signaling_result_path = SIGNALING_ONLY_DIR / "result.properties"
    signaling_events_path = SIGNALING_ONLY_DIR / "events.jsonl"

    live = load_properties(live_result_path)
    control_probe = load_properties(control_result_path)
    signaling_probe = load_properties(signaling_result_path)
    readiness = load_json(RTT_RESULT)
    terminal = load_json(TERMINAL_RESULT)

    if terminal.get("scenarioId") != SCENARIO_ID or terminal.get("terminalVerdict") != "RUNNABLE_PASS":
        raise ValueError("local BAUDOT-INTEROP-004 terminal reducer must produce RUNNABLE_PASS before export")
    if readiness.get("scenarioId") != SCENARIO_ID or readiness.get("result") != "PASS":
        raise ValueError("replacement-leg RTT reference validation must pass before export")

    control = readiness.get("control")
    signaling_only = readiness.get("signalingOnly")
    if not isinstance(control, dict) or not isinstance(signaling_only, dict):
        raise ValueError("replacement readiness result is missing control/signalingOnly arms")

    live_at = latest_event_time(live_events_path)
    control_at = latest_event_time(control_events_path)
    signaling_at = latest_event_time(signaling_events_path)
    live_provider = provider_metadata(live, "live")
    control_provider = provider_metadata(control_probe, "control-probe")
    signaling_provider = provider_metadata(signaling_probe, "signaling-only-probe")

    observations: list[dict[str, Any]] = []

    def add(**kwargs: Any) -> None:
        observations.append(
            observation_input(
                run_id=run_id,
                adapter_id=adapter_id,
                correlation_id=kwargs.pop("correlation_id"),
                **kwargs,
            )
        )

    live_facts = [
        ("referAccepted", bool_property(live, "refer.accepted", "live")),
        ("notifyProgressObserved", bool_property(live, "notify.progress.observed", "live")),
        ("replacementDialogEstablished", bool_property(live, "replacement.dialog.established", "live")),
        ("replacementTargetCorrelated", bool_property(live, "replacement.target.correlated", "live")),
        ("oldLegReleased", bool_property(live, "oldLeg.terminatedAfterReplacementEstablished", "live")),
    ]
    for fact_type, fact_value in live_facts:
        add(
            observation_id=f"interop004.live.{fact_type}",
            source_id="jain-sip.live-refer-transfer",
            observed_at=live_at,
            arm_id="live-transfer",
            fact_type=fact_type,
            fact_value=fact_value,
            claim_scope="refer-replacement-continuity",
            source_artifact=live_result_path,
            correlation_id="jain-live-refer-v1",
            extra=live_provider,
        )

    control_probe_facts = [
        ("referAccepted", bool_property(control_probe, "refer.accepted", "control-probe")),
        ("replacementDialogEstablished", bool_property(control_probe, "replacement.dialog.established", "control-probe")),
        ("rttNegotiated", bool_property(control_probe, "rtt.negotiated", "control-probe")),
        ("oldLegReleased", bool_property(control_probe, "oldLeg.bye.afterRttObservation", "control-probe")),
    ]
    for fact_type, fact_value in control_probe_facts:
        add(
            observation_id=f"interop004.control.probe.{fact_type}",
            source_id="jain-sip.rtt-control",
            observed_at=control_at,
            arm_id="control",
            fact_type=fact_type,
            fact_value=fact_value,
            claim_scope="replacement-leg-rtt-readiness",
            source_artifact=control_result_path,
            correlation_id="jain-live-refer-rtt-v1",
            extra=control_provider,
        )

    for fact_type in ("firstT140CharacterObserved", "rttReady"):
        add(
            observation_id=f"interop004.control.reference.{fact_type}",
            source_id="baudot-reference.rfc4103-control",
            observed_at=control_at,
            arm_id="control",
            fact_type=fact_type,
            fact_value=bool_json(control, fact_type, "control-reference"),
            claim_scope="replacement-leg-rtt-readiness",
            source_artifact=RTT_RESULT,
            correlation_id="jain-live-refer-rtt-v1",
            extra={"referenceValidator": readiness.get("validator")},
        )

    signaling_probe_facts = [
        ("referAccepted", bool_property(signaling_probe, "refer.accepted", "signaling-only-probe")),
        ("replacementDialogEstablished", bool_property(signaling_probe, "replacement.dialog.established", "signaling-only-probe")),
        ("rttNegotiated", bool_property(signaling_probe, "rtt.negotiated", "signaling-only-probe")),
        ("oldLegPreserved", not bool_property(signaling_probe, "oldLeg.bye.sent", "signaling-only-probe")),
    ]
    for fact_type, fact_value in signaling_probe_facts:
        add(
            observation_id=f"interop004.signaling-only.probe.{fact_type}",
            source_id="jain-sip.rtt-signaling-only",
            observed_at=signaling_at,
            arm_id="signaling-only",
            fact_type=fact_type,
            fact_value=fact_value,
            claim_scope="replacement-leg-rtt-readiness",
            source_artifact=signaling_result_path,
            correlation_id="jain-live-refer-rtt-v1",
            extra=signaling_provider,
        )

    for fact_type in ("firstT140CharacterObserved", "rttReady"):
        add(
            observation_id=f"interop004.signaling-only.reference.{fact_type}",
            source_id="baudot-reference.rfc4103-signaling-only",
            observed_at=signaling_at,
            arm_id="signaling-only",
            fact_type=fact_type,
            fact_value=bool_json(signaling_only, fact_type, "signaling-only-reference"),
            claim_scope="replacement-leg-rtt-readiness",
            source_artifact=RTT_RESULT,
            correlation_id="jain-live-refer-rtt-v1",
            extra={"referenceValidator": readiness.get("validator")},
        )

    observations.sort(key=lambda item: (item["sourceId"], item["observationId"]))

    artifacts = [
        SCENARIO,
        CONTRACT,
        live_result_path,
        live_events_path,
        control_result_path,
        control_events_path,
        signaling_result_path,
        signaling_events_path,
        RTT_RESULT,
        TERMINAL_RESULT,
    ]
    return observations, artifacts


def write_export(run_id: str, adapter_id: str, output: Path) -> None:
    observations, artifacts = build_observations(run_id, adapter_id)
    output.mkdir(parents=True, exist_ok=True)

    inputs_path = output / "observation-inputs.jsonl"
    with inputs_path.open("w", encoding="utf-8") as handle:
        for observation in observations:
            handle.write(json.dumps(observation, sort_keys=True, separators=(",", ":")) + "\n")

    metadata = {
        "version": 1,
        "kind": "baudot.omni.observation-inputs",
        "authority": "candidate-input",
        "scenarioId": SCENARIO_ID,
        "bridgeContract": "baudot-omni-emulytics-bridge-v1",
        "runBinding": {
            "runId": run_id,
            "adapterId": adapter_id,
            "adapterKind": "baudot-testkit",
            "capability": "communications",
        },
        "observationCount": len(observations),
        "sourceArtifacts": [
            {"path": relative(path), "sha256": sha256(path)} for path in sorted(artifacts, key=relative)
        ],
        "claim": "ObservationInput candidates only; ACE Omni has not yet created authoritative ObservationEnvelope records.",
        "promotionRule": "Omni ingestion does not promote BAUDOT-INTEROP-004 beyond its existing scenario status.",
    }
    metadata_path = output / "bridge-export.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest_path = output / "manifest.sha256"
    manifest_path.write_text(
        f"{sha256(metadata_path)}  bridge-export.json\n"
        f"{sha256(inputs_path)}  observation-inputs.jsonl\n",
        encoding="utf-8",
    )

    print(f"✓ {SCENARIO_ID} exported {len(observations)} Omni ObservationInput candidates")
    print(f"inputs: {inputs_path}")
    print("authority: candidate-input (not Omni ledger evidence)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True, help="Omni-assigned or caller-provided run binding")
    parser.add_argument("--adapter-id", default="baudot-interop004", help="Omni adapter identity")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    write_export(args.run_id, args.adapter_id, args.output)


if __name__ == "__main__":
    main()
