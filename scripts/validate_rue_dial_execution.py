#!/usr/bin/env python3
"""Independently reduce the bounded live RUE-DIAL-001 JAIN execution."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXECUTION = ROOT / "testkit" / "vrs" / "executions" / "RUE-DIAL-001-jain.json"
RESULT = (
    ROOT
    / "target"
    / "evidence"
    / "RUE-DIAL-001"
    / "jain-one-stage-dial-around-v1"
    / "route-proof"
    / "result.properties"
)

EXPECTED_TARGET = "sip:+12025550199@provider-b.example;user=phone"
EXPECTED_DEFAULT = "provider-a.example"
EXPECTED_SELECTED = "provider-b.example"


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def load_properties(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError(f"missing live result: {path}")
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"malformed result line: {raw}")
        key, value = line.split("=", 1)
        if key in result:
            raise ValueError(f"duplicate result key: {key}")
        result[key] = value
    return result


def main() -> int:
    execution = load_json(EXECUTION)
    if execution.get("id") != "RUE-DIAL-001-jain":
        raise ValueError("execution id drift")
    if execution.get("matrixRow") != "RUE-DIAL-001":
        raise ValueError("execution must remain bound to RUE-DIAL-001")
    if execution.get("status") != "runnable-candidate":
        raise ValueError("execution status must remain runnable-candidate until promotion review")
    if execution.get("entrypoint") != "org.mcc0nnell.baudot.harness.RueOneStageDialAroundProbe":
        raise ValueError("execution entrypoint drift")
    if execution.get("runner") != "scripts/run-rue-one-stage-dial-around.sh":
        raise ValueError("execution runner drift")

    result = load_properties(RESULT)
    expected_true = {
        "rue.inboundTargetPreserved",
        "rue.inboundToPreserved",
        "rue.inboundSourcePreserved",
        "providerA.forwardedTargetPreserved",
        "providerB.inviteObserved",
        "providerB.targetPreserved",
        "providerB.toPreserved",
        "providerB.sourcePreserved",
        "providerB.ackObserved",
        "rue.final200Observed",
        "rue.ackObservedByDefaultProvider",
        "dialog.established",
    }
    failed_true = sorted(key for key in expected_true if result.get(key) != "true")
    if failed_true:
        raise ValueError(f"live route facts not true: {failed_true}")

    expected_false = {
        "media.offered",
        "media.readiness.proven",
        "rtt.readiness.proven",
        "video.readiness.proven",
    }
    failed_false = sorted(key for key in expected_false if result.get(key) != "false")
    if failed_false:
        raise ValueError(f"claim-boundary facts not false: {failed_false}")

    if result.get("expected.requestUri") != EXPECTED_TARGET:
        raise ValueError("selected-provider Request-URI drift")
    if result.get("default.provider.domain") != EXPECTED_DEFAULT:
        raise ValueError("default-provider domain drift")
    if result.get("selected.provider.domain") != EXPECTED_SELECTED:
        raise ValueError("selected-provider domain drift")
    if result.get("transport.claim") != "loopback-udp-harness-only":
        raise ValueError("harness transport must remain explicitly non-production")
    if result.get("claim") != "rfc9248-one-stage-dial-around-route-semantics-only":
        raise ValueError("live claim scope drift")
    if result.get("scenario.result") != "PASS":
        raise ValueError("RUE-DIAL-001 live execution did not pass")

    print("✓ RUE-DIAL-001 live route semantics independently reduced: PASS")
    print("  selected provider: provider-b.example")
    print("  media/RTT/video readiness: deliberately unproven")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
