#!/usr/bin/env python3
"""Reduce BAUDOT-TTY-005 controlled jitter/reordering evidence."""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

try:
    from .tty_pcmu_rtp import read_rtp_sequence
    from .reduce_tty_v18_wiretap_udp import inspect_packets
except ImportError:
    from tty_pcmu_rtp import read_rtp_sequence
    from reduce_tty_v18_wiretap_udp import inspect_packets


def read_ascii(path: Path) -> str:
    return path.read_bytes().decode("ascii")


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def reduce_run(run_dir: Path) -> dict[str, object]:
    source_text = read_ascii(run_dir / "source.txt")
    case = run_dir / "jitter-reorder-recovery"
    pre_packets = read_rtp_sequence(case / "pre-route.rtpseq")
    post_packets = read_rtp_sequence(case / "post-route.rtpseq")
    resequenced_packets = read_rtp_sequence(case / "resequenced.rtpseq")
    delay_index = int((case / "delayed-index.txt").read_text(encoding="utf-8").strip())
    delay_ms = float((case / "delay-ms.txt").read_text(encoding="utf-8").strip())
    if not 0 <= delay_index < len(pre_packets) - 1:
        raise ValueError(f"invalid recorded delay index: {delay_index}")

    pre = inspect_packets(case / "pre-route.rtpseq")
    post = inspect_packets(case / "post-route.rtpseq")
    resequenced = inspect_packets(case / "resequenced.rtpseq")
    sender = read_json(case / "sender.json")
    receiver = read_json(case / "receiver.json")
    resequence = read_json(case / "resequence.json")
    raw_exit_code = int((case / "raw-reconstruct.exit-code.txt").read_text(encoding="utf-8").strip())
    decoded = read_ascii(case / "decoded.txt")

    delayed_sequence = struct.unpack_from("!H", pre_packets[delay_index], 2)[0]
    following_sequence = struct.unpack_from("!H", pre_packets[delay_index + 1], 2)[0]
    arrival_sequences = [int(value) for value in post["sequenceNumbers"]]
    sender_sequences = [int(value) for value in sender["sentSequenceNumbers"]]
    receiver_sequences = [int(value) for value in receiver["sequenceNumbers"]]

    sender_inverted = (
        sender_sequences.index(following_sequence) < sender_sequences.index(delayed_sequence)
    )
    receiver_inverted = (
        arrival_sequences.index(following_sequence) < arrival_sequences.index(delayed_sequence)
    )

    checks = {
        "preRouteProfileMatches": pre["headerProfileMatches"],
        "postRouteProfileMatches": post["headerProfileMatches"],
        "packetCountPreserved": len(pre_packets) == len(post_packets),
        "datagramSetPreserved": sorted(pre_packets) == sorted(post_packets),
        "senderScheduledFollowingPacketFirst": sender_inverted,
        "receiverObservedFollowingPacketFirst": receiver_inverted,
        "receiverEvidenceMatchesPreservedArrivalOrder": receiver_sequences == arrival_sequences,
        "arrivalOrderContinuityRejected": not post["sequenceProgression"],
        "rawReconstructionRejected": raw_exit_code != 0,
        "resequencerChangedOrder": bool(resequence["changedOrder"]),
        "resequencedProfileMatches": resequenced["headerProfileMatches"],
        "resequencedSequenceProgression": resequenced["sequenceProgression"],
        "resequencedTimestampProgression": resequenced["timestampProgression"],
        "resequencedStreamRestoredExactly": pre_packets == resequenced_packets,
        "decodedTextMatchesAfterResequencing": decoded == source_text,
    }
    passed = all(checks.values())

    return {
        "scenario": "BAUDOT-TTY-005",
        "description": (
            "controlled send jitter delays one RTP packet until the following packet is sent first; "
            "live arrival order is preserved as evidence, raw reconstruction rejects it, and deterministic "
            "RTP resequencing restores the exact stream before TTY decode"
        ),
        "sourceText": source_text,
        "delayIndex": delay_index,
        "configuredDelayMs": delay_ms,
        "delayedSequence": delayed_sequence,
        "followingSequence": following_sequence,
        "preRoute": pre,
        "arrivalOrder": post,
        "resequenced": resequenced,
        "arrivalTiming": {
            "arrivalOffsetsMs": receiver.get("arrivalOffsetsMs", []),
            "interarrivalMs": receiver.get("interarrivalMs", []),
        },
        "decodedTextAfterResequencing": decoded,
        "checks": checks,
        "terminalVerdict": "pass" if passed else "fail",
        "claimBoundary": (
            "One bounded deterministic jitter/reordering case over the controlled Wiretap UDP topology; "
            "not a general jitter-buffer, WAN, SBC, PSTN, or V.18 tolerance claim."
        ),
    }


def main(argv: list[str]) -> int:
    run_dir = Path(argv[1]) if len(argv) > 1 else Path("target/evidence-routed/tty-v18-jitter")
    result = reduce_run(run_dir)
    output = run_dir / "tty-jitter-validation.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["terminalVerdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
