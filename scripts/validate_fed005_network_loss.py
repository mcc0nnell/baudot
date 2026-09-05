#!/usr/bin/env python3
"""Independently reduce BAUDOT-FED-005 Wiretap-routed network-loss evidence."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from baudot_reference import PrimaryT140RtpPacket, Rfc2198T140Packet, recover_forward_gap
from scripts.validate_fed002_browser import validate_browser_evidence


@dataclass(frozen=True, slots=True)
class Fed005Result:
    source_emitted_all_three: bool
    source_sequence_one_valid: bool
    network_drop_declared: bool
    network_drop_counter_exactly_one: bool
    gateway_observed_loss: bool
    source_survivors_match_gateway: bool
    gateway_forwarded_two: bool
    sink_observed_degraded_stream: bool
    raw_forwarding_identical: bool
    independent_recovery_valid: bool
    gateway_recovery_matches_reference: bool
    no_missing_marker_emitted: bool
    browser_ready: bool
    semantic_text_equal: bool
    wiretap_route_declared: bool
    gateway_media_termination_declared: bool
    expected_text: str | None
    browser_text: str | None
    terminal_verdict: str
    failed_facts: tuple[str, ...]


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object at {path}")
    return value


def validate(run_dir: Path) -> Fed005Result:
    source_dir = run_dir / "source"
    gateway_dir = run_dir / "gateway"
    sink_dir = run_dir / "sink"

    source = _read_json(source_dir / "source-result.json")
    network = _read_json(run_dir / "network-loss-result.json")
    topology = _read_json(run_dir / "topology.json")
    gateway = _read_json(gateway_dir / "gateway-result.json")
    sink = _read_json(sink_dir / "sink-result.json")

    source_packets = [
        (source_dir / "rtt-seq-0-sent.bin").read_bytes(),
        (source_dir / "rtt-seq-1-sent.bin").read_bytes(),
        (source_dir / "rtt-seq-2-sent.bin").read_bytes(),
    ]
    gateway_packets = [
        (gateway_dir / "rtt-datagram-1-received.bin").read_bytes(),
        (gateway_dir / "rtt-datagram-2-received.bin").read_bytes(),
    ]
    sink_packets = [
        (sink_dir / "rtt-datagram-1-received.bin").read_bytes(),
        (sink_dir / "rtt-datagram-2-received.bin").read_bytes(),
    ]

    source_emitted_all_three = source.get("emittedSequenceNumbers") == [0, 1, 2]
    network_drop_declared = (
        network.get("mechanism") == "nftables-host-output-raw-rtp-sequence-match"
        and network.get("droppedSequenceNumber") == 1
        and network.get("destination") == topology.get("gatewayEndpoint")
    )
    network_drop_counter_exactly_one = network.get("droppedPackets") == 1
    wiretap_route_declared = (
        topology.get("transport") == "sandia-wiretap-v0.9.0"
        and topology.get("lossPoint") == "host-output-after-wiretap-server-reoriginates-udp"
        and topology.get("mediaNetwork") == "10.77.25.0/24"
        and topology.get("signalingNetwork") == "10.77.15.0/24"
        and topology.get("signalingResponseRouting") == "rfc3581-rport-over-transparent-flow"
    )

    source_sequence_one_valid = False
    independent_recovery_valid = False
    expected_text: str | None = None
    reference_blocks: list[dict[str, object]] = []
    try:
        seq0 = PrimaryT140RtpPacket.from_bytes(source_packets[0], expected_payload_type=98)
        seq1 = PrimaryT140RtpPacket.from_bytes(source_packets[1], expected_payload_type=98)
        seq2 = Rfc2198T140Packet.from_bytes(
            source_packets[2],
            expected_red_payload_type=99,
            expected_t140_payload_type=98,
        )
        source_sequence_one_valid = (
            seq1.sequence_number == 1
            and seq1.timestamp == 1000
            and seq1.block.text == "B"
        )
        recovered = recover_forward_gap(seq0.sequence_number, seq2)
        reference_blocks = [
            {"sequenceNumber": seq0.sequence_number, "text": seq0.block.text, "source": "primary"},
            *[
                {"sequenceNumber": block.sequence_number, "text": block.block.text, "source": block.source}
                for block in recovered
            ],
        ]
        expected_text = seq0.block.text + "".join(block.block.text for block in recovered)
        independent_recovery_valid = (
            seq0.sequence_number == 0
            and seq0.block.text == "A"
            and seq2.sequence_number == 2
            and len(seq2.redundant) == 1
            and seq2.redundant[0].block.text == "B"
            and seq2.primary.text == "C"
            and expected_text == "ABC"
            and reference_blocks
            == [
                {"sequenceNumber": 0, "text": "A", "source": "primary"},
                {"sequenceNumber": 1, "text": "B", "source": "redundant"},
                {"sequenceNumber": 2, "text": "C", "source": "primary"},
            ]
        )
    except ValueError:
        pass

    gateway_meta = gateway.get("gateway")
    if not isinstance(gateway_meta, dict):
        gateway_meta = {}
    gateway_sequences = [packet.get("sequenceNumber") for packet in gateway.get("inputDatagrams", []) if isinstance(packet, dict)]
    gateway_observed_loss = gateway_sequences == [0, 2]
    source_survivors_match_gateway = source_packets[0] == gateway_packets[0] and source_packets[2] == gateway_packets[1]
    gateway_forwarded_two = gateway_meta.get("datagramsForwarded") == 2
    gateway_media_termination_declared = gateway_meta.get("mediaTerminates") is True
    gateway_recovery_matches_reference = (
        gateway_meta.get("emittedBlocks") == reference_blocks
        and gateway_meta.get("recoveredFromRedundancyCount") == 1
    )
    no_missing_marker_emitted = gateway_meta.get("missingMarkerCount") == 0

    sink_observed_degraded_stream = sink.get("receivedSequenceNumbers") == [0, 2]
    raw_forwarding_identical = gateway_packets == sink_packets

    browser_result = validate_browser_evidence(gateway.get("browser", {}))
    browser_ready = browser_result.terminal_verdict == "ready"
    browser_text = browser_result.decoded_text
    semantic_text_equal = expected_text is not None and browser_text == expected_text

    facts = {
        "sourceEmittedAllThree": source_emitted_all_three,
        "sourceSequenceOneValid": source_sequence_one_valid,
        "networkDropDeclared": network_drop_declared,
        "networkDropCounterExactlyOne": network_drop_counter_exactly_one,
        "gatewayObservedLoss": gateway_observed_loss,
        "sourceSurvivorsMatchGateway": source_survivors_match_gateway,
        "gatewayForwardedTwo": gateway_forwarded_two,
        "sinkObservedDegradedStream": sink_observed_degraded_stream,
        "rawForwardingIdentical": raw_forwarding_identical,
        "independentRecoveryValid": independent_recovery_valid,
        "gatewayRecoveryMatchesReference": gateway_recovery_matches_reference,
        "noMissingMarkerEmitted": no_missing_marker_emitted,
        "browserReady": browser_ready,
        "semanticTextEqual": semantic_text_equal,
        "wiretapRouteDeclared": wiretap_route_declared,
        "gatewayMediaTerminationDeclared": gateway_media_termination_declared,
    }
    failed_facts = tuple(sorted(name for name, value in facts.items() if not value))
    return Fed005Result(
        source_emitted_all_three=source_emitted_all_three,
        source_sequence_one_valid=source_sequence_one_valid,
        network_drop_declared=network_drop_declared,
        network_drop_counter_exactly_one=network_drop_counter_exactly_one,
        gateway_observed_loss=gateway_observed_loss,
        source_survivors_match_gateway=source_survivors_match_gateway,
        gateway_forwarded_two=gateway_forwarded_two,
        sink_observed_degraded_stream=sink_observed_degraded_stream,
        raw_forwarding_identical=raw_forwarding_identical,
        independent_recovery_valid=independent_recovery_valid,
        gateway_recovery_matches_reference=gateway_recovery_matches_reference,
        no_missing_marker_emitted=no_missing_marker_emitted,
        browser_ready=browser_ready,
        semantic_text_equal=semantic_text_equal,
        wiretap_route_declared=wiretap_route_declared,
        gateway_media_termination_declared=gateway_media_termination_declared,
        expected_text=expected_text,
        browser_text=browser_text,
        terminal_verdict="ready" if not failed_facts else "not-ready",
        failed_facts=failed_facts,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = validate(args.run_dir)
    payload = asdict(result)
    payload["failed_facts"] = list(result.failed_facts)
    payload["claimBoundary"] = (
        "Wiretap-routed network-path loss with nftables fault injection and deterministic RFC 2198 recovery into real Chromium; "
        "not a Wiretap-native fault-injection feature, not reordering/timer proof, and not standards or production VRS conformance"
    )
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result.terminal_verdict == "ready" else 6


if __name__ == "__main__":
    raise SystemExit(main())
