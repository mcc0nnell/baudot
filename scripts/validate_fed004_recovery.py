#!/usr/bin/env python3
"""Independently reduce BAUDOT-FED-004 controlled RFC 2198 recovery evidence."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from baudot_reference import PrimaryT140RtpPacket, Rfc2198T140Packet, recover_forward_gap
from scripts.run_federation_boundary import read_properties
from scripts.validate_fed002_browser import validate_browser_evidence


@dataclass(frozen=True, slots=True)
class Fed004Result:
    sip_dialog_established: bool
    interpreter_received_media: bool
    controlled_omission_declared: bool
    omitted_sequence_absent: bool
    gateway_received_two: bool
    gateway_forwarded_two: bool
    raw_forwarding_identical: bool
    prior_primary_valid: bool
    recovery_carrier_valid: bool
    independent_recovery_valid: bool
    gateway_recovery_matches_reference: bool
    no_missing_marker_emitted: bool
    browser_ready: bool
    semantic_text_equal: bool
    gateway_media_termination_declared: bool
    expected_text: str | None
    browser_text: str | None
    recovered_sources: tuple[str, ...]
    terminal_verdict: str
    failed_facts: tuple[str, ...]


def validate(evidence_root: Path, *, correlation: str) -> Fed004Result:
    sip_base = evidence_root / "BAUDOT-FED-004" / correlation
    caller_dir = sip_base / "caller"
    interpreter_dir = sip_base / "callee"
    gateway_dir = evidence_root / "gateway"

    gateway_result = json.loads((gateway_dir / "gateway-result.json").read_text(encoding="utf-8"))
    loss_plan = json.loads((caller_dir / "rtt-loss-plan.json").read_text(encoding="utf-8"))
    caller = read_properties(caller_dir / "result.properties")
    interpreter = read_properties(interpreter_dir / "result.properties")

    sip_dialog_established = caller.get("signaling.dialog.established") == "true"
    interpreter_received_media = interpreter.get("media.probe.received") == "true"
    controlled_omission_declared = (
        loss_plan.get("injection") == "controlled-source-omission"
        and loss_plan.get("emittedSequenceNumbers") == [0, 2]
        and loss_plan.get("omittedSequenceNumbers") == [1]
        and loss_plan.get("omittedT140Text") == "B"
        and loss_plan.get("recoveryCarrierSequence") == 2
    )

    gateway_meta = gateway_result.get("gateway", {})
    gateway_received_two = gateway_meta.get("datagramsReceived") == 2
    gateway_forwarded_two = gateway_meta.get("datagramsForwarded") == 2
    gateway_media_termination_declared = gateway_meta.get("mediaTerminates") is True

    gateway_packets = [
        (gateway_dir / f"rtt-datagram-{index}-received.bin").read_bytes()
        for index in (1, 2)
    ]
    interpreter_packets = [
        (interpreter_dir / f"rtt-datagram-{index}-received.bin").read_bytes()
        for index in (1, 2)
    ]
    raw_forwarding_identical = gateway_packets == interpreter_packets

    prior_primary_valid = False
    recovery_carrier_valid = False
    independent_recovery_valid = False
    omitted_sequence_absent = False
    expected_text: str | None = None
    recovered_sources: tuple[str, ...] = ()
    reference_blocks: list[dict[str, object]] = []
    try:
        prior = PrimaryT140RtpPacket.from_bytes(gateway_packets[0], expected_payload_type=98)
        carrier = Rfc2198T140Packet.from_bytes(
            gateway_packets[1],
            expected_red_payload_type=99,
            expected_t140_payload_type=98,
        )
        prior_primary_valid = (
            prior.sequence_number == 0
            and prior.timestamp == 700
            and prior.block.text == "A"
        )
        recovery_carrier_valid = (
            carrier.sequence_number == 2
            and carrier.timestamp == 1300
            and len(carrier.redundant) == 1
            and carrier.redundant[0].timestamp_offset == 300
            and carrier.redundant[0].block.text == "B"
            and carrier.primary.text == "C"
        )
        omitted_sequence_absent = prior.sequence_number == 0 and carrier.sequence_number == 2
        recovered = recover_forward_gap(prior.sequence_number, carrier)
        recovered_sources = tuple(block.source for block in recovered)
        reference_blocks = [
            {
                "sequenceNumber": block.sequence_number,
                "text": block.block.text,
                "source": block.source,
            }
            for block in recovered
        ]
        expected_text = prior.block.text + "".join(block.block.text for block in recovered)
        independent_recovery_valid = (
            expected_text == "ABC"
            and [(block.sequence_number, block.block.text, block.source) for block in recovered]
            == [(1, "B", "redundant"), (2, "C", "primary")]
        )
    except ValueError:
        pass

    gateway_blocks = gateway_meta.get("emittedBlocks")
    gateway_recovery_matches_reference = (
        isinstance(gateway_blocks, list)
        and gateway_blocks == [
            {"sequenceNumber": 0, "text": "A", "source": "primary"},
            *reference_blocks,
        ]
        and gateway_meta.get("recoveredFromRedundancyCount") == 1
    )
    no_missing_marker_emitted = gateway_meta.get("missingMarkerCount") == 0

    browser_result = validate_browser_evidence(gateway_result.get("browser", {}))
    browser_ready = browser_result.terminal_verdict == "ready"
    browser_text = browser_result.decoded_text
    semantic_text_equal = expected_text is not None and browser_text == expected_text

    facts = {
        "sipDialogEstablished": sip_dialog_established,
        "interpreterReceivedMedia": interpreter_received_media,
        "controlledOmissionDeclared": controlled_omission_declared,
        "omittedSequenceAbsent": omitted_sequence_absent,
        "gatewayReceivedTwo": gateway_received_two,
        "gatewayForwardedTwo": gateway_forwarded_two,
        "rawForwardingIdentical": raw_forwarding_identical,
        "priorPrimaryValid": prior_primary_valid,
        "recoveryCarrierValid": recovery_carrier_valid,
        "independentRecoveryValid": independent_recovery_valid,
        "gatewayRecoveryMatchesReference": gateway_recovery_matches_reference,
        "noMissingMarkerEmitted": no_missing_marker_emitted,
        "browserReady": browser_ready,
        "semanticTextEqual": semantic_text_equal,
        "gatewayMediaTerminationDeclared": gateway_media_termination_declared,
    }
    failed_facts = tuple(sorted(name for name, value in facts.items() if not value))
    return Fed004Result(
        sip_dialog_established=sip_dialog_established,
        interpreter_received_media=interpreter_received_media,
        controlled_omission_declared=controlled_omission_declared,
        omitted_sequence_absent=omitted_sequence_absent,
        gateway_received_two=gateway_received_two,
        gateway_forwarded_two=gateway_forwarded_two,
        raw_forwarding_identical=raw_forwarding_identical,
        prior_primary_valid=prior_primary_valid,
        recovery_carrier_valid=recovery_carrier_valid,
        independent_recovery_valid=independent_recovery_valid,
        gateway_recovery_matches_reference=gateway_recovery_matches_reference,
        no_missing_marker_emitted=no_missing_marker_emitted,
        browser_ready=browser_ready,
        semantic_text_equal=semantic_text_equal,
        gateway_media_termination_declared=gateway_media_termination_declared,
        expected_text=expected_text,
        browser_text=browser_text,
        recovered_sources=recovered_sources,
        terminal_verdict="ready" if not failed_facts else "not-ready",
        failed_facts=failed_facts,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, default=Path("target/evidence/fed004"))
    parser.add_argument("--correlation", default="fed004-red-loss-recovery")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = validate(args.evidence_root, correlation=args.correlation)
    payload = asdict(result)
    payload["failed_facts"] = list(result.failed_facts)
    payload["recovered_sources"] = list(result.recovered_sources)
    payload["claimBoundary"] = (
        "controlled source omission with deterministic RFC 2198 recovery into real Chromium; "
        "not full RFC4103/RFC2198/WebRTC/SIP conformance or production VRS interoperability"
    )
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result.terminal_verdict == "ready" else 6


if __name__ == "__main__":
    raise SystemExit(main())
