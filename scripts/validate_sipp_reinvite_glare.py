#!/usr/bin/env python3
"""Terminal reducer for SIPP-HOSTILE-004 against the JAIN SIP glare target.

SIPp's own success is evidence, not verdict authority. This reducer joins the
preserved SIPp wire trace with target-side JAIN observations and publishes only
the narrow signaling-overlap verdict. It does not promote media or RTT readiness.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SCENARIO = "BAUDOT-INTEROP-003"
HOSTILE_ID = "SIPP-HOSTILE-004"
CORRELATION = "sipp-hostile-004-jain-v1"

MESSAGE_START = re.compile(
    r"(?im)^[ \t]*(?:(?:INVITE|ACK|BYE|REFER|NOTIFY|OPTIONS)\s+\S+\s+SIP/2\.0|SIP/2\.0\s+\d{3}\b[^\r\n]*)[ \t]*$"
)
CSEQ = re.compile(r"(?im)^CSeq:\s*(\d+)\s+([A-Z]+)\s*$")


@dataclass(frozen=True)
class SipMessage:
    offset: int
    start_line: str
    raw: str
    cseq: int | None
    cseq_method: str | None

    @property
    def is_response(self) -> bool:
        return self.start_line.upper().startswith("SIP/2.0 ")

    @property
    def status(self) -> int | None:
        if not self.is_response:
            return None
        match = re.match(r"(?i)^SIP/2\.0\s+(\d{3})\b", self.start_line)
        return int(match.group(1)) if match else None

    @property
    def request_method(self) -> str | None:
        if self.is_response:
            return None
        return self.start_line.split(None, 1)[0].upper()


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


def parse_messages(trace: str) -> list[SipMessage]:
    starts = list(MESSAGE_START.finditer(trace))
    messages: list[SipMessage] = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(trace)
        raw = trace[match.start():end]
        start_line = match.group(0).strip()
        cseq_match = CSEQ.search(raw)
        messages.append(
            SipMessage(
                offset=match.start(),
                start_line=start_line,
                raw=raw,
                cseq=int(cseq_match.group(1)) if cseq_match else None,
                cseq_method=cseq_match.group(2).upper() if cseq_match else None,
            )
        )
    return messages


def find_request(messages: list[SipMessage], method: str, cseq: int) -> SipMessage | None:
    method = method.upper()
    return next(
        (
            message
            for message in messages
            if not message.is_response
            and message.request_method == method
            and message.cseq == cseq
            and message.cseq_method == method
        ),
        None,
    )


def find_response(messages: list[SipMessage], status: int, cseq: int, method: str) -> SipMessage | None:
    method = method.upper()
    return next(
        (
            message
            for message in messages
            if message.is_response
            and message.status == status
            and message.cseq == cseq
            and message.cseq_method == method
        ),
        None,
    )


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: validate_sipp_reinvite_glare.py <sipp-message-log> <target-result.properties> <output.json>"
        )

    trace_path = Path(sys.argv[1])
    target_result_path = Path(sys.argv[2])
    output_path = Path(sys.argv[3])

    require(trace_path.is_file(), f"missing SIPp message trace: {trace_path}")
    require(target_result_path.is_file(), f"missing JAIN target result: {target_result_path}")

    trace = trace_path.read_text(encoding="utf-8", errors="replace")
    target = read_properties(target_result_path)
    messages = parse_messages(trace)

    require(messages, "SIPp trace contained no parseable SIP message blocks")
    require(target.get("scenario.id") == SCENARIO, "target scenario id drifted")
    require(target.get("hostile.id") == HOSTILE_ID, "target hostile id drifted")
    require(target.get("correlation.id") == CORRELATION, "target correlation id drifted")
    require(target.get("target.result") == "PASS", "JAIN target-side state did not complete")
    require(target.get("target.initialInvite200Sent") == "true", "initial dialog was not answered")
    require(target.get("target.initialAckObserved") == "true", "initial ACK was not observed")
    require(target.get("target.firstReinviteHeld") == "true", "CSeq 2 re-INVITE was not held")
    require(target.get("target.firstReinvite200Sent") == "true", "CSeq 2 re-INVITE did not complete")
    require(target.get("target.firstReinviteAckObserved") == "true", "CSeq 2 ACK was not observed")
    require(target.get("terminal.glareVerdictOwnedHere") == "false", "target stole terminal verdict authority")
    require(target.get("rttReady") == "false", "signaling-only glare target promoted RTT readiness")

    initial_invite = find_request(messages, "INVITE", 1)
    initial200 = find_response(messages, 200, 1, "INVITE")
    invite2 = find_request(messages, "INVITE", 2)
    invite3 = find_request(messages, "INVITE", 3)
    glare491 = find_response(messages, 491, 3, "INVITE")
    first200 = find_response(messages, 200, 2, "INVITE")
    ack3 = find_request(messages, "ACK", 3)
    ack2 = find_request(messages, "ACK", 2)

    require(initial_invite is not None, "SIPp trace lacks initial INVITE")
    require(initial200 is not None, "SIPp trace lacks initial 200")
    require(invite2 is not None, "SIPp trace lacks CSeq 2 re-INVITE")
    require(invite3 is not None, "SIPp trace lacks CSeq 3 glare re-INVITE")
    require(glare491 is not None, "SIPp trace lacks 491 for CSeq 3")
    require(first200 is not None, "SIPp trace lacks 200 for CSeq 2")
    require(ack3 is not None, "SIPp trace lacks ACK for rejected CSeq 3 INVITE")
    require(ack2 is not None, "SIPp trace lacks ACK for completed CSeq 2 INVITE")

    require(initial_invite.offset < initial200.offset, "initial 200 preceded initial INVITE")
    require(invite2.offset < invite3.offset, "CSeq 3 did not follow CSeq 2")
    require(invite3.offset < glare491.offset, "491 appeared before the glare request")
    require(glare491.offset < ack3.offset, "ACK for CSeq 3 appeared before 491")
    require(glare491.offset < first200.offset, "earlier CSeq 2 completed before glare was rejected")
    require(first200.offset < ack2.offset, "ACK for CSeq 2 appeared before its 200")

    output = {
        "scenarioId": SCENARIO,
        "hostileId": HOSTILE_ID,
        "correlationId": CORRELATION,
        "stimulusGenerator": "SIPp",
        "target": "JAIN SIP RI",
        "traceSha256": sha256(trace_path),
        "targetResultSha256": sha256(target_result_path),
        "parsedSipMessageCount": len(messages),
        "initialDialogObserved": True,
        "cseq2ReinviteObserved": True,
        "cseq3GlareObserved": True,
        "cseq3Status": 491,
        "cseq2Status": 200,
        "responseOrdering": "cseq3-491-before-cseq2-200",
        "targetGlareDeliveredToApplication": target.get("target.glareReinviteDeliveredToApplication") == "true",
        "targetApplication491Sent": target.get("target.application491Sent") == "true",
        "rttReady": False,
        "mediaReadinessProven": False,
        "terminalVerdict": "RUNNABLE_PASS",
        "status": "runnable",
        "claimBoundary": {
            "sipConformance": False,
            "reinviteConformance": False,
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
