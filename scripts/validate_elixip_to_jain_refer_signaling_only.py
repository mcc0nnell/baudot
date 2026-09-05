#!/usr/bin/env python3
"""Reduce the Elixip -> JAIN SIP signaling-only BAUDOT-INTEROP-004 arm."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


EXPECTED = {
    "scenario.id": "BAUDOT-INTEROP-004",
    "correlation.id": "elixip-to-jain-signaling-only-v1",
    "arm.id": "signaling-only",
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
    "rtt.observationWindow.complete": "true",
    "rtt.datagram.observed": "false",
    "oldLeg.bye.sent": "false",
    "rttReady": "false",
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
        ("refer ", "refer-to: <sip:provider-b@127.0.0.1:5283"),
    )
    require_contains(run_dir / "refer-202.response.sip", ("sip/2.0 202", "cseq:"))
    require_contains(
        run_dir / "replacement-invite.request.sip",
        ("content-type: application/sdp", "m=text 42640", "a=rtpmap:98 t140/1000"),
    )
    require_contains(
        run_dir / "replacement-response-200.sip",
        ("content-type: application/sdp", "m=text 42641", "a=rtpmap:98 t140/1000"),
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

    unexpected = run_dir / "unexpected-rtt-datagram.bin"
    if unexpected.exists():
        raise ValueError("signaling-only reverse arm preserved an unexpected RTT datagram")

    events = load_events(run_dir / "events.jsonl")
    event_types = [str(event.get("type", "")) for event in events]
    if "refer.rtt.observation_timeout" not in event_types:
        raise ValueError("bounded no-packet observation event is missing")
    if "old_leg.preserved" not in event_types:
        raise ValueError("JAIN transfer processor did not preserve old-leg decision evidence")
    if "provider_b.ack.observed" not in event_types:
        raise ValueError("controlled replacement endpoint did not observe replacement ACK")
    if "reverse.unexpected_readiness" in event_types:
        raise ValueError("reverse arm recorded unexpected readiness")

    log = elixip_log.read_text(encoding="utf-8", errors="strict")
    markers = [
        "BAUDOT-ELIXIP originalDialogEstablished=true",
        "BAUDOT-ELIXIP referSent=true target=sip:provider-b@127.0.0.1:5283",
        "BAUDOT-ELIXIP referAccepted=true",
        "BAUDOT-ELIXIP terminalNotifyObserved=true",
        "BAUDOT-ELIXIP oldLegPreserved=true",
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
        "correlationId": "elixip-to-jain-signaling-only-v1",
        "sourceImplementation": "Elixip",
        "transferImplementation": "JAIN-SIP",
        "originalDialogEstablished": True,
        "referSentByElixip": True,
        "referAccepted": True,
        "terminalNotifyObservedByElixip": True,
        "replacementDialogEstablished": True,
        "replacementAckObserved": True,
        "rttNegotiated": True,
        "firstT140CharacterObserved": False,
        "boundedObservationCompleted": True,
        "rttReady": False,
        "oldLegPreservedByJainDecision": True,
        "oldLegObservedPreservedByElixip": True,
        "result": "PASS",
        "claimBoundary": {
            "sipConformance": False,
            "referConformance": False,
            "rfc4103Conformance": False,
            "t140Conformance": False,
            "productionVrsReadiness": False,
        },
    }
    terminal_path = run_dir / "terminal-result.json"
    terminal_path.write_text(
        json.dumps(terminal, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_path = run_dir / "terminal.manifest.sha256"
    manifest_path.write_text(
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
        print(f"Elixip -> JAIN REFER reduction failed: {exc}", file=sys.stderr)
        return 2
    print("✓ Elixip -> JAIN SIP signaling-only transfer reduced to PASS")
    print("  transfer signaling complete; bounded T.140 absence; original Elixip leg preserved")
    print(f"  correlation={terminal['correlationId']} rttReady=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
