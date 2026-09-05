#!/usr/bin/env python3
"""Independently validate PJSIP/PJMEDIA-native RFC 2198 T.140 redundancy."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from baudot_reference.rfc2198 import Rfc2198T140Packet
from baudot_reference.rfc4103 import PrimaryT140RtpPacket
from baudot_reference.rfc4103_recovery import recover_forward_gap

SCENARIO = "PJSIP-NATIVE-RFC2198"
CORRELATION = "pjsip-2.17-native-red-v1"
EXPECTED_COMMIT = "5a457451fa2712ba18e12b01738e8ff3af2b26fd"
RED_PT = 100
T140_PT = 98


def load_properties(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        key, sep, value = raw.partition("=")
        if not sep:
            raise ValueError(f"malformed properties line: {raw!r}")
        values[key] = value
    return values


def require(values: dict[str, str], key: str, expected: str) -> None:
    actual = values.get(key)
    if actual != expected:
        raise ValueError(f"expected {key}={expected}, got {actual!r}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def payload_type(content: bytes) -> int:
    if len(content) < 2:
        raise ValueError("RTP evidence packet is too short")
    return content[1] & 0x7F


def main() -> None:
    root = Path(os.environ.get("BAUDOT_EVIDENCE_ROOT", "target/evidence-external"))
    run_root = root / SCENARIO / CORRELATION
    receiver = run_root / "jain-red-receiver"
    terminal = run_root / "terminal"

    props = load_properties(receiver / "result.properties")
    for key, expected in {
        "implementation": "pjsip/pjproject",
        "implementation.release": "2.17",
        "sip.invite.observed": "true",
        "sip.text.offered": "true",
        "sip.t140.offered": "true",
        "sip.red.offered": "true",
        "sip.red.fmtpOffered": "true",
        "sip.ack.observed": "true",
        "rtt.datagram.minimumTwoObserved": "true",
        "rfc2198Observed": "UNCLASSIFIED_BY_JAVA",
        "lossRecovered": "UNCLASSIFIED_BY_JAVA",
    }.items():
        require(props, key, expected)

    offer = (receiver / "pjsip-offer.sdp").read_text(encoding="utf-8").lower()
    answer = (receiver / "baudot-answer.sdp").read_text(encoding="utf-8").lower()
    for needle in ("m=text ", "rtp/avp 100 98", "rtpmap:100 red/1000", "fmtp:100 98/98/98", "rtpmap:98 t140/1000"):
        if needle not in offer:
            raise ValueError(f"PJSIP offer missing native RED profile element: {needle}")
        if needle not in answer:
            raise ValueError(f"Baudot answer missing selected RED profile element: {needle}")

    admission_path = run_root / "pjsip-admission.json"
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    if admission.get("repository") != "pjsip/pjproject":
        raise ValueError("unexpected PJSIP repository identity")
    if admission.get("release") != "2.17" or admission.get("commit") != EXPECTED_COMMIT:
        raise ValueError("unexpected PJSIP release/commit identity")
    if admission.get("cleanCheckout") is not True:
        raise ValueError("PJSIP checkout was not clean at admission")
    if admission.get("redundancyLevel") != 2:
        raise ValueError("native RED admission did not pin redundancy level 2")

    stdout = (run_root / "pjsip.stdout.log").read_text(encoding="utf-8")
    for marker in (
        "PJSIP_NATIVE_RFC2198_START release=2.17",
        "redundancyLevel=2",
        "PJSIP_NATIVE_RFC2198_CALL_CONFIRMED",
        "PJSIP_NATIVE_RFC2198_TEXT_MEDIA_ACTIVE",
        "PJSIP_NATIVE_RFC2198_SEND_REQUESTED text=H",
        "PJSIP_NATIVE_RFC2198_COMPLETE",
    ):
        if marker not in stdout:
            raise ValueError(f"missing native RED sender marker: {marker}")

    packet_paths = sorted(receiver.glob("rtt-datagram-*.bin"))
    if len(packet_paths) < 2:
        raise ValueError("expected at least two PJSIP-originated RTT datagrams")

    direct_candidates: list[tuple[Path, PrimaryT140RtpPacket]] = []
    red_candidates: list[tuple[Path, Rfc2198T140Packet]] = []
    packet_summary: list[dict[str, object]] = []

    for path in packet_paths:
        content = path.read_bytes()
        pt = payload_type(content)
        if pt == T140_PT:
            packet = PrimaryT140RtpPacket.from_bytes(content, expected_payload_type=T140_PT)
            direct_candidates.append((path, packet))
            packet_summary.append({
                "file": path.name,
                "sha256": sha256(path),
                "payloadType": pt,
                "kind": "direct-t140",
                "sequenceNumber": packet.sequence_number,
                "text": packet.block.text,
            })
        elif pt == RED_PT:
            packet = Rfc2198T140Packet.from_bytes(
                content,
                expected_red_payload_type=RED_PT,
                expected_t140_payload_type=T140_PT,
            )
            red_candidates.append((path, packet))
            packet_summary.append({
                "file": path.name,
                "sha256": sha256(path),
                "payloadType": pt,
                "kind": "rfc2198-red",
                "sequenceNumber": packet.sequence_number,
                "primaryText": packet.primary.text,
                "redundantTexts": [item.block.text for item in packet.redundant],
                "timestampOffsets": [item.timestamp_offset for item in packet.redundant],
            })
        else:
            raise ValueError(f"unexpected native text payload type {pt} in {path.name}")

    direct_h = next(
        ((path, packet) for path, packet in direct_candidates if packet.block.text == "H"),
        None,
    )
    if direct_h is None:
        raise ValueError("native PJSIP stream did not preserve direct T.140 'H' control packet")
    direct_path, direct_packet = direct_h

    recovery_match: tuple[Path, Rfc2198T140Packet, tuple] | None = None
    prior_sequence = (direct_packet.sequence_number - 1) % (1 << 16)
    for path, red_packet in red_candidates:
        recovered = recover_forward_gap(prior_sequence, red_packet)
        if any(
            item.sequence_number == direct_packet.sequence_number
            and item.source == "redundant"
            and item.block.text == "H"
            for item in recovered
        ):
            recovery_match = (path, red_packet, recovered)
            break

    if recovery_match is None:
        raise ValueError("no native PJSIP RED packet recovered the deliberately dropped direct 'H'")

    red_path, red_packet, recovered = recovery_match
    recovered_h = next(
        item for item in recovered
        if item.sequence_number == direct_packet.sequence_number and item.source == "redundant"
    )

    terminal.mkdir(parents=True, exist_ok=True)
    result = {
        "scenarioId": SCENARIO,
        "correlationId": CORRELATION,
        "result": "PASS",
        "implementation": {
            "repository": "pjsip/pjproject",
            "release": "2.17",
            "commit": EXPECTED_COMMIT,
            "mediaImplementation": "PJMEDIA text stream via PJSUA2 Call::sendText",
            "configuredRedundancyLevel": 2,
        },
        "negotiation": {
            "redPayloadType": RED_PT,
            "t140PayloadType": T140_PT,
            "clockRate": 1000,
            "fmtp": "98/98/98",
            "nativeTextMediaActive": True,
        },
        "wireObservation": {
            "packetCount": len(packet_paths),
            "packets": packet_summary,
            "directControlPacket": direct_path.name,
            "qualifyingRedPacket": red_path.name,
            "rfc2198Observed": True,
        },
        "lossSimulation": {
            "model": "drop direct PT98 packet after previous sequence, then consume later PT100 RED packet",
            "droppedSequenceNumber": direct_packet.sequence_number,
            "recoveredSequenceNumber": recovered_h.sequence_number,
            "recoveredText": recovered_h.block.text,
            "recoverySource": recovered_h.source,
            "lossRecovered": True,
        },
        "claimBoundary": {
            "nativePjsipRfc2198EmissionObserved": True,
            "controlledSinglePacketRecoveryObserved": True,
            "sipConformance": False,
            "rfc2198Conformance": False,
            "rfc4103Conformance": False,
            "t140Conformance": False,
            "productionVrsReadiness": False,
        },
    }
    result_path = terminal / "pjsip-native-rfc2198.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest_entries = [
        (result_path, "pjsip-native-rfc2198.json"),
        (admission_path, "../pjsip-admission.json"),
        (receiver / "pjsip-offer.sdp", "../jain-red-receiver/pjsip-offer.sdp"),
        (receiver / "baudot-answer.sdp", "../jain-red-receiver/baudot-answer.sdp"),
    ]
    manifest_entries.extend((path, f"../jain-red-receiver/{path.name}") for path in packet_paths)
    (terminal / "manifest.sha256").write_text(
        "".join(f"{sha256(path)}  {label}\n" for path, label in manifest_entries),
        encoding="utf-8",
    )

    print("✓ PJSIP 2.17 negotiated native RFC 2198/T.140 redundancy")
    print("✓ independent RED parser observed native PT100 redundancy")
    print("✓ deliberate loss of direct PT98 'H' recovered from later native RED generation")
    print(f"evidence: {result_path}")


if __name__ == "__main__":
    main()
