#!/usr/bin/env python3
"""Reconcile incoming PJSIP native text, live readiness, and release evidence."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

SCENARIO = "PJSIP-NATIVE-T140-UAS"
CORRELATION = "pjsip-2.17-native-text-uas-v1"
EXPECTED_COMMIT = "5a457451fa2712ba18e12b01738e8ff3af2b26fd"


def load_properties(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        key, sep, value = raw.partition("=")
        if not sep:
            raise ValueError(f"malformed properties line: {raw!r}")
        values[key] = value
    return values


def require(values: dict[str, str], key: str, expected: str) -> None:
    actual = values.get(key)
    if actual != expected:
        raise ValueError(f"expected {key}={expected}, got {actual!r}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    root = Path(os.environ.get("BAUDOT_EVIDENCE_DIR", "target/evidence-external"))
    run = root / SCENARIO / CORRELATION
    caller = run / "jain-caller"
    readiness = run / "readiness"
    terminal = run / "terminal"

    admission = json.loads((run / "pjsip-admission.json").read_text(encoding="utf-8"))
    if admission.get("repository") != "pjsip/pjproject":
        raise ValueError("unexpected PJSIP repository")
    if admission.get("release") != "2.17" or admission.get("commit") != EXPECTED_COMMIT:
        raise ValueError("unexpected PJSIP release/commit")
    if admission.get("cleanCheckout") is not True:
        raise ValueError("PJSIP checkout was not clean")

    caller_props = load_properties(caller / "result.properties")
    require(caller_props, "scenario.id", SCENARIO)
    require(caller_props, "caller.implementation", "JAIN-SIP")
    require(caller_props, "callee.implementation", "pjsip/pjproject-2.17")
    require(caller_props, "sip.dialog.confirmed", "true")
    require(caller_props, "sip.t140.answerObserved", "true")
    require(caller_props, "sip.ack.sent", "true")
    require(caller_props, "rtt.readinessToken.observed", "true")
    require(caller_props, "rttReady", "EXTERNAL_BAUDOT_REFERENCE_TOKEN")
    require(caller_props, "call.bye.sent", "true")
    require(caller_props, "call.bye.afterReadiness", "true")
    require(caller_props, "scenario.result", "OBSERVED")

    gate = json.loads((readiness / "result.json").read_text(encoding="utf-8"))
    if gate.get("result") != "PASS" or gate.get("rttReady") is not True:
        raise ValueError("live readiness gate did not pass")
    token = gate.get("readiness") or {}
    if token.get("semanticAuthority") != "baudot-reference":
        raise ValueError("unexpected readiness authority")
    if token.get("payloadType") != 98 or token.get("firstT140Text") != "H":
        raise ValueError("unexpected readiness payload/text")

    gate_token = (readiness / "rtt-ready.json").read_bytes()
    caller_token = (caller / "rtt-ready.token.json").read_bytes()
    if gate_token != caller_token:
        raise ValueError("JAIN did not preserve the exact readiness token it consumed")

    offer = (caller / "offer.sdp").read_text(encoding="utf-8").lower()
    answer = (caller / "answer.sdp").read_text(encoding="utf-8").lower()
    if "m=text " not in offer or "rtp/avp 98" not in offer or "t140/1000" not in offer:
        raise ValueError("JAIN offer did not select direct PT98 T.140")
    if "m=text " not in answer or "t140/1000" not in answer:
        raise ValueError("PJSIP UAS answer did not retain T.140 media")

    pjsip_log = (run / "pjsip.stdout.log").read_text(encoding="utf-8")
    markers = (
        "PJSIP_NATIVE_T140_UAS_READY release=2.17",
        "PJSIP_NATIVE_T140_UAS_INCOMING",
        "PJSIP_NATIVE_T140_UAS_ANSWER_REQUESTED textCount=1",
        "PJSIP_NATIVE_T140_UAS_MEDIA_STATE",
        "PJSIP_NATIVE_T140_UAS_SEND_REQUESTED text=H",
        "PJSIP_NATIVE_T140_UAS_TEXT_SENT",
        "PJSIP_NATIVE_T140_UAS_REMOTE_RELEASE_OBSERVED",
        "PJSIP_NATIVE_T140_UAS_COMPLETE",
    )
    for marker in markers:
        if marker not in pjsip_log:
            raise ValueError(f"missing PJSIP UAS observation marker: {marker}")

    packet_name = token.get("packet")
    if not isinstance(packet_name, str):
        raise ValueError("readiness token lacks packet name")
    packet_path = readiness / packet_name
    if not packet_path.exists():
        raise ValueError("qualifying native PJSIP packet was not preserved")
    if sha256(packet_path) != token.get("packetSha256"):
        raise ValueError("readiness packet hash does not match preserved datagram")

    terminal.mkdir(parents=True, exist_ok=True)
    result = {
        "scenarioId": SCENARIO,
        "correlationId": CORRELATION,
        "result": "PASS",
        "implementation": {
            "repository": "pjsip/pjproject",
            "release": "2.17",
            "commit": EXPECTED_COMMIT,
            "role": "incoming native RTT endpoint",
        },
        "signaling": {
            "jainOfferDirectT140Pt98": True,
            "pjsipAnswerT140": True,
            "dialogConfirmed": True,
        },
        "readiness": {
            "semanticAuthority": "baudot-reference",
            "firstT140Text": "H",
            "payloadType": 98,
            "packet": packet_name,
            "packetSha256": token["packetSha256"],
            "rttReady": True,
        },
        "release": {
            "jainConsumedExactReadinessToken": True,
            "byeAfterReadiness": True,
            "pjsipObservedRemoteRelease": True,
        },
        "claimBoundary": {
            "incomingPjsipNativeTextObserved": True,
            "referInterop": False,
            "sipConformance": False,
            "rfc4103Conformance": False,
            "t140Conformance": False,
            "productionVrsReadiness": False,
        },
    }
    result_path = terminal / "pjsip-native-t140-uas.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest_files = [
        result_path,
        run / "pjsip-admission.json",
        readiness / "result.json",
        readiness / "rtt-ready.json",
        packet_path,
        caller / "offer.sdp",
        caller / "answer.sdp",
        caller / "rtt-ready.token.json",
        caller / "bye.request.sip",
        caller / "bye-200.response.sip",
    ]
    lines = []
    for path in manifest_files:
        lines.append(f"{sha256(path)}  {path.relative_to(terminal)}\n")
    (terminal / "manifest.sha256").write_text("".join(lines), encoding="utf-8")

    print("✓ PJSIP 2.17 answered an incoming text-only call")
    print("✓ native PJSIP media produced T.140 'H' accepted by the live Baudot reference gate")
    print("✓ JAIN released the call only after consuming the exact independent readiness token")
    print(f"evidence: {result_path}")


if __name__ == "__main__":
    main()
