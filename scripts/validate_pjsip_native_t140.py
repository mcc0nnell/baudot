#!/usr/bin/env python3
"""Independently validate a PJSIP/PJMEDIA-native T.140 wire observation."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from baudot_reference.rfc4103 import PrimaryT140RtpPacket

SCENARIO = "PJSIP-NATIVE-T140"
CORRELATION = "pjsip-2.17-native-text-v1"
EXPECTED_COMMIT = "5a457451fa2712ba18e12b01738e8ff3af2b26fd"


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


def require(values: dict[str, str], key: str, expected: str) -> None:
    actual = values.get(key)
    if actual != expected:
        raise ValueError(f"expected {key}={expected}, got {actual!r}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    root = Path(os.environ.get("BAUDOT_EVIDENCE_ROOT", "target/evidence-external"))
    run_root = root / SCENARIO / CORRELATION
    receiver = run_root / "jain-receiver"
    terminal = run_root / "terminal"

    props = load_properties(receiver / "result.properties")
    require(props, "implementation", "pjsip/pjproject")
    require(props, "implementation.release", "2.17")
    require(props, "sip.invite.observed", "true")
    require(props, "sip.text.offered", "true")
    require(props, "sip.t140.offered", "true")
    require(props, "sip.ack.observed", "true")
    require(props, "rtt.datagram.observed", "true")
    require(props, "firstT140CharacterObserved", "UNCLASSIFIED_BY_JAVA")
    require(props, "rttReady", "UNCLASSIFIED_BY_JAVA")

    offer = (receiver / "pjsip-offer.sdp").read_text(encoding="utf-8").lower()
    answer = (receiver / "baudot-answer.sdp").read_text(encoding="utf-8").lower()
    if "m=text " not in offer or "t140/1000" not in offer:
        raise ValueError("PJSIP offer did not preserve a text/t140 media description")
    if "m=text " not in answer or "rtp/avp 98" not in answer or "t140/1000" not in answer:
        raise ValueError("Baudot answer did not select direct T.140 payload type 98")

    packets = sorted(receiver.glob("rtt-datagram-*.bin"))
    if not packets:
        raise ValueError("no PJSIP-originated RTT datagrams were preserved")

    parsed: list[dict[str, object]] = []
    first_nonempty: tuple[Path, PrimaryT140RtpPacket] | None = None
    for packet_path in packets:
        packet = PrimaryT140RtpPacket.from_bytes(
            packet_path.read_bytes(), expected_payload_type=98
        )
        parsed.append(
            {
                "file": packet_path.name,
                "sha256": sha256(packet_path),
                "text": packet.block.text,
                "empty": packet.block.is_empty,
            }
        )
        if first_nonempty is None and not packet.block.is_empty:
            first_nonempty = (packet_path, packet)

    if first_nonempty is None:
        raise ValueError("PJSIP emitted RTP but no non-empty T.140 block was observed")

    packet_path, packet = first_nonempty
    if packet.block.text != "H":
        raise ValueError(
            f"expected first PJSIP-native T.140 text 'H', got {packet.block.text!r}"
        )

    admission_path = run_root / "pjsip-admission.json"
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    if admission.get("repository") != "pjsip/pjproject":
        raise ValueError("unexpected PJSIP repository identity")
    if admission.get("release") != "2.17":
        raise ValueError("unexpected PJSIP release identity")
    if admission.get("commit") != EXPECTED_COMMIT:
        raise ValueError("unexpected PJSIP commit identity")
    if admission.get("cleanCheckout") is not True:
        raise ValueError("PJSIP checkout was not clean at admission")

    sender_stdout = (run_root / "pjsip.stdout.log").read_text(encoding="utf-8")
    for marker in (
        "PJSIP_NATIVE_T140_START release=2.17",
        "PJSIP_NATIVE_T140_CALL_CONFIRMED",
        "PJSIP_NATIVE_T140_SEND_REQUESTED text=H",
        "PJSIP_NATIVE_T140_COMPLETE",
    ):
        if marker not in sender_stdout:
            raise ValueError(f"missing native sender marker: {marker}")

    terminal.mkdir(parents=True, exist_ok=True)
    result = {
        "scenarioId": SCENARIO,
        "correlationId": CORRELATION,
        "implementation": {
            "repository": "pjsip/pjproject",
            "release": "2.17",
            "commit": EXPECTED_COMMIT,
            "mediaImplementation": "PJMEDIA text stream via PJSUA2 Call::sendText",
        },
        "negotiation": {
            "textOffered": True,
            "t140Offered": True,
            "selectedPayloadType": 98,
            "clockRate": 1000,
        },
        "wireObservation": {
            "packetCount": len(packets),
            "packets": parsed,
            "firstNonemptyPacket": packet_path.name,
            "firstT140Text": packet.block.text,
            "firstT140CharacterObserved": True,
        },
        "rttReady": True,
        "result": "PASS",
        "claimBoundary": {
            "nativePjsipTextEmissionObserved": True,
            "sipConformance": False,
            "rfc4103Conformance": False,
            "t140Conformance": False,
            "productionVrsReadiness": False,
        },
    }
    result_path = terminal / "pjsip-native-t140.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest_entries = [
        (result_path, "pjsip-native-t140.json"),
        (admission_path, "../pjsip-admission.json"),
        (receiver / "pjsip-offer.sdp", "../jain-receiver/pjsip-offer.sdp"),
        (receiver / "baudot-answer.sdp", "../jain-receiver/baudot-answer.sdp"),
    ]
    manifest_entries.extend(
        (path, f"../jain-receiver/{path.name}") for path in packets
    )
    manifest_path = terminal / "manifest.sha256"
    manifest_path.write_text(
        "".join(f"{sha256(path)}  {label}\n" for path, label in manifest_entries),
        encoding="utf-8",
    )

    print("✓ PJSIP 2.17 native PJMEDIA text emission observed on the wire")
    print("✓ independent RFC 4103 reference parsed first non-empty T.140 text as 'H'")
    print(f"evidence: {result_path}")


if __name__ == "__main__":
    main()
