#!/usr/bin/env python3
"""Independently reduce the JAIN SIP -> Elixip positive BAUDOT-INTEROP-004 arm."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from baudot_reference.rfc4103 import PrimaryT140RtpPacket


EXPECTED = {
    "scenario.id": "BAUDOT-INTEROP-004",
    "correlation.id": "jain-to-elixip-positive-handoff-v1",
    "arm.id": "positive",
    "provider.sourceImplementation": "JAIN-SIP",
    "provider.targetImplementation": "Elixip",
    "refer.accepted": "true",
    "notify.final.observed": "true",
    "notify.final.subscriptionTerminated": "true",
    "replacement.dialog.established": "true",
    "replacement.target.correlated": "true",
    "rtt.negotiated": "true",
    "rtt.datagram.observed": "true",
    "rtt.canonicalBytesMatched": "true",
    "firstT140CharacterObserved": "UNCLASSIFIED_BY_JAVA",
    "rttReady": "UNCLASSIFIED_BY_JAVA",
    "oldLeg.bye.sent": "true",
    "oldLeg.bye.observed": "true",
    "oldLeg.bye.afterRttObservation": "true",
    "scenarioResult": "PASS",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_properties(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.lstrip().startswith("#"):
            continue
        if "=" not in raw:
            raise ValueError(f"malformed property line: {raw!r}")
        key, value = raw.split("=", 1)
        if key in values:
            raise ValueError(f"duplicate property: {key}")
        values[key] = value
    return values


def require_contains(path: Path, needles: tuple[str, ...]) -> None:
    text = path.read_text(encoding="utf-8", errors="strict").lower()
    for needle in needles:
        if needle.lower() not in text:
            raise ValueError(f"{path.name}: missing {needle!r}")


def event_types(path: Path) -> list[str]:
    result: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        event = json.loads(raw)
        result.append(str(event.get("type", "")))
    return result


def validate(run_dir: Path, elixip_log: Path) -> dict[str, object]:
    result_path = run_dir / "result.properties"
    if not result_path.is_file():
        raise ValueError(f"missing result.properties: {result_path}")
    values = read_properties(result_path)
    for key, expected in EXPECTED.items():
        actual = values.get(key)
        if actual != expected:
            raise ValueError(f"{key}: expected {expected!r}, observed {actual!r}")

    require_contains(
        run_dir / "replacement-invite.request.sip",
        ("content-type: application/sdp", "m=text 42630", "a=rtpmap:98 t140/1000"),
    )
    require_contains(
        run_dir / "replacement-response-200.sip",
        ("content-type: application/sdp", "m=text ", "a=rtpmap:98 t140/1000"),
    )
    require_contains(run_dir / "replacement-ack.request.sip", ("ack ", "cseq: 1 ack"))
    require_contains(
        run_dir / "notify-200.request.sip",
        (
            "event: refer",
            "subscription-state: terminated",
            "content-type: message/sipfrag",
            "sip/2.0 200",
        ),
    )
    require_contains(run_dir / "old-leg-bye-sent.request.sip", ("bye ",))
    require_contains(run_dir / "old-leg-bye-observed.request.sip", ("bye ",))

    packet_path = run_dir / "rtt-datagram-received.bin"
    if not packet_path.is_file():
        raise ValueError("replacement-leg RTT datagram was not preserved")
    packet = PrimaryT140RtpPacket.from_bytes(
        packet_path.read_bytes(), expected_payload_type=98
    )
    if packet.block.is_empty:
        raise ValueError("preserved T140block is empty")
    if packet.block.text != "H":
        raise ValueError(
            f"expected canonical first T.140 character 'H', got {packet.block.text!r}"
        )

    events = event_types(run_dir / "events.jsonl")
    try:
        rtt_index = events.index("refer.rtt.observed")
        bye_index = events.index("old_leg.bye.sent")
    except ValueError as exc:
        raise ValueError("missing RTT observation or old-leg release event") from exc
    if rtt_index >= bye_index:
        raise ValueError("old leg was released before preserved RTT observation")
    if "old_leg.preserved" in events:
        raise ValueError("positive arm preserved the old leg despite canonical RTT readiness")

    log = elixip_log.read_text(encoding="utf-8", errors="strict")
    ack_marker = "BAUDOT-ELIXIP replacementAckObserved=true"
    send_marker = "BAUDOT-ELIXIP canonicalT140DatagramSent=true"
    ack_index = log.find(ack_marker)
    send_index = log.find(send_marker)
    if ack_index < 0:
        raise ValueError("Elixip did not independently record replacement ACK receipt")
    if send_index < 0:
        raise ValueError("external scenario did not record canonical T.140 stimulus emission")
    if ack_index >= send_index:
        raise ValueError("canonical T.140 stimulus was not emitted after Elixip ACK observation")
    if "targetPort=42630" not in log[send_index:]:
        raise ValueError("external scenario did not follow JAIN's offered m=text port")

    terminal = {
        "scenarioId": "BAUDOT-INTEROP-004",
        "correlationId": "jain-to-elixip-positive-handoff-v1",
        "validator": "baudot_reference.rfc4103.PrimaryT140RtpPacket",
        "referAccepted": True,
        "replacementDialogEstablished": True,
        "replacementAckObservedByElixip": True,
        "rttNegotiated": True,
        "firstT140CharacterObserved": True,
        "firstT140Text": packet.block.text,
        "rttReady": True,
        "oldLegReleasedAfterRttObservation": True,
        "packetSha256": sha256(packet_path),
        "result": "PASS",
        "stimulusBoundary": (
            "canonical RTP/T.140 datagram emitted by Baudot-owned scenario after "
            "Elixip ACK observation; not native Elixip RFC4103 media"
        ),
        "claimBoundary": {
            "sipConformance": False,
            "rfc4103Conformance": False,
            "t140Conformance": False,
            "elixipNativeRfc4103Media": False,
            "productionVrsReadiness": False,
        },
    }
    terminal_path = run_dir / "terminal-result.json"
    terminal_path.write_text(
        json.dumps(terminal, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return terminal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--elixip-log", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        terminal = validate(args.run_dir, args.elixip_log)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Elixip positive REFER reduction failed: {exc}", file=sys.stderr)
        return 2
    print("✓ JAIN SIP -> Elixip positive handoff reduced to PASS")
    print("  Elixip ACK -> canonical T.140 bytes -> independent T.140 parse -> old-leg release")
    print(f"  firstT140Text={terminal['firstT140Text']!r} rttReady=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
