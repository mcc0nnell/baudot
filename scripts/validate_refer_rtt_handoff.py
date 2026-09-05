#!/usr/bin/env python3
"""Independently validate replacement-leg RTT readiness for BAUDOT-INTEROP-004."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from baudot_reference.rfc4103 import PrimaryT140RtpPacket

ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "target" / "evidence" / "BAUDOT-INTEROP-004" / "jain-live-refer-rtt-v1"
CONTROL = RUN_ROOT / "control"
SIGNALING_ONLY = RUN_ROOT / "signaling-only"
TERMINAL = RUN_ROOT / "terminal"


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


def require(values: dict[str, str], key: str, expected: str, label: str) -> None:
    actual = values.get(key)
    if actual != expected:
        raise ValueError(f"{label}: expected {key}={expected}, got {actual!r}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    control = load_properties(CONTROL / "result.properties")
    signaling = load_properties(SIGNALING_ONLY / "result.properties")

    for label, values in (("control", control), ("signaling-only", signaling)):
        require(values, "signaling.transfer.complete", "true", label)
        require(values, "refer.accepted", "true", label)
        require(values, "notify.final.observed", "true", label)
        require(values, "replacement.dialog.established", "true", label)
        require(values, "replacement.target.correlated", "true", label)
        require(values, "rtt.negotiated", "true", label)

    control_packet_path = CONTROL / "rtt-datagram-received.bin"
    if not control_packet_path.exists():
        raise ValueError("control: replacement-leg RTT datagram was not preserved")
    packet = PrimaryT140RtpPacket.from_bytes(
        control_packet_path.read_bytes(), expected_payload_type=98
    )
    if packet.block.is_empty:
        raise ValueError("control: preserved T140block is empty")
    if packet.block.text != "H":
        raise ValueError(f"control: expected canonical first T.140 character 'H', got {packet.block.text!r}")

    require(control, "rtt.datagram.observed", "true", "control")
    require(control, "rtt.canonicalBytesMatched", "true", "control")
    require(control, "oldLeg.bye.sent", "true", "control")
    require(control, "oldLeg.bye.observed", "true", "control")
    require(control, "oldLeg.bye.afterRttObservation", "true", "control")

    if (SIGNALING_ONLY / "rtt-datagram-received.bin").exists():
        raise ValueError("signaling-only: unexpected RTT datagram evidence exists")
    require(signaling, "rtt.datagram.observed", "false", "signaling-only")
    require(signaling, "rtt.canonicalBytesMatched", "false", "signaling-only")
    require(signaling, "oldLeg.bye.sent", "false", "signaling-only")
    require(signaling, "oldLeg.bye.observed", "false", "signaling-only")

    control_rtt_ready = True
    signaling_rtt_ready = False

    result = {
        "scenarioId": "BAUDOT-INTEROP-004",
        "correlationId": "jain-live-refer-rtt-v1",
        "validator": "baudot_reference.rfc4103.PrimaryT140RtpPacket",
        "control": {
            "referAccepted": True,
            "replacementDialogEstablished": True,
            "rttNegotiated": True,
            "firstT140CharacterObserved": True,
            "firstT140Text": packet.block.text,
            "rttReady": control_rtt_ready,
            "oldLegReleasedAfterRttObservation": True,
            "packetSha256": sha256(control_packet_path),
        },
        "signalingOnly": {
            "referAccepted": True,
            "replacementDialogEstablished": True,
            "rttNegotiated": True,
            "firstT140CharacterObserved": False,
            "rttReady": signaling_rtt_ready,
            "oldLegReleased": False,
        },
        "invariant": "REFER/NOTIFY/replacement-dialog success does not imply RTT readiness",
        "result": "PASS",
        "claimBoundary": {
            "sipConformance": False,
            "rfc4103Conformance": False,
            "t140Conformance": False,
            "productionVrsReadiness": False,
        },
    }

    TERMINAL.mkdir(parents=True, exist_ok=True)
    result_path = TERMINAL / "refer-rtt-readiness.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = TERMINAL / "manifest.sha256"
    manifest_path.write_text(
        f"{sha256(result_path)}  refer-rtt-readiness.json\n"
        f"{sha256(control_packet_path)}  ../control/rtt-datagram-received.bin\n",
        encoding="utf-8",
    )

    print("✓ BAUDOT-INTEROP-004 control: signaling + independently parsed T.140 => rttReady=true")
    print("✓ BAUDOT-INTEROP-004 signaling-only: signaling succeeds, no T.140 => rttReady=false")
    print(f"evidence: {result_path}")


if __name__ == "__main__":
    main()
