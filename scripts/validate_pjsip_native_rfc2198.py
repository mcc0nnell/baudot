#!/usr/bin/env python3
"""Independently reduce native PJSIP/PJMEDIA RFC 2198/T.140 evidence."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from baudot_reference.rfc2198 import InvalidRedT140Packet, Rfc2198T140Packet
from baudot_reference.rfc4103 import PrimaryT140RtpPacket
from baudot_reference.rfc4103_recovery import (
    infer_redundant_sequence_numbers,
    recover_forward_gap,
)

SCENARIO = "PJSIP-NATIVE-RFC2198"
RED_PT = 100
T140_PT = 98
SEQUENCE_MODULUS = 1 << 16
VALID_OUTCOMES = {"recovery", "zero-length-history", "age-order-invalid"}


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
    correlation = os.environ["BAUDOT_PJSIP_RFC2198_CORRELATION"]
    expected_commit = os.environ["BAUDOT_PJSIP_EXPECTED_COMMIT"]
    profile = os.environ["BAUDOT_PJSIP_PROFILE_LABEL"]
    expected_outcome = os.environ["BAUDOT_PJSIP_EXPECT_OUTCOME"]
    if expected_outcome not in VALID_OUTCOMES:
        raise ValueError(f"unsupported expected outcome: {expected_outcome}")

    run_root = root / SCENARIO / correlation
    receiver = run_root / "jain-red-receiver"
    terminal = run_root / "terminal"

    props = load_properties(receiver / "result.properties")
    for key, expected in {
        "implementation": "pjsip/pjproject",
        "implementation.profile": profile,
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
    for needle in (
        "m=text ",
        "rtp/avp 100 98",
        "rtpmap:100 red/1000",
        "fmtp:100 98/98/98",
        "rtpmap:98 t140/1000",
    ):
        if needle not in offer:
            raise ValueError(f"PJSIP offer missing native RED profile element: {needle}")
        if needle not in answer:
            raise ValueError(f"Baudot answer missing selected RED profile element: {needle}")

    admission_path = run_root / "pjsip-admission.json"
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    if admission.get("repository") != "pjsip/pjproject":
        raise ValueError("unexpected PJSIP repository identity")
    if admission.get("commit") != expected_commit or admission.get("profile") != profile:
        raise ValueError("unexpected PJSIP profile/commit identity")
    if admission.get("cleanCheckout") is not True:
        raise ValueError("PJSIP checkout was not clean at admission")
    if admission.get("redundancyLevel") != 2:
        raise ValueError("native RED admission did not pin redundancy level 2")
    if admission.get("expectedOutcome") != expected_outcome:
        raise ValueError("admission expected outcome does not match reducer")

    stdout = (run_root / "pjsip.stdout.log").read_text(encoding="utf-8")
    for marker in (
        f"PJSIP_NATIVE_RFC2198_START profile={profile}",
        "redundancyLevel=2",
        "PJSIP_NATIVE_RFC2198_CALL_CONFIRMED",
        "PJSIP_NATIVE_RFC2198_TEXT_MEDIA_ACTIVE",
        "PJSIP_NATIVE_RFC2198_SEND_REQUESTED ordinal=1 text=H",
        "PJSIP_NATIVE_RFC2198_SEND_REQUESTED ordinal=2 text=I",
        "PJSIP_NATIVE_RFC2198_COMPLETE",
    ):
        if marker not in stdout:
            raise ValueError(f"missing native RED sender marker: {marker}")

    packet_paths = sorted(receiver.glob("rtt-datagram-*.bin"))
    if len(packet_paths) < 2:
        raise ValueError("expected at least two PJSIP-originated RTT datagrams")

    primary_by_sequence: dict[int, tuple[str, Path]] = {}
    red_candidates: list[tuple[Path, Rfc2198T140Packet]] = []
    strict_red_rejections: list[dict[str, str]] = []
    packet_summary: list[dict[str, object]] = []

    for path in packet_paths:
        content = path.read_bytes()
        pt = payload_type(content)
        if pt == T140_PT:
            packet = PrimaryT140RtpPacket.from_bytes(content, expected_payload_type=T140_PT)
            primary_by_sequence[packet.sequence_number] = (packet.block.text, path)
            packet_summary.append({
                "file": path.name,
                "sha256": sha256(path),
                "payloadType": pt,
                "kind": "direct-t140",
                "sequenceNumber": packet.sequence_number,
                "text": packet.block.text,
            })
        elif pt == RED_PT:
            try:
                packet = Rfc2198T140Packet.from_bytes(
                    content,
                    expected_red_payload_type=RED_PT,
                    expected_t140_payload_type=T140_PT,
                )
            except InvalidRedT140Packet as exc:
                rejection = str(exc)
                strict_red_rejections.append({
                    "file": path.name,
                    "sha256": sha256(path),
                    "reason": rejection,
                })
                packet_summary.append({
                    "file": path.name,
                    "sha256": sha256(path),
                    "payloadType": pt,
                    "kind": "rfc2198-red-rejected",
                    "strictParserAccepted": False,
                    "rejection": rejection,
                })
                continue

            red_candidates.append((path, packet))
            primary_by_sequence[packet.sequence_number] = (packet.primary.text, path)
            packet_summary.append({
                "file": path.name,
                "sha256": sha256(path),
                "payloadType": pt,
                "kind": "rfc2198-red",
                "strictParserAccepted": True,
                "sequenceNumber": packet.sequence_number,
                "primaryText": packet.primary.text,
                "redundantTexts": [item.block.text for item in packet.redundant],
                "redundantLengths": [len(item.block.payload) for item in packet.redundant],
                "timestampOffsets": [item.timestamp_offset for item in packet.redundant],
            })
        else:
            raise ValueError(f"unexpected native text payload type {pt} in {path.name}")

    if not red_candidates and not strict_red_rejections:
        raise ValueError("PJSIP negotiated RED but emitted no PT100 packet")

    recovery_match: dict[str, object] | None = None
    for red_path, red_packet in red_candidates:
        for sequence, generation in zip(
            infer_redundant_sequence_numbers(red_packet), red_packet.redundant, strict=True
        ):
            prior = primary_by_sequence.get(sequence)
            if prior is None:
                continue
            prior_text, prior_path = prior
            if not prior_text or generation.block.text != prior_text:
                continue

            previous_sequence = (sequence - 1) % SEQUENCE_MODULUS
            recovered = recover_forward_gap(previous_sequence, red_packet)
            matched = next(
                (
                    item for item in recovered
                    if item.sequence_number == sequence
                    and item.source == "redundant"
                    and item.block.text == prior_text
                ),
                None,
            )
            if matched is not None:
                recovery_match = {
                    "droppedPacket": prior_path.name,
                    "droppedSequenceNumber": sequence,
                    "droppedText": prior_text,
                    "qualifyingRedPacket": red_path.name,
                    "qualifyingRedSequenceNumber": red_packet.sequence_number,
                    "recoveredSequenceNumber": matched.sequence_number,
                    "recoveredText": matched.block.text,
                    "recoverySource": matched.source,
                }
                break
        if recovery_match is not None:
            break

    zero_length_redundancy = any(
        len(item.block.payload) == 0
        for _, packet in red_candidates
        for item in packet.redundant
    )
    age_order_rejections = [
        item for item in strict_red_rejections
        if "age order" in item["reason"].lower()
    ]

    if expected_outcome == "recovery":
        if strict_red_rejections:
            raise ValueError(
                "recovery profile emitted RED packet(s) rejected by the strict RFC2198/T.140 parser"
            )
        if recovery_match is None:
            raise ValueError("native PJSIP RED never recovered an earlier non-empty primary generation")
    elif expected_outcome == "zero-length-history":
        if recovery_match is not None:
            raise ValueError("zero-length baseline unexpectedly recovered text; limitation assumption is stale")
        if not zero_length_redundancy:
            raise ValueError("zero-length baseline did not reproduce empty RED history")
    elif expected_outcome == "age-order-invalid":
        if recovery_match is not None:
            raise ValueError("age-order limitation profile unexpectedly recovered text; assumption is stale")
        if not age_order_rejections:
            raise ValueError("expected strict age-order rejection was not reproduced")

    observed_limitation = expected_outcome != "recovery"
    terminal.mkdir(parents=True, exist_ok=True)
    result_name = "pjsip-native-rfc2198.json"
    result = {
        "scenarioId": SCENARIO,
        "correlationId": correlation,
        "result": "OBSERVED_LIMITATION" if observed_limitation else "PASS",
        "expectedOutcome": expected_outcome,
        "implementation": {
            "repository": "pjsip/pjproject",
            "profile": profile,
            "commit": expected_commit,
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
            "rfc2198PayloadTypeObserved": True,
            "strictRedParserRejectedPacketCount": len(strict_red_rejections),
            "strictRedParserRejections": strict_red_rejections,
            "zeroLengthRedundantGenerationObserved": zero_length_redundancy,
            "ageOrderViolationObserved": bool(age_order_rejections),
        },
        "lossSimulation": {
            "lossRecovered": recovery_match is not None,
            "recovery": recovery_match,
        },
        "claimBoundary": {
            "nativePjsipRfc2198PayloadObserved": True,
            "controlledSinglePacketRecoveryObserved": recovery_match is not None,
            "nativePjsipRfc2198RecoveryQualified": expected_outcome == "recovery",
            "sipConformance": False,
            "rfc2198Conformance": False,
            "rfc4103Conformance": False,
            "t140Conformance": False,
            "productionVrsReadiness": False,
        },
    }
    result_path = terminal / result_name
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest_entries = [
        (result_path, result_name),
        (admission_path, "../pjsip-admission.json"),
        (receiver / "pjsip-offer.sdp", "../jain-red-receiver/pjsip-offer.sdp"),
        (receiver / "baudot-answer.sdp", "../jain-red-receiver/baudot-answer.sdp"),
    ]
    manifest_entries.extend((path, f"../jain-red-receiver/{path.name}") for path in packet_paths)
    (terminal / "manifest.sha256").write_text(
        "".join(f"{sha256(path)}  {label}\n" for path, label in manifest_entries),
        encoding="utf-8",
    )

    if expected_outcome == "recovery":
        print("✓ native PJSIP profile emitted strict-parseable RFC2198/T.140 redundancy")
        print("✓ independent reducer recovered an earlier non-empty generation after simulated loss")
    elif expected_outcome == "zero-length-history":
        print("✓ PJSIP profile reproduced native PT100 RED with zero-length history")
        print("✓ independent reducer correctly refused to claim text recovery")
    else:
        print("✓ PJSIP profile reproduced native PT100 RED rejected for RFC4103 age ordering")
        print("✓ strict parser remained authoritative; no recovery claim was made")
    print(f"evidence: {result_path}")


if __name__ == "__main__":
    main()
