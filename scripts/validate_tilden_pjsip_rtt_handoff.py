#!/usr/bin/env python3
"""Reduce TILDEN-HANDOFF-002 evidence without moving T.140 authority into Java or Tilden."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_properties(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value
    return result


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    args = parser.parse_args()

    out = args.out.resolve()
    selection = load_json(args.selection.resolve())
    selection_id = selection["selectionId"]
    selected_endpoint = selection["selectedEndpoint"]

    route = load_json(out / "route.json")
    caller = load_properties(out / "jain-caller" / "result.properties")
    readiness = load_json(out / "readiness" / "result.json")
    token = load_json(out / "readiness" / "rtt-ready.json")
    invite = (out / "jain-caller" / "invite.request.sip").read_text(encoding="utf-8")

    require(route["selectionId"] == selection_id, "route selectionId drift")
    require(route["selectedEndpoint"] == selected_endpoint, "route selectedEndpoint drift")
    require(caller.get("scenario.id") == "TILDEN-HANDOFF-002", "unexpected scenario id")
    require(caller.get("tilden.selection.id") == selection_id, "caller lost Tilden selection id")
    require(caller.get("tilden.selected.endpoint") == selected_endpoint, "caller selected endpoint drift")
    require(caller.get("signaling.dialog.established") == "true", "selected route did not establish")
    require(caller.get("sip.t140.answerObserved") == "true", "selected endpoint did not answer with T.140")
    require(caller.get("rtt.readinessToken.observed") == "true", "caller did not observe readiness token")
    require(caller.get("rttReady") == "EXTERNAL_BAUDOT_REFERENCE_TOKEN", "Java claimed RTT semantics directly")
    require(caller.get("call.bye.afterReadiness") == "true", "call released before RTT readiness")
    require(caller.get("runtime.claim") == "selected-route-native-rtt-ready", "unexpected runtime claim")
    require(caller.get("scenario.result") == "OBSERVED", "caller observation incomplete")

    require(readiness.get("result") == "PASS", "independent readiness gate did not pass")
    require(readiness.get("rttReady") is True, "independent readiness gate did not classify RTT ready")
    require(readiness.get("semanticAuthority") == "baudot-reference", "unexpected readiness authority")
    require(token.get("rttReady") is True, "readiness token is not positive")
    require(token.get("semanticAuthority") == "baudot-reference", "token authority drift")
    require(token.get("firstT140Text") == "H", "unexpected first native T.140 text")

    request_line = invite.splitlines()[0] if invite.splitlines() else ""
    require(request_line == f"INVITE {selected_endpoint} SIP/2.0", "SIP Request-URI did not equal selected endpoint")

    terminal = {
        "scenarioId": "TILDEN-HANDOFF-002",
        "selectionId": selection_id,
        "selectedEndpoint": selected_endpoint,
        "facts": {
            "routeSelectionPreserved": True,
            "selectedEndpointUsedAsRequestUri": True,
            "dialogEstablished": True,
            "t140Negotiated": True,
            "firstT140CharacterObserved": True,
            "rttReady": True,
            "releaseAfterReadiness": True,
        },
        "semanticAuthority": "baudot-reference",
        "routingAuthority": "tilden-selection-evidence",
        "verdict": "ready",
        "claimBoundary": (
            "controlled Tilden-selected SIP plus native PJSIP RTT readiness; "
            "no SIP/RTP/RFC4103/T140/PJSIP/Tilden/VRS conformance claim"
        ),
    }
    (out / "terminal-result.json").write_text(
        json.dumps(terminal, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(terminal, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
