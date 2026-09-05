#!/usr/bin/env python3
"""Terminal reducer for the runnable BAUDOT-INTEROP-004 evidence chain."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.validate_refer_provider_matrix import load_fixture, validate_matrix

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "target" / "evidence" / "BAUDOT-INTEROP-004"
LIVE_SIGNALING = EVIDENCE / "jain-live-refer-v1" / "live-refer-transfer" / "result.properties"
RTT_RESULT = EVIDENCE / "jain-live-refer-rtt-v1" / "terminal" / "refer-rtt-readiness.json"
TERMINAL = EVIDENCE / "terminal"
FIXTURE = ROOT / "testkit" / "refer" / "provider-transfer-matrix.json"


def load_properties(path: Path) -> dict[str, str]:
    if not path.exists():
        raise ValueError(f"missing evidence: {path}")
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        key, sep, value = raw.partition("=")
        if not sep:
            raise ValueError(f"malformed property line in {path}: {raw!r}")
        values[key] = value
    return values


def require(values: dict[str, str], key: str, expected: str, label: str) -> None:
    actual = values.get(key)
    if actual != expected:
        raise ValueError(f"{label}: expected {key}={expected}, got {actual!r}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    # Re-run the deterministic matrix reducer as part of the terminal decision;
    # provider labels remain configuration and cannot change reduction semantics.
    validate_matrix(load_fixture())

    live = load_properties(LIVE_SIGNALING)
    require(live, "scenario.result", "PASS", "live-signaling")
    require(live, "live.referNotify.proven", "true", "live-signaling")
    require(live, "refer.accepted", "true", "live-signaling")
    require(live, "notify.final.observed", "true", "live-signaling")
    require(live, "replacement.dialog.established", "true", "live-signaling")
    require(live, "replacement.target.correlated", "true", "live-signaling")
    require(live, "oldLeg.terminatedAfterReplacementEstablished", "true", "live-signaling")

    if not RTT_RESULT.exists():
        raise ValueError(f"missing replacement readiness evidence: {RTT_RESULT}")
    readiness = json.loads(RTT_RESULT.read_text(encoding="utf-8"))
    if readiness.get("result") != "PASS":
        raise ValueError("replacement-leg readiness validator did not pass")

    control = readiness.get("control", {})
    signaling_only = readiness.get("signalingOnly", {})
    required_control = {
        "referAccepted": True,
        "replacementDialogEstablished": True,
        "rttNegotiated": True,
        "firstT140CharacterObserved": True,
        "rttReady": True,
        "oldLegReleasedAfterRttObservation": True,
    }
    for key, expected in required_control.items():
        if control.get(key) != expected:
            raise ValueError(f"control: expected {key}={expected!r}, got {control.get(key)!r}")

    required_failure = {
        "referAccepted": True,
        "replacementDialogEstablished": True,
        "rttNegotiated": True,
        "firstT140CharacterObserved": False,
        "rttReady": False,
        "oldLegReleased": False,
    }
    for key, expected in required_failure.items():
        if signaling_only.get(key) != expected:
            raise ValueError(
                f"signaling-only: expected {key}={expected!r}, got {signaling_only.get(key)!r}"
            )

    result = {
        "scenarioId": "BAUDOT-INTEROP-004",
        "status": "runnable",
        "terminalVerdict": "RUNNABLE_PASS",
        "providerMatrix": {
            "fixtureSha256": sha256(FIXTURE),
            "providerCount": 3,
            "directedPairCount": 6,
            "transferModes": ["blind", "warm"],
        },
        "liveTransfer": {
            "source": live.get("provider.source"),
            "target": live.get("provider.target"),
            "referAccepted": True,
            "notifyFinalObserved": True,
            "replacementDialogEstablished": True,
            "replacementTargetCorrelated": True,
            "oldLegTerminatedAfterReplacementEstablished": True,
            "resultSha256": sha256(LIVE_SIGNALING),
        },
        "replacementReadiness": {
            "controlRttReady": True,
            "signalingOnlyRttReady": False,
            "controlOldLegReleasedAfterRttObservation": True,
            "signalingOnlyOldLegPreserved": True,
            "resultSha256": sha256(RTT_RESULT),
        },
        "invariant": "successful REFER/NOTIFY/replacement-dialog signaling does not imply replacement accessibility readiness",
        "claimBoundary": {
            "sipConformance": False,
            "referConformance": False,
            "rfc4103Conformance": False,
            "t140Conformance": False,
            "externalProviderInteropProven": False,
            "productionVrsReadiness": False,
        },
    }

    TERMINAL.mkdir(parents=True, exist_ok=True)
    result_path = TERMINAL / "result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = TERMINAL / "manifest.sha256"
    manifest_path.write_text(
        f"{sha256(result_path)}  result.json\n"
        f"{sha256(FIXTURE)}  ../../../../testkit/refer/provider-transfer-matrix.json\n"
        f"{sha256(LIVE_SIGNALING)}  ../jain-live-refer-v1/live-refer-transfer/result.properties\n"
        f"{sha256(RTT_RESULT)}  ../jain-live-refer-rtt-v1/terminal/refer-rtt-readiness.json\n",
        encoding="utf-8",
    )

    print("✓ BAUDOT-INTEROP-004 terminalVerdict=RUNNABLE_PASS")
    print(f"evidence: {result_path}")


if __name__ == "__main__":
    main()
