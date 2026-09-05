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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run_dir = args.run_dir
    scenario = run_dir.parent.name

    caller = run_dir / "caller"
    callee = run_dir / "callee"

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

    evidence = {
        "schema": "baudot.rtt-transport-evidence/v1",
        "scenario": scenario,
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
        "presentation": presentation.as_dict(),
        "claimBoundary": {
            "doesNotEstablish": [
                "full RFC 3261 conformance",
                "full RFC 4103 conformance",
                "full T.140 conformance",
                "RTCP behavior",
                "out-of-order recovery",
                "browser or WebRTC interoperability",
                "production network readiness",
            ]
        },
        "verdict": "pass",
    }

    output = run_dir / "rtt-validation.json"
    output.write_text(json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("✓ RTT bytes preserved and independently validated as RFC 4103/RFC 2198 T.140")
    print("✓ presentation: 'Hi' (missing-text markers: 0)")


if __name__ == "__main__":
    main()
