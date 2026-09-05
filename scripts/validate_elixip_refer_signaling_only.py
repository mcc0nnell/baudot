#!/usr/bin/env python3
"""Reduce the JAIN SIP -> Elixip signaling-only BAUDOT-INTEROP-004 arm."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


EXPECTED = {
    "scenario.id": "BAUDOT-INTEROP-004",
    "correlation.id": "jain-to-elixip-signaling-only-v1",
    "arm.id": "signaling-only",
    "provider.sourceImplementation": "JAIN-SIP",
    "provider.targetImplementation": "Elixip",
    "refer.accepted": "true",
    "notify.final.observed": "true",
    "notify.final.subscriptionTerminated": "true",
    "replacement.dialog.established": "true",
    "replacement.target.correlated": "true",
    "rtt.negotiated": "true",
    "rtt.observationWindow.complete": "true",
    "rtt.datagram.observed": "false",
    "oldLeg.bye.sent": "false",
    "oldLeg.bye.observed": "false",
    "rttReady": "false",
    "scenarioResult": "PASS",
}


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


def validate(run_dir: Path, elixip_log: Path) -> dict[str, str]:
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
        ("m=text ", "a=rtpmap:98 t140/1000", "content-type: application/sdp"),
    )
    require_contains(
        run_dir / "replacement-response-200.sip",
        ("m=text ", "a=rtpmap:98 t140/1000", "content-type: application/sdp"),
    )
    require_contains(
        run_dir / "replacement-ack.request.sip",
        ("ack sip:", "cseq: 1 ack"),
    )
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
        raise ValueError("signaling-only arm preserved an unexpected RTT datagram")

    events = (run_dir / "events.jsonl").read_text(encoding="utf-8")
    if "refer.rtt.observation_timeout" not in events:
        raise ValueError("bounded no-packet observation event is missing")
    if "old_leg.preserved" not in events:
        raise ValueError("old-leg preservation event is missing")

    if not elixip_log.is_file():
        raise ValueError(f"missing external Elixip log: {elixip_log}")
    log = elixip_log.read_text(encoding="utf-8", errors="strict")
    if "BAUDOT-ELIXIP replacementAckObserved=true" not in log:
        raise ValueError("Elixip did not independently record replacement ACK receipt")

    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--elixip-log", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        values = validate(args.run_dir, args.elixip_log)
    except (OSError, ValueError) as exc:
        print(f"Elixip REFER reduction failed: {exc}", file=sys.stderr)
        return 2
    print("✓ JAIN SIP -> Elixip signaling-only transfer reduced to PASS")
    print("  replacement SIP established on both sides; T.140 absent; original leg preserved")
    print(f"  correlation={values['correlation.id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
