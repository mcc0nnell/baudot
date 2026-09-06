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
from pathlib import Path

SCENARIO = "BAUDOT-INTEROP-003"
HOSTILE_ID = "SIPP-HOSTILE-004"
CORRELATION = "sipp-hostile-004-jain-v1"


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


def response_match(trace: str, status: int, cseq: int) -> re.Match[str] | None:
    pattern = re.compile(
        rf"SIP/2\.0\s+{status}\b.*?^CSeq:\s*{cseq}\s+INVITE\s*$",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    return pattern.search(trace)


def request_match(trace: str, cseq: int) -> re.Match[str] | None:
    pattern = re.compile(
        rf"^INVITE\s+.*?\s+SIP/2\.0\s*$.*?^CSeq:\s*{cseq}\s+INVITE\s*$",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    return pattern.search(trace)


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

    invite2 = request_match(trace, 2)
    invite3 = request_match(trace, 3)
    glare491 = response_match(trace, 491, 3)
    first200 = response_match(trace, 200, 2)

    require(invite2 is not None, "SIPp trace lacks CSeq 2 re-INVITE")
    require(invite3 is not None, "SIPp trace lacks CSeq 3 glare re-INVITE")
    require(glare491 is not None, "SIPp trace lacks 491 for CSeq 3")
    require(first200 is not None, "SIPp trace lacks 200 for CSeq 2")
    require(invite2.start() < invite3.start(), "CSeq 3 did not follow CSeq 2")
    require(invite3.start() < glare491.start(), "491 appeared before the glare request")
    require(glare491.start() < first200.start(), "earlier CSeq 2 completed before glare was rejected")

    output = {
        "scenarioId": SCENARIO,
        "hostileId": HOSTILE_ID,
        "correlationId": CORRELATION,
        "stimulusGenerator": "SIPp",
        "target": "JAIN SIP RI",
        "traceSha256": sha256(trace_path),
        "targetResultSha256": sha256(target_result_path),
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
