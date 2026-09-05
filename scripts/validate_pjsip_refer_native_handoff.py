#!/usr/bin/env python3
"""Reduce JAIN SIP -> PJSIP native-media BAUDOT-INTEROP-004 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

EXPECTED_COMMIT = "5a457451fa2712ba18e12b01738e8ff3af2b26fd"
EXPECTED = {
    "scenario.id": "BAUDOT-INTEROP-004",
    "correlation.id": "jain-to-pjsip-native-handoff-v1",
    "arm.id": "positive-native-pjsip",
    "provider.sourceImplementation": "JAIN-SIP",
    "provider.targetImplementation": "pjsip/pjproject-2.17",
    "refer.accepted": "true",
    "notify.final.observed": "true",
    "notify.final.subscriptionTerminated": "true",
    "replacement.dialog.established": "true",
    "replacement.target.correlated": "true",
    "rtt.negotiated": "true",
    "rtt.readinessToken.observed": "true",
    "firstT140CharacterObserved": "UNCLASSIFIED_BY_JAVA",
    "rttReady": "EXTERNAL_BAUDOT_REFERENCE_TOKEN",
    "oldLeg.bye.sent": "true",
    "oldLeg.bye.observed": "true",
    "oldLeg.bye.afterReadinessToken": "true",
    "scenarioResult": "PASS",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_properties(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        key, sep, value = raw.partition("=")
        if not sep:
            raise ValueError(f"malformed property line: {raw!r}")
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
    types: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            types.append(str(json.loads(raw).get("type", "")))
    return types


def validate(out: Path) -> dict[str, object]:
    run = out / "jain-to-pjsip-native-handoff"
    readiness = out / "readiness"

    admission = json.loads((out / "pjsip-admission.json").read_text(encoding="utf-8"))
    if admission.get("repository") != "pjsip/pjproject":
        raise ValueError("unexpected PJSIP repository")
    if admission.get("release") != "2.17" or admission.get("commit") != EXPECTED_COMMIT:
        raise ValueError("unexpected PJSIP release/commit")
    if admission.get("cleanCheckout") is not True:
        raise ValueError("PJSIP checkout was not clean")

    values = read_properties(run / "result.properties")
    for key, expected in EXPECTED.items():
        actual = values.get(key)
        if actual != expected:
            raise ValueError(f"{key}: expected {expected!r}, observed {actual!r}")

    require_contains(
        run / "replacement-invite.request.sip",
        ("content-type: application/sdp", "m=text 5313", "a=rtpmap:98 t140/1000"),
    )
    require_contains(
        run / "replacement-response-200.sip",
        ("content-type: application/sdp", "m=text ", "t140/1000"),
    )
    require_contains(run / "replacement-ack.request.sip", ("ack ", "cseq: 1 ack"))
    require_contains(
        run / "notify-200.request.sip",
        (
            "event: refer",
            "subscription-state: terminated",
            "content-type: message/sipfrag",
            "sip/2.0 200",
        ),
    )
    require_contains(run / "old-leg-bye-sent.request.sip", ("bye ",))
    require_contains(run / "old-leg-bye-observed.request.sip", ("bye ",))

    gate = json.loads((readiness / "result.json").read_text(encoding="utf-8"))
    if gate.get("result") != "PASS" or gate.get("rttReady") is not True:
        raise ValueError("live RTT readiness gate did not pass")
    token = gate.get("readiness") or {}
    if token.get("semanticAuthority") != "baudot-reference":
        raise ValueError("unexpected readiness semantic authority")
    if token.get("payloadType") != 98 or token.get("firstT140Text") != "H":
        raise ValueError("unexpected readiness payload/text")

    gate_token = (readiness / "rtt-ready.json").read_bytes()
    jain_token = (run / "rtt-ready.token.json").read_bytes()
    if gate_token != jain_token:
        raise ValueError("JAIN did not preserve the exact readiness token it consumed")

    packet_name = token.get("packet")
    if not isinstance(packet_name, str):
        raise ValueError("readiness token lacks packet name")
    packet_path = readiness / packet_name
    if not packet_path.is_file():
        raise ValueError("qualifying native PJSIP packet was not preserved")
    if sha256(packet_path) != token.get("packetSha256"):
        raise ValueError("readiness token packet hash does not match preserved bytes")

    events = event_types(run / "events.jsonl")
    try:
        readiness_index = events.index("refer.rtt.readiness_token_observed")
        bye_index = events.index("old_leg.bye.sent")
    except ValueError as exc:
        raise ValueError("missing readiness-token or old-leg BYE event") from exc
    if readiness_index >= bye_index:
        raise ValueError("old leg was released before independent semantic readiness")
    if "old_leg.preserved" in events:
        raise ValueError("positive native-media arm preserved the old leg")

    log = (out / "pjsip.stdout.log").read_text(encoding="utf-8", errors="strict")
    markers = (
        "PJSIP_NATIVE_T140_UAS_READY release=2.17",
        "PJSIP_NATIVE_T140_UAS_INCOMING",
        "PJSIP_NATIVE_T140_UAS_ANSWER_REQUESTED textCount=1",
        "PJSIP_NATIVE_T140_UAS_TEXT_MEDIA_ACTIVE",
        "PJSIP_NATIVE_T140_UAS_SEND_REQUESTED text=H",
        "PJSIP_NATIVE_T140_UAS_TEXT_SENT",
        "PJSIP_NATIVE_T140_UAS_COMPLETION_SIGNAL_OBSERVED",
        "PJSIP_NATIVE_T140_UAS_COMPLETE",
    )
    positions: dict[str, int] = {}
    for marker in markers:
        pos = log.find(marker)
        if pos < 0:
            raise ValueError(f"missing PJSIP observation marker: {marker}")
        positions[marker] = pos
    if positions["PJSIP_NATIVE_T140_UAS_TEXT_MEDIA_ACTIVE"] >= positions[
        "PJSIP_NATIVE_T140_UAS_SEND_REQUESTED text=H"
    ]:
        raise ValueError("PJSIP text send was not after native text media activation")
    if positions["PJSIP_NATIVE_T140_UAS_TEXT_SENT"] >= positions[
        "PJSIP_NATIVE_T140_UAS_COMPLETION_SIGNAL_OBSERVED"
    ]:
        raise ValueError("PJSIP cleanup signal preceded native text send")

    terminal = {
        "scenarioId": "BAUDOT-INTEROP-004",
        "correlationId": "jain-to-pjsip-native-handoff-v1",
        "result": "PASS",
        "implementations": {
            "signalingInstrument": "JAIN-SIP",
            "replacementNativeMedia": {
                "repository": "pjsip/pjproject",
                "release": "2.17",
                "commit": EXPECTED_COMMIT,
            },
        },
        "referAccepted": True,
        "replacementDialogEstablished": True,
        "rttNegotiated": True,
        "readiness": {
            "semanticAuthority": "baudot-reference",
            "firstT140Text": "H",
            "payloadType": 98,
            "packet": packet_name,
            "packetSha256": token["packetSha256"],
            "rttReady": True,
        },
        "oldLegReleasedAfterIndependentReadiness": True,
        "claimBoundary": {
            "nativePjsipReplacementMediaObserved": True,
            "controlledReferHandoffObserved": True,
            "sipConformance": False,
            "rfc4103Conformance": False,
            "t140Conformance": False,
            "pjsipConformance": False,
            "vrsConformance": False,
            "productionVrsReadiness": False,
        },
    }
    terminal_path = run / "terminal-result.json"
    terminal_path.write_text(
        json.dumps(terminal, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return terminal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        terminal = validate(args.out)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"PJSIP native REFER handoff reduction failed: {exc}", file=sys.stderr)
        return 2
    print("✓ JAIN SIP -> PJSIP native-media BAUDOT-INTEROP-004 reduced to PASS")
    print("  REFER -> PJSIP dialog -> native T.140 -> Baudot semantic token -> old-leg release")
    print(f"  firstT140Text={terminal['readiness']['firstT140Text']!r} rttReady=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
