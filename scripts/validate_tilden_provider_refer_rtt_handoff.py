#!/usr/bin/env python3
"""Reduce TILDEN-HANDOFF-003 by joining Tilden route evidence to BAUDOT-INTEROP-004."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

INNER_CORRELATION = "jain-to-pjsip-native-handoff-v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_properties(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise ValueError(f"malformed property line: {raw!r}")
        result[key] = value
    return result


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    args = parser.parse_args()

    out = args.out.resolve()
    selection_path = args.selection.resolve()
    selection = load_json(selection_path)
    route = load_json(out / "route.json")

    selection_id = selection["selectionId"]
    selected_endpoint = selection["selectedEndpoint"]
    require(route["selectionId"] == selection_id, "route selectionId drift")
    require(route["selectedEndpoint"] == selected_endpoint, "route selectedEndpoint drift")

    inner = out / "inner-evidence" / "BAUDOT-INTEROP-004" / INNER_CORRELATION
    run = inner / "jain-to-pjsip-native-handoff"
    inner_terminal = load_json(run / "terminal-result.json")
    inner_values = load_properties(run / "result.properties")
    readiness = load_json(inner / "readiness" / "result.json")

    original_invite = (run / "original-invite.request.sip").read_text(encoding="utf-8")
    request_line = original_invite.splitlines()[0] if original_invite.splitlines() else ""
    require(
        request_line == f"INVITE {selected_endpoint} SIP/2.0",
        "original SIP Request-URI did not equal Tilden selectedEndpoint",
    )

    require(inner_values.get("scenario.id") == "BAUDOT-INTEROP-004", "unexpected inner scenario")
    require(inner_values.get("provider.source") == "provider-a", "unexpected selected provider identity")
    require(inner_values.get("refer.accepted") == "true", "selected provider did not accept REFER")
    require(
        inner_values.get("replacement.dialog.established") == "true",
        "replacement dialog did not establish",
    )
    require(inner_values.get("rtt.negotiated") == "true", "replacement RTT was not negotiated")
    require(
        inner_values.get("rttReady") == "EXTERNAL_BAUDOT_REFERENCE_TOKEN",
        "inner JAIN harness claimed RTT semantics directly",
    )
    require(
        inner_values.get("oldLeg.bye.afterReadinessToken") == "true",
        "original provider leg released before independent readiness",
    )
    require(inner_values.get("scenarioResult") == "PASS", "inner REFER handoff did not pass")

    require(inner_terminal.get("result") == "PASS", "inner terminal reducer did not pass")
    require(inner_terminal.get("referAccepted") is True, "inner terminal REFER fact missing")
    require(
        inner_terminal.get("replacementDialogEstablished") is True,
        "inner terminal replacement-dialog fact missing",
    )
    require(
        inner_terminal.get("oldLegReleasedAfterIndependentReadiness") is True,
        "inner terminal release-order fact missing",
    )
    inner_readiness = inner_terminal.get("readiness") or {}
    require(inner_readiness.get("semanticAuthority") == "baudot-reference", "unexpected semantic authority")
    require(inner_readiness.get("rttReady") is True, "inner terminal RTT readiness is not true")
    require(inner_readiness.get("firstT140Text") == "H", "unexpected first replacement T.140 text")

    require(readiness.get("result") == "PASS", "inner independent readiness gate did not pass")
    require(readiness.get("rttReady") is True, "inner independent readiness classification is not true")

    inner_manifest = inner / "bundle.manifest.sha256"
    require(inner_manifest.is_file(), "inner evidence bundle manifest missing")

    terminal = {
        "scenarioId": "TILDEN-HANDOFF-003",
        "selectionId": selection_id,
        "selectedProviderEndpoint": selected_endpoint,
        "facts": {
            "routeSelectionPreserved": True,
            "selectedProviderUsedAsOriginalRequestUri": True,
            "referAccepted": True,
            "replacementDialogEstablished": True,
            "replacementRttReady": True,
            "oldLegReleasedAfterIndependentReadiness": True,
        },
        "routingAuthority": "tilden-selection-evidence",
        "transferAuthority": "baudot-interop004",
        "semanticAuthority": "baudot-reference",
        "innerEvidence": {
            "scenarioId": "BAUDOT-INTEROP-004",
            "correlationId": INNER_CORRELATION,
            "terminalSha256": sha256(run / "terminal-result.json"),
            "bundleManifestSha256": sha256(inner_manifest),
            "qualifyingPacketSha256": inner_readiness["packetSha256"],
        },
        "selectionSha256": sha256(selection_path),
        "verdict": "ready-after-transfer",
        "claimBoundary": (
            "controlled Tilden-selected provider route through Baudot REFER to pinned PJSIP native RTT; "
            "no Tilden/SIP/RTP/RFC4103/T140/PJSIP/VRS conformance or production-readiness claim"
        ),
    }

    (out / "terminal-result.json").write_text(
        json.dumps(terminal, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(terminal, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
