#!/usr/bin/env python3
"""Reduce the Elixip -> JAIN SIP positive BAUDOT-INTEROP-004 handoff arm."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from baudot_reference.rfc4103 import PrimaryT140RtpPacket


EXPECTED = {
    "scenario.id": "BAUDOT-INTEROP-004",
    "correlation.id": "elixip-to-jain-positive-handoff-v1",
    "arm.id": "positive",
    "provider.sourceImplementation": "Elixip",
    "provider.transferImplementation": "JAIN-SIP",
    "original.dialog.ackObserved": "true",
    "refer.observed": "true",
    "refer.target.correlated": "true",
    "notify.final.acknowledged": "true",
    "replacement.dialog.established": "true",
    "replacement.target.inviteObserved": "true",
    "replacement.target.ackObserved": "true",
    "rtt.negotiated": "true",
    "rtt.datagram.observed": "true",
    "rtt.canonicalBytesMatched": "true",
    "firstT140CharacterObserved": "UNCLASSIFIED_BY_JAVA",
    "rttReady": "UNCLASSIFIED_BY_JAVA",
    "oldLeg.bye.sent": "true",
    "oldLeg.bye.completed": "true",
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


def load_events(path: Path) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            events.append(json.loads(raw))
    return events


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
        run_dir / "refer.request.sip",
        ("refer ", "refer-to: <sip:provider-b@127.0.0.1:5293"),
    )
    require_contains(run_dir / "refer-202.response.sip", ("sip/2.0 202", "cseq:"))
    require_contains(
        run_dir / "replacement-invite.request.sip",
        ("content-type: application/sdp", "m=text 42650", "a=rtpmap:98 t140/1000"),
    )
    require_contains(
        run_dir / "replacement-response-200.sip",
        ("content-type: application/sdp", "m=text 42651", "a=rtpmap:98 t140/1000"),
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
    require_contains(run_dir / "old-leg-bye-200.response.sip", ("sip/2.0 200", "cseq:"))

    sent_path = run_dir / "rtt-datagram-sent.bin"
    received_path = run_dir / "rtt-datagram-received.bin"
    if not sent_path.is_file() or not received_path.is_file():
        raise ValueError("positive reverse arm did not preserve sent and received RTT datagrams")
    if sent_path.read_bytes() != received_path.read_bytes():
        raise ValueError("received replacement RTT bytes differ from controlled provider-b stimulus")

    packet = PrimaryT140RtpPacket.from_bytes(
        received_path.read_bytes(), expected_payload_type=98
    )
    if packet.block.is_empty:
        raise ValueError("preserved T140block is empty")
    if packet.block.text != "H":
        raise ValueError(f"expected first T.140 text 'H', got {packet.block.text!r}")

    events = load_events(run_dir / "events.jsonl")
    event_types = [str(event.get("type", "")) for event in events]
    required_events = (
        "provider_b.ack.observed",
        "provider_b.rtt.sent",
        "refer.rtt.observed",
        "old_leg.bye.sent",
        "old_leg.bye.completed",
    )
    for event_type in required_events:
        if event_type not in event_types:
            raise ValueError(f"missing evidence event: {event_type}")
    if "old_leg.preserved" in event_types:
        raise ValueError("positive reverse arm preserved the old leg")
    if event_types.index("provider_b.ack.observed") >= event_types.index("refer.rtt.observed"):
        raise ValueError("RTT was observed before replacement ACK evidence")
    if event_types.index("refer.rtt.observed") >= event_types.index("old_leg.bye.sent"):
        raise ValueError("original leg was released before RTT observation")
    if event_types.index("old_leg.bye.sent") >= event_types.index("old_leg.bye.completed"):
        raise ValueError("old-leg completion event preceded BYE send evidence")

    log = elixip_log.read_text(encoding="utf-8", errors="strict")
    markers = [
        "BAUDOT-ELIXIP originalDialogEstablished=true",
        "BAUDOT-ELIXIP referSent=true target=sip:provider-b@127.0.0.1:5293",
        "BAUDOT-ELIXIP referAccepted=true",
        "BAUDOT-ELIXIP terminalNotifyObserved=true",
        "BAUDOT-ELIXIP oldLegReleased=true",
    ]
    positions: list[int] = []
    for marker in markers:
        position = log.find(marker)
        if position < 0:
            raise ValueError(f"Elixip observation marker missing: {marker}")
        positions.append(position)
    if positions != sorted(positions):
        raise ValueError("Elixip observation markers are out of expected order")

    terminal = {
        "scenarioId": "BAUDOT-INTEROP-004",
        "correlationId": "elixip-to-jain-positive-handoff-v1",
        "sourceImplementation": "Elixip",
        "transferImplementation": "JAIN-SIP",
        "originalDialogEstablished": True,
        "referSentByElixip": True,
        "referAccepted": True,
        "terminalNotifyObservedByElixip": True,
        "replacementDialogEstablished": True,
        "replacementAckObserved": True,
        "rttNegotiated": True,
        "firstT140CharacterObserved": True,
        "firstT140Text": packet.block.text,
        "rttReady": True,
        "oldLegReleasedAfterRttObservation": True,
        "oldLegReleaseObservedByElixip": True,
        "packetSha256": sha256(received_path),
        "result": "PASS",
        "stimulusBoundary": (
            "canonical RTP/T.140 datagram emitted by Baudot-owned controlled provider-b "
            "after replacement ACK; not native Elixip media"
        ),
        "claimBoundary": {
            "sipConformance": False,
            "referConformance": False,
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
    terminal_manifest = run_dir / "terminal.manifest.sha256"
    terminal_manifest.write_text(
        f"{sha256(terminal_path)}  terminal-result.json\n",
        encoding="utf-8",
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
        print(f"Elixip -> JAIN positive REFER reduction failed: {exc}", file=sys.stderr)
        return 2
    print("✓ Elixip -> JAIN SIP positive handoff reduced to PASS")
    print("  Elixip REFER -> replacement ACK -> T.140 'H' -> original-leg release")
    print(f"  correlation={terminal['correlationId']} rttReady=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
