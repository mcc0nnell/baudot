#!/usr/bin/env python3
"""Terminal reducer for SIPP-HOSTILE-002 delayed REFER/NOTIFY pressure."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from sipp_trace import find_request, find_response, parse_messages

SCENARIO = "BAUDOT-INTEROP-004"
HOSTILE_ID = "SIPP-HOSTILE-002"
CORRELATION = "sipp-hostile-002-jain-v1"
MIN_DELAY_MILLIS = 900
MAX_DELAY_MILLIS = 5000


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_properties(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        require(bool(separator), f"malformed properties line in {path}: {line!r}")
        values[key] = value
    return values


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: validate_sipp_delayed_refer_notify.py <sipp-message-log> <target-result.properties> <output.json>"
        )

    trace_path = Path(sys.argv[1])
    target_result_path = Path(sys.argv[2])
    output_path = Path(sys.argv[3])

    require(trace_path.is_file(), f"missing SIPp message trace: {trace_path}")
    require(target_result_path.is_file(), f"missing JAIN target result: {target_result_path}")

    trace = trace_path.read_text(encoding="utf-8", errors="replace")
    messages = parse_messages(trace)
    target = read_properties(target_result_path)

    require(messages, "SIPp trace contained no parseable SIP message blocks")
    require(target.get("scenario.id") == SCENARIO, "target scenario id drifted")
    require(target.get("hostile.id") == HOSTILE_ID, "target hostile id drifted")
    require(target.get("correlation.id") == CORRELATION, "target correlation id drifted")
    require(target.get("target.result") == "PASS", "JAIN delayed-NOTIFY target did not pass")
    require(target.get("target.dialogEstablished") == "true", "original dialog not established")
    require(target.get("target.referSent") == "true", "REFER was not sent")
    require(target.get("target.referAccepted202") == "true", "REFER 202 not observed")
    require(target.get("target.terminalNotifyObserved") == "true", "terminal NOTIFY not observed")
    require(target.get("target.notifyAcknowledged200") == "true", "NOTIFY was not acknowledged")
    require(target.get("target.terminalSipfragSuccess") == "true", "terminal sipfrag did not report 200")
    require(target.get("terminal.referVerdictOwnedHere") == "false", "JAIN target stole terminal verdict authority")
    require(target.get("replacement.dialog.established") == "false", "signaling-only pressure invented replacement dialog")
    require(target.get("firstT140CharacterObserved") == "false", "signaling-only pressure invented T.140 observation")
    require(target.get("rttReady") == "false", "signaling-only pressure promoted RTT readiness")
    require(target.get("oldLegReleased") == "false", "old leg was released without replacement readiness")

    delay_millis = int(target.get("target.notifyDelayMillis", "-1"))
    require(delay_millis >= MIN_DELAY_MILLIS, f"NOTIFY delay too short: {delay_millis} ms")
    require(delay_millis <= MAX_DELAY_MILLIS, f"NOTIFY delay escaped bounded window: {delay_millis} ms")

    invite = find_request(messages, "INVITE", 1)
    invite200 = find_response(messages, 200, 1, "INVITE")
    ack = find_request(messages, "ACK", 1)
    refer = find_request(messages, "REFER", 2)
    refer202 = find_response(messages, 202, 2, "REFER")
    notify = find_request(messages, "NOTIFY")
    notify200 = find_response(messages, 200, method="NOTIFY")

    require(invite is not None, "trace lacks initial INVITE")
    require(invite200 is not None, "trace lacks initial INVITE 200")
    require(ack is not None, "trace lacks initial ACK")
    require(refer is not None, "trace lacks REFER CSeq 2")
    require(refer202 is not None, "trace lacks REFER 202")
    require(notify is not None, "trace lacks terminal NOTIFY")
    require(notify200 is not None, "trace lacks NOTIFY 200 response")

    require(notify.has_header("Event", "refer"), "NOTIFY missing Event: refer")
    require(notify.has_header("Subscription-State", "terminated"), "NOTIFY subscription did not terminate")
    require(notify.has_header("Content-Type", "message/sipfrag"), "NOTIFY missing message/sipfrag content type")
    require(notify.body.upper().startswith("SIP/2.0 200"), "NOTIFY sipfrag did not report terminal 200")

    require(invite.offset < invite200.offset < ack.offset, "initial dialog message ordering invalid")
    require(ack.offset < refer.offset < refer202.offset, "REFER acceptance ordering invalid")
    require(refer202.offset < notify.offset < notify200.offset, "delayed NOTIFY ordering invalid")

    output = {
        "scenarioId": SCENARIO,
        "hostileId": HOSTILE_ID,
        "correlationId": CORRELATION,
        "stimulusGenerator": "SIPp",
        "target": "JAIN SIP RI",
        "traceSha256": sha256(trace_path),
        "targetResultSha256": sha256(target_result_path),
        "parsedSipMessageCount": len(messages),
        "referAccepted": True,
        "referStatus": 202,
        "terminalNotifyObserved": True,
        "terminalNotifySipfragStatus": 200,
        "notifyDelayMillis": delay_millis,
        "replacementDialogEstablished": False,
        "firstT140CharacterObserved": False,
        "rttReady": False,
        "oldLegReleased": False,
        "terminalVerdict": "RUNNABLE_PASS",
        "status": "runnable",
        "claimBoundary": {
            "sipConformance": False,
            "referConformance": False,
            "rfc4103Conformance": False,
            "t140Conformance": False,
            "accessibilityConformance": False,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
