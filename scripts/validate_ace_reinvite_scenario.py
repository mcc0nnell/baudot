#!/usr/bin/env python3
"""Terminal reduction for all executable BAUDOT-INTEROP-003 gates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENARIO_ROOT = ROOT / "target" / "evidence" / "BAUDOT-INTEROP-003"
MESSAGE_RESULT = SCENARIO_ROOT / "jain-message-correlation-v1" / "jain-message-proof" / "result.properties"
OVERLAP_RESULT = SCENARIO_ROOT / "jain-live-overlap-v1" / "live-overlap" / "result.properties"
READINESS_RESULT = (
    SCENARIO_ROOT
    / "jain-live-rtt-readiness-v1"
    / "live-rtt-readiness"
    / "rtt-readiness-validation.json"
)
OUTPUT = SCENARIO_ROOT / "scenario-validation.json"
OUTPUT_SHA = SCENARIO_ROOT / "scenario-validation.json.sha256"


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def properties(path: Path) -> dict[str, str]:
    require(path.is_file(), f"missing gate result: {path}")
    output: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        require(bool(separator), f"malformed property line: {raw}")
        output[key.strip()] = value.strip()
    return output


def main() -> None:
    message = properties(MESSAGE_RESULT)
    overlap = properties(OVERLAP_RESULT)
    require(READINESS_RESULT.is_file(), f"missing readiness validation: {READINESS_RESULT}")
    readiness = json.loads(READINESS_RESULT.read_text(encoding="utf-8"))

    require(message.get("scenario.result") == "PASS", "message-correlation gate failed")
    require(message.get("external.response.bound") == "true", "external SDP response lost request correlation")
    require(message.get("external.sdp.bound") == "true", "external SDP was not bound to its declared request")
    require(message.get("stale.sdp.detected") == "true", "message gate did not detect stale SDP")

    require(overlap.get("scenario.result") == "PASS", "live-overlap gate failed")
    require(overlap.get("dialog.established") == "true", "live dialog was not established")
    require(overlap.get("live.dialog.overlap.proven") == "true", "live overlap was not proven")
    require(overlap.get("glare.reinvite.status") == "491", "overlap did not produce 491 Request Pending")
    require(overlap.get("first.reinvite.status") == "200", "earlier pending re-INVITE did not complete with 200")

    require(readiness.get("scenarioResult") == "PASS", "live RTT readiness gate failed")
    control = readiness.get("control", {})
    stale = readiness.get("stale", {})
    require(control.get("sipStatus") == 200, "control re-INVITE did not return 200")
    require(control.get("rttNegotiated") is True, "control did not negotiate RTT")
    require(control.get("firstT140CharacterObserved") is True, "control did not observe first T.140 character")
    require(control.get("rttReady") is True, "control did not become RTT ready")
    require(stale.get("sipStatus") == 200, "stale re-INVITE did not preserve 200 signaling")
    require(stale.get("staleSdpDetected") is True, "live stale SDP was not detected")
    require(stale.get("rttNegotiated") is True, "stale answer did not still advertise RTT")
    require(stale.get("firstT140CharacterObserved") is False, "stale arm unexpectedly observed first T.140 character")
    require(stale.get("rttReady") is False, "stale arm unexpectedly became RTT ready")

    reduced = {
        "scenarioId": "BAUDOT-INTEROP-003",
        "status": "runnable",
        "terminalVerdict": "RUNNABLE_PASS",
        "gates": {
            "jainSipMessageCorrelation": "PASS",
            "jainSipLiveOverlap": "PASS",
            "jainSipLiveRttReadiness": "PASS",
        },
        "observedInvariants": {
            "overlappingRequestRemainsIndependentlyCorrelated": True,
            "glareProduces491WhilePriorInviteRemainsPending": True,
            "externallySuppliedSdpRemainsRequestBound": True,
            "staleSdpCanCoexistWithSip200": True,
            "sip200DoesNotImplyRttReady": True,
            "rttReadyRequiresNegotiationAndFirstT140Character": True,
        },
        "control": control,
        "stale": stale,
        "claimBoundary": {
            "portableScenarioRunnable": True,
            "scenarioProven": False,
            "fullSipConformance": False,
            "fullRfc4103Conformance": False,
            "fullT140Conformance": False,
            "productionVrsReadiness": False,
            "contemporaryAceDefectEstablished": False,
        },
    }

    encoded = (json.dumps(reduced, indent=2, sort_keys=True) + "\n").encode("utf-8")
    OUTPUT.write_bytes(encoded)
    digest = hashlib.sha256(encoded).hexdigest()
    OUTPUT_SHA.write_text(f"{digest}  {OUTPUT.name}\n", encoding="utf-8")
    print("✓ BAUDOT-INTEROP-003 terminal reduction: RUNNABLE_PASS")


if __name__ == "__main__":
    main()
