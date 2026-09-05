#!/usr/bin/env python3
"""Independent Baudot reduction for BAUDOT-INTEROP-003 live RTT readiness."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from baudot_reference.rfc4103 import PrimaryT140RtpPacket

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT
    / "target"
    / "evidence"
    / "BAUDOT-INTEROP-003"
    / "jain-live-rtt-readiness-v1"
    / "live-rtt-readiness"
)
RESULT = EVIDENCE / "result.properties"
VALIDATION = EVIDENCE / "rtt-readiness-validation.json"
VALIDATION_SHA = EVIDENCE / "rtt-readiness-validation.json.sha256"


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def properties(path: Path) -> dict[str, str]:
    output: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        require(bool(separator), f"malformed property line: {raw}")
        output[key.strip()] = value.strip()
    return output


def sdp_text_port(sdp: str) -> int:
    match = re.search(r"(?m)^m=text\s+(\d+)\s+RTP/AVP\s+.*$", sdp)
    require(match is not None, "SDP has no m=text line")
    return int(match.group(1))


def negotiates_t140(sdp: str) -> bool:
    return (
        re.search(r"(?m)^m=text\s+\d+\s+RTP/AVP\s+.*\b98\b.*$", sdp) is not None
        and re.search(r"(?im)^a=rtpmap:98\s+t140/1000\s*$", sdp) is not None
    )


def main() -> None:
    require(RESULT.is_file(), f"missing Java result: {RESULT}")
    props = properties(RESULT)
    require(props.get("scenario.result") == "PASS", "Java transport gate did not pass")
    require(props.get("control.sip.status") == "200", "control SIP status is not 200")
    require(props.get("stale.sip.status") == "200", "stale SIP status is not 200")
    require(props.get("control.datagram.received") == "true", "control datagram was not observed")
    require(
        props.get("control.wireBytesPreserved") == "true",
        "control datagram bytes were not preserved",
    )
    require(
        props.get("stale.datagram.receivedAtIntendedFreshPort") == "false",
        "stale arm unexpectedly reached the intended fresh RTT port",
    )
    require(props.get("stale.sdp.detected") == "true", "Java gate did not detect stale SDP")

    control_sdp = (EVIDENCE / "control.answer.sdp").read_text(encoding="utf-8")
    stale_sdp = (EVIDENCE / "stale.answer.sdp").read_text(encoding="utf-8")
    expected_fresh_sdp = (EVIDENCE / "stale.expected-fresh-answer.sdp").read_text(encoding="utf-8")

    require(control_sdp == stale_sdp, "stale arm did not actually reuse the control answer SDP")
    require(stale_sdp != expected_fresh_sdp, "stale arm unexpectedly matches fresh SDP")
    require(sdp_text_port(control_sdp) == 42202, "unexpected control RTT port")
    require(sdp_text_port(stale_sdp) == 42202, "stale answer does not advertise prior RTT port")
    require(sdp_text_port(expected_fresh_sdp) == 42203, "unexpected intended fresh RTT port")

    control_packet_bytes = (EVIDENCE / "control-rtt-received.bin").read_bytes()
    control_packet = PrimaryT140RtpPacket.from_bytes(
        control_packet_bytes,
        expected_payload_type=98,
    )
    require(control_packet.block.text == "H", "control packet did not contain expected T140block H")

    stale_receive_file = EVIDENCE / "stale-rtt-received.bin"
    require(not stale_receive_file.exists(), "stale arm preserved an unexpected received datagram")
    require((EVIDENCE / "stale-rtt-timeout.txt").is_file(), "stale arm lacks bounded timeout evidence")

    control_negotiated = negotiates_t140(control_sdp)
    stale_negotiated = negotiates_t140(stale_sdp)
    control_first_character = control_packet.block.text != ""
    stale_first_character = False

    control_ready = control_negotiated and control_first_character
    stale_ready = stale_negotiated and stale_first_character
    require(control_ready, "control RTT readiness did not become true")
    require(not stale_ready, "stale RTT readiness unexpectedly became true")

    validation = {
        "scenarioId": "BAUDOT-INTEROP-003",
        "profile": "jain-live-rtt-readiness-v1",
        "scenarioResult": "PASS",
        "control": {
            "sipStatus": 200,
            "answerTextPort": sdp_text_port(control_sdp),
            "rttNegotiated": control_negotiated,
            "firstT140CharacterObserved": control_first_character,
            "firstT140Text": control_packet.block.text,
            "rttReady": control_ready,
        },
        "stale": {
            "sipStatus": 200,
            "answerTextPort": sdp_text_port(stale_sdp),
            "intendedFreshTextPort": sdp_text_port(expected_fresh_sdp),
            "staleSdpDetected": True,
            "rttNegotiated": stale_negotiated,
            "firstT140CharacterObserved": stale_first_character,
            "rttReady": stale_ready,
        },
        "claimBoundary": {
            "liveStaleSdpMismatchExercised": True,
            "controlPrimaryT140PacketValidated": True,
            "fullRfc4103Conformance": False,
            "sipConformance": False,
            "productionVrsReadiness": False,
        },
    }

    encoded = (json.dumps(validation, indent=2, sort_keys=True) + "\n").encode("utf-8")
    VALIDATION.write_bytes(encoded)
    digest = hashlib.sha256(encoded).hexdigest()
    VALIDATION_SHA.write_text(f"{digest}  {VALIDATION.name}\n", encoding="utf-8")
    print(
        "✓ BAUDOT-INTEROP-003 live RTT readiness: "
        "control ready, stale SDP preserved 200 while RTT readiness remained false"
    )


if __name__ == "__main__":
    main()
