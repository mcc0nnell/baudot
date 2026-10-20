#!/usr/bin/env python3
"""Reduce live Wiretap UDP evidence for BAUDOT-TTY-003/004."""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

try:
    from .tty_pcmu_rtp import read_rtp_sequence
except ImportError:
    from tty_pcmu_rtp import read_rtp_sequence

EXPECTED_PT = 0
EXPECTED_PAYLOAD_BYTES = 160
EXPECTED_TIMESTAMP_STEP = 160


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_ascii(path: Path) -> str:
    return path.read_bytes().decode("ascii")


def inspect_packets(path: Path) -> dict[str, object]:
    packets = read_rtp_sequence(path)
    parsed: list[dict[str, int]] = []
    for packet in packets:
        if len(packet) < 12:
            raise ValueError(f"{path}: RTP datagram shorter than fixed header")
        first, second, sequence, timestamp, ssrc = struct.unpack("!BBHII", packet[:12])
        csrc_count = first & 0x0F
        extension = (first >> 4) & 0x01
        if csrc_count != 0 or extension:
            raise ValueError(f"{path}: only fixed 12-byte RTP headers are admitted")
        parsed.append(
            {
                "version": first >> 6,
                "payloadType": second & 0x7F,
                "sequence": sequence,
                "timestamp": timestamp,
                "ssrc": ssrc,
                "payloadBytes": len(packet) - 12,
            }
        )

    if not parsed:
        raise ValueError(f"{path}: empty RTP sequence")

    progression = [
        (parsed[index]["sequence"] - parsed[index - 1]["sequence"]) & 0xFFFF
        for index in range(1, len(parsed))
    ]
    timestamp_steps = [
        (parsed[index]["timestamp"] - parsed[index - 1]["timestamp"]) & 0xFFFFFFFF
        for index in range(1, len(parsed))
    ]
    return {
        "sha256": sha256(path),
        "packetCount": len(parsed),
        "firstSequence": parsed[0]["sequence"],
        "lastSequence": parsed[-1]["sequence"],
        "firstTimestamp": parsed[0]["timestamp"],
        "lastTimestamp": parsed[-1]["timestamp"],
        "singleSsrc": len({item["ssrc"] for item in parsed}) == 1,
        "headerProfileMatches": all(
            item["version"] == 2
            and item["payloadType"] == EXPECTED_PT
            and item["payloadBytes"] == EXPECTED_PAYLOAD_BYTES
            for item in parsed
        ),
        "sequenceProgression": all(step == 1 for step in progression),
        "timestampProgression": all(step == EXPECTED_TIMESTAMP_STEP for step in timestamp_steps),
        "sequenceSteps": progression,
        "timestampSteps": timestamp_steps,
        "sequenceNumbers": [item["sequence"] for item in parsed],
    }


def reduce_clean_case(case_dir: Path, source_text: str) -> dict[str, object]:
    pre_path = case_dir / "pre-route.rtpseq"
    post_path = case_dir / "post-route.rtpseq"
    pre_packets = read_rtp_sequence(pre_path)
    post_packets = read_rtp_sequence(post_path)
    pre = inspect_packets(pre_path)
    post = inspect_packets(post_path)
    decoded = read_ascii(case_dir / "decoded.txt")

    checks = {
        "preRouteHeaderProfileMatches": pre["headerProfileMatches"],
        "postRouteHeaderProfileMatches": post["headerProfileMatches"],
        "postRouteSequenceProgression": post["sequenceProgression"],
        "postRouteTimestampProgression": post["timestampProgression"],
        "postRouteSingleSsrc": post["singleSsrc"],
        "packetCountPreserved": pre["packetCount"] == post["packetCount"],
        "datagramsPreservedExactly": pre_packets == post_packets,
        "decodedTextMatches": decoded == source_text,
    }
    return {
        "preRoute": pre,
        "postRoute": post,
        "decodedText": decoded,
        "checks": checks,
        "passed": all(checks.values()),
    }


def reduce_drop_case(case_dir: Path) -> dict[str, object]:
    pre_path = case_dir / "pre-route.rtpseq"
    post_path = case_dir / "post-route.rtpseq"
    pre_packets = read_rtp_sequence(pre_path)
    post_packets = read_rtp_sequence(post_path)
    drop_index = int((case_dir / "dropped-index.txt").read_text(encoding="utf-8").strip())
    if not 0 <= drop_index < len(pre_packets):
        raise ValueError(f"invalid recorded drop index: {drop_index}")

    expected_post = pre_packets[:drop_index] + pre_packets[drop_index + 1 :]
    pre = inspect_packets(pre_path)
    post = inspect_packets(post_path)
    dropped_sequence = struct.unpack_from("!H", pre_packets[drop_index], 2)[0]
    observed_sequence_steps = post["sequenceSteps"]
    gap_detected = any(step != 1 for step in observed_sequence_steps)
    decoded = read_ascii(case_dir / "decoded.txt") if (case_dir / "decoded.txt").exists() else ""

    checks = {
        "onePacketRemoved": len(pre_packets) - len(post_packets) == 1,
        "exactDeclaredDropObserved": post_packets == expected_post,
        "sequenceGapDetected": gap_detected,
        "cleanContinuityRejected": not post["sequenceProgression"],
    }
    return {
        "dropIndex": drop_index,
        "droppedSequence": dropped_sequence,
        "preRoute": pre,
        "postRoute": post,
        "decodedTextObserved": decoded,
        "checks": checks,
        "passed": all(checks.values()),
    }


def reduce_run(run_dir: Path) -> dict[str, object]:
    source_text = read_ascii(run_dir / "source.txt")
    min_to_span = reduce_clean_case(run_dir / "minimodem-to-spandsp", source_text)
    span_to_min = reduce_clean_case(run_dir / "spandsp-to-minimodem", source_text)
    drop = reduce_drop_case(run_dir / "drop-one-negative-control")

    tty003_pass = min_to_span["passed"] and span_to_min["passed"]
    tty004_pass = drop["passed"]
    passed = tty003_pass and tty004_pass

    return {
        "scenarios": {
            "BAUDOT-TTY-003": {
                "description": "PCMU RTP over live UDP through the routed Sandia Wiretap topology",
                "minimodemToSpanDsp": min_to_span,
                "spanDspToMinimodem": span_to_min,
                "terminalVerdict": "pass" if tty003_pass else "fail",
            },
            "BAUDOT-TTY-004": {
                "description": "negative control: exactly one RTP datagram intentionally omitted",
                "dropOne": drop,
                "terminalVerdict": "expected-impairment-detected" if tty004_pass else "fail",
            },
        },
        "sourceText": source_text,
        "terminalVerdict": "pass" if passed else "fail",
        "claimBoundary": (
            "Controlled local Wiretap/UDP qualification with deterministic PCMU RTP and one packet-loss negative control; "
            "not PSTN, SBC, arbitrary jitter/loss tolerance, hardware TTY, or V.18 conformance."
        ),
    }


def main(argv: list[str]) -> int:
    run_dir = Path(argv[1]) if len(argv) > 1 else Path("target/evidence-routed/tty-v18-wiretap")
    result = reduce_run(run_dir)
    output = run_dir / "tty-wiretap-validation.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["terminalVerdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
