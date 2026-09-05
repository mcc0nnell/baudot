#!/usr/bin/env python3
"""Validate RTT evidence without trusting the Java sender's protocol classification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from baudot_reference.rfc2198 import Rfc2198T140Packet
from baudot_reference.rfc4103 import PrimaryT140RtpPacket
from baudot_reference.rfc4103_recovery import (
    infer_redundant_sequence_numbers,
    recover_forward_gap,
)
from baudot_reference.t140 import apply_t140_baseline

T140_PT = 98
RED_PT = 99
CLOCK_RATE = 1000


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_properties(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        require(bool(separator) and bool(key), f"{path}: malformed property line: {raw!r}")
        values[key] = value
    return values


def validate_sdp(text: str, *, direction: str, label: str) -> dict[str, object]:
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    media = next((line for line in lines if line.startswith("m=text ")), None)
    require(media is not None, f"{label}: missing m=text media line")
    parts = media.split()
    require(len(parts) >= 5, f"{label}: malformed m=text media line")
    require(parts[2] == "RTP/AVP", f"{label}: expected RTP/AVP")
    require(parts[3:] == [str(RED_PT), str(T140_PT)], f"{label}: payload order must be RED then T.140")

    required = {
        f"a=rtpmap:{RED_PT} red/{CLOCK_RATE}",
        f"a=fmtp:{RED_PT} {T140_PT}/{T140_PT}/{T140_PT}",
        f"a=rtpmap:{T140_PT} t140/{CLOCK_RATE}",
        f"a={direction}",
    }
    missing = required - set(lines)
    require(not missing, f"{label}: missing SDP attributes: {sorted(missing)}")

    return {
        "media": "text",
        "protocol": "RTP/AVP",
        "redPayloadType": RED_PT,
        "t140PayloadType": T140_PT,
        "clockRate": CLOCK_RATE,
        "redundancy": [T140_PT, T140_PT, T140_PT],
        "direction": direction,
    }


def validate_normal(primary: PrimaryT140RtpPacket, red: Rfc2198T140Packet) -> dict[str, object]:
    require(primary.marker is True, "initial direct T.140 packet must carry the marker bit")
    require(primary.sequence_number == 1, "unexpected initial RTP sequence number")
    require(primary.timestamp == 1000, "unexpected initial RTP timestamp")
    require(primary.block.text == "H", "unexpected initial T140block")

    require(red.marker is False, "follow-up RED packet must not carry the initial marker bit")
    require(red.sequence_number == 2, "unexpected RED RTP sequence number")
    require(red.timestamp == 1300, "unexpected RED RTP timestamp")
    require(len(red.redundant) == 1, "expected one redundant generation")
    require(red.redundant[0].timestamp_offset == 300, "unexpected RED timestamp offset")
    require(red.redundant[0].block.text == "H", "redundant T140block does not match prior primary")
    require(red.primary.text == "i", "unexpected RED primary T140block")
    require(infer_redundant_sequence_numbers(red) == (1,), "RED history does not map back to RTP sequence 1")

    recovered = recover_forward_gap(primary.sequence_number, red)
    normalized_text = primary.block.text + "".join(item.block.text for item in recovered)
    presentation = apply_t140_baseline(ord(character) for character in normalized_text)
    require(presentation.display_text == "Hi", "normalized RTT presentation is not 'Hi'")
    require(presentation.missing_text_markers == 0, "normal RTT path introduced a missing-text marker")

    return {
        "presentation": presentation.as_dict(),
        "recovery": {
            "gapDetected": False,
            "recoveredSequenceNumbers": [],
            "sources": [item.source for item in recovered],
        },
    }


def validate_recovery(
    caller: Path,
    primary: PrimaryT140RtpPacket,
    red: Rfc2198T140Packet,
) -> dict[str, object]:
    plan_path = caller / "rtt-loss-plan.json"
    require(plan_path.is_file(), "recovery profile is missing rtt-loss-plan.json")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    require(plan.get("injection") == "controlled-source-omission", "unexpected recovery injection type")
    require(plan.get("emittedSequenceNumbers") == [0, 2], "recovery plan must emit RTP sequences 0 and 2")
    require(plan.get("omittedSequenceNumbers") == [1], "recovery plan must omit RTP sequence 1")
    require(plan.get("omittedTimestamp") == 1000, "recovery plan omitted timestamp must be 1000")
    require(plan.get("omittedT140Text") == "B", "recovery plan omitted T140block must be 'B'")
    require(plan.get("recoveryCarrierSequence") == 2, "RED recovery carrier must be RTP sequence 2")
    require(plan.get("redundantTimestampOffset") == 300, "RED recovery offset must be 300 ms")

    require(primary.marker is True, "recovery prior packet must carry the marker bit")
    require(primary.sequence_number == 0, "recovery prior RTP sequence must be 0")
    require(primary.timestamp == 700, "recovery prior RTP timestamp must be 700")
    require(primary.block.text == "A", "recovery prior T140block must be 'A'")

    require(red.marker is False, "recovery RED packet marker must be clear")
    require(red.sequence_number == 2, "recovery RED RTP sequence must be 2")
    require(red.timestamp == 1300, "recovery RED RTP timestamp must be 1300")
    require(len(red.redundant) == 1, "recovery RED packet must contain one redundant generation")
    require(red.redundant[0].timestamp_offset == 300, "recovery RED timestamp offset must be 300")
    require(red.redundant[0].block.text == "B", "redundant T140block must recover omitted 'B'")
    require(red.primary.text == "C", "recovery RED primary T140block must be 'C'")
    require(infer_redundant_sequence_numbers(red) == (1,), "RED history must map to omitted RTP sequence 1")

    recovered = recover_forward_gap(primary.sequence_number, red)
    require([item.sequence_number for item in recovered] == [1, 2], "recovery output must contain sequences 1 and 2")
    require([item.source for item in recovered] == ["redundant", "primary"], "missing sequence must be recovered from redundancy")
    require(recovered[0].block.text == "B", "recovered sequence 1 must contain 'B'")
    require(all(item.source != "missing-marker" for item in recovered), "recovery path introduced a missing-text marker source")

    normalized_text = primary.block.text + "".join(item.block.text for item in recovered)
    presentation = apply_t140_baseline(ord(character) for character in normalized_text)
    require(presentation.display_text == "ABC", "recovered RTT presentation is not 'ABC'")
    require(presentation.missing_text_markers == 0, "successful RED recovery introduced a missing-text marker")

    return {
        "presentation": presentation.as_dict(),
        "lossInjection": plan,
        "recovery": {
            "gapDetected": True,
            "previousSequenceNumber": 0,
            "observedNextSequenceNumber": 2,
            "missingSequenceNumbers": [1],
            "recoveredSequenceNumbers": [1],
            "sources": [item.source for item in recovered],
            "missingTextMarkers": 0,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run_dir = args.run_dir
    scenario = run_dir.parent.name

    caller = run_dir / "caller"
    callee = run_dir / "callee"
    caller_result = read_properties(caller / "result.properties")
    callee_result = read_properties(callee / "result.properties")
    profile = caller_result.get("rtt.profile", "normal")
    require(callee_result.get("rtt.profile", "normal") == profile, "caller/callee RTT profile mismatch")
    require(profile in {"normal", "recovery"}, f"unsupported RTT profile: {profile}")

    sent = [
        (caller / "rtt-datagram-1-sent.bin").read_bytes(),
        (caller / "rtt-datagram-2-sent.bin").read_bytes(),
    ]
    received = [
        (callee / "rtt-datagram-1-received.bin").read_bytes(),
        (callee / "rtt-datagram-2-received.bin").read_bytes(),
    ]
    require(sent == received, "RTT datagrams changed between sender and receiver evidence")
    require(len(sent) == 2, "expected exactly two RTT datagrams")

    offer = validate_sdp((callee / "offer.sdp").read_text(encoding="utf-8"), direction="sendonly", label="offer")
    answer = validate_sdp((caller / "answer.sdp").read_text(encoding="utf-8"), direction="recvonly", label="answer")

    observed_pts = [(packet[1] & 0x7F) for packet in received if len(packet) >= 2]
    require(observed_pts == [T140_PT, RED_PT], f"unexpected payload-type sequence: {observed_pts}")

    primary = PrimaryT140RtpPacket.from_bytes(received[0], expected_payload_type=T140_PT)
    red = Rfc2198T140Packet.from_bytes(
        received[1],
        expected_red_payload_type=RED_PT,
        expected_t140_payload_type=T140_PT,
    )

    semantic = validate_normal(primary, red) if profile == "normal" else validate_recovery(caller, primary, red)

    evidence: dict[str, object] = {
        "schema": "baudot.rtt-transport-evidence/v2",
        "scenario": scenario,
        "profile": profile,
        "validationAuthority": "baudot-python-reference",
        "wireBytesPreserved": True,
        "sdp": {"offer": offer, "answer": answer},
        "rtp": {
            "directPayloadType": primary.payload_type,
            "redPayloadType": red.red_payload_type,
            "sequence": [primary.sequence_number, red.sequence_number],
            "timestamps": [primary.timestamp, red.timestamp],
            "redundantSequenceNumbers": list(infer_redundant_sequence_numbers(red)),
            "redundantText": red.redundant[0].block.text,
            "primaryText": [primary.block.text, red.primary.text],
        },
        **semantic,
        "claimBoundary": {
            "doesNotEstablish": [
                "full RFC 3261 conformance",
                "full RFC 4103 conformance",
                "full T.140 conformance",
                "RTCP behavior",
                "out-of-order recovery",
                "browser or WebRTC interoperability",
                "production network readiness",
                "network-induced packet loss" if profile == "recovery" else "packet-loss recovery beyond the exercised path",
            ]
        },
        "verdict": "pass",
    }

    output = run_dir / "rtt-validation.json"
    output.write_text(json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if profile == "recovery":
        print("✓ controlled source omission created RTP sequence gap 0 → 2")
        print("✓ RFC 2198 recovered sequence 1 from redundancy: presentation 'ABC', missing markers 0")
    else:
        print("✓ RTT bytes preserved and independently validated as RFC 4103/RFC 2198 T.140")
        print("✓ presentation: 'Hi' (missing-text markers: 0)")


if __name__ == "__main__":
    main()
