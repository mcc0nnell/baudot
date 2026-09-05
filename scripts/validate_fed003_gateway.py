#!/usr/bin/env python3
"""Independently reduce BAUDOT-FED-003 inline RFC4103 -> WebRTC evidence."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from baudot_reference import PrimaryT140RtpPacket, Rfc2198T140Packet
from scripts.run_federation_boundary import read_properties
from scripts.validate_fed002_browser import validate_browser_evidence


@dataclass(frozen=True, slots=True)
class Fed003Result:
    sip_dialog_established: bool
    interpreter_received_media: bool
    gateway_received_two: bool
    gateway_forwarded_two: bool
    raw_forwarding_identical: bool
    direct_primary_valid: bool
    red_primary_valid: bool
    redundancy_not_duplicated: bool
    browser_ready: bool
    semantic_text_equal: bool
    gateway_media_termination_declared: bool
    expected_text: str | None
    browser_text: str | None
    terminal_verdict: str
    failed_facts: tuple[str, ...]


def validate(
    evidence_root: Path,
    *,
    correlation: str,
) -> Fed003Result:
    sip_base = evidence_root / "BAUDOT-FED-003" / correlation
    gateway_dir = evidence_root / "gateway"
    gateway_result = json.loads((gateway_dir / "gateway-result.json").read_text(encoding="utf-8"))

    caller = read_properties(sip_base / "caller" / "result.properties")
    interpreter = read_properties(sip_base / "callee" / "result.properties")

    sip_dialog_established = caller.get("signaling.dialog.established") == "true"
    interpreter_received_media = interpreter.get("media.probe.received") == "true"

    gateway_meta = gateway_result.get("gateway", {})
    gateway_received_two = gateway_meta.get("datagramsReceived") == 2
    gateway_forwarded_two = gateway_meta.get("datagramsForwarded") == 2
    gateway_media_termination_declared = gateway_meta.get("mediaTerminates") is True

    gateway_packets = [
        (gateway_dir / f"rtt-datagram-{index}-received.bin").read_bytes()
        for index in (1, 2)
    ]
    interpreter_packets = [
        (sip_base / "callee" / f"rtt-datagram-{index}-received.bin").read_bytes()
        for index in (1, 2)
    ]
    raw_forwarding_identical = gateway_packets == interpreter_packets

    direct_primary_valid = False
    red_primary_valid = False
    redundancy_not_duplicated = False
    expected_text: str | None = None
    try:
        direct = PrimaryT140RtpPacket.from_bytes(gateway_packets[0], expected_payload_type=98)
        red = Rfc2198T140Packet.from_bytes(
            gateway_packets[1],
            expected_red_payload_type=99,
            expected_t140_payload_type=98,
        )
        direct_primary_valid = direct.block.text == "H"
        red_primary_valid = red.primary.text == "i"
        expected_text = direct.block.text + red.primary.text
        redundancy_not_duplicated = (
            len(red.redundant) == 1
            and red.redundant[0].block.text == direct.block.text
            and expected_text == "Hi"
        )
    except ValueError:
        pass

    browser_result = validate_browser_evidence(gateway_result.get("browser", {}))
    browser_ready = browser_result.terminal_verdict == "ready"
    browser_text = browser_result.decoded_text
    semantic_text_equal = expected_text is not None and browser_text == expected_text

    facts = {
        "sipDialogEstablished": sip_dialog_established,
        "interpreterReceivedMedia": interpreter_received_media,
        "gatewayReceivedTwo": gateway_received_two,
        "gatewayForwardedTwo": gateway_forwarded_two,
        "rawForwardingIdentical": raw_forwarding_identical,
        "directPrimaryValid": direct_primary_valid,
        "redPrimaryValid": red_primary_valid,
        "redundancyNotDuplicated": redundancy_not_duplicated,
        "browserReady": browser_ready,
        "semanticTextEqual": semantic_text_equal,
        "gatewayMediaTerminationDeclared": gateway_media_termination_declared,
    }
    failed_facts = tuple(sorted(name for name, value in facts.items() if not value))
    return Fed003Result(
        sip_dialog_established=sip_dialog_established,
        interpreter_received_media=interpreter_received_media,
        gateway_received_two=gateway_received_two,
        gateway_forwarded_two=gateway_forwarded_two,
        raw_forwarding_identical=raw_forwarding_identical,
        direct_primary_valid=direct_primary_valid,
        red_primary_valid=red_primary_valid,
        redundancy_not_duplicated=redundancy_not_duplicated,
        browser_ready=browser_ready,
        semantic_text_equal=semantic_text_equal,
        gateway_media_termination_declared=gateway_media_termination_declared,
        expected_text=expected_text,
        browser_text=browser_text,
        terminal_verdict="ready" if not failed_facts else "not-ready",
        failed_facts=failed_facts,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, default=Path("target/evidence/fed003"))
    parser.add_argument("--correlation", default="fed003-rtt-webrtc-gateway")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = validate(args.evidence_root, correlation=args.correlation)
    payload = asdict(result)
    payload["failed_facts"] = list(result.failed_facts)
    payload["claimBoundary"] = (
        "runnable inline T.140 gateway evidence; not full RFC4103/RFC2198/WebRTC/SIP conformance "
        "and not production VRS interoperability"
    )
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result.terminal_verdict == "ready" else 6


if __name__ == "__main__":
    raise SystemExit(main())
