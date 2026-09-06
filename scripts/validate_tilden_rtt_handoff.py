#!/usr/bin/env python3
"""Reduce Tilden route evidence plus independently validated RTT evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_properties(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        require(bool(separator) and bool(key), f"{path}: malformed property line: {raw!r}")
        values[key] = value
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--runtime-route", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()

    route = json.loads(args.route.read_text(encoding="utf-8"))
    runtime_route = json.loads(args.runtime_route.read_text(encoding="utf-8"))
    rtt = json.loads((args.run_dir / "rtt-validation.json").read_text(encoding="utf-8"))
    caller = read_properties(args.run_dir / "caller" / "result.properties")
    callee = read_properties(args.run_dir / "callee" / "result.properties")

    selection_id = route["selectionId"]
    selected_endpoint = route["selectedEndpoint"]

    require(args.run_dir.name == selection_id, "run directory is not correlated by selectionId")
    require(runtime_route.get("selectionId") == selection_id, "runtime route selectionId mismatch")
    require(runtime_route.get("selectedEndpoint") == selected_endpoint, "runtime route endpoint mismatch")
    require(runtime_route.get("canonicalRequestUri") == selected_endpoint, "runtime SIP URI differs from Tilden selection")
    require(caller.get("correlation.id") == selection_id, "caller evidence lost selectionId correlation")
    require(callee.get("correlation.id") == selection_id, "callee evidence lost selectionId correlation")
    require(caller.get("signaling.dialog.established") == "true", "selected route did not establish a SIP dialog")
    require(callee.get("media.probe.received") == "true", "selected route did not deliver the expected RTT datagrams")
    require(rtt.get("verdict") == "pass", "independent RTT validator did not pass")
    require(rtt.get("validationAuthority") == "baudot-python-reference", "unexpected RTT validation authority")
    require(rtt.get("wireBytesPreserved") is True, "RTT wire bytes were not preserved")

    presentation = rtt.get("presentation", {})
    require(presentation.get("displayText") == "Hi", "validated RTT presentation is not 'Hi'")
    require(presentation.get("missingTextMarkers") == 0, "validated RTT presentation contains missing-text markers")

    evidence = {
        "schema": "baudot.tilden-rtt-handoff-evidence/v1",
        "scenario": "TILDEN-HANDOFF-002",
        "selectionId": selection_id,
        "target": route.get("target"),
        "selectedEndpoint": selected_endpoint,
        "resolutionDigest": route.get("resolutionDigest"),
        "requestDigest": route.get("requestDigest"),
        "signalingDialogEstablished": True,
        "rtt": {
            "validationAuthority": rtt["validationAuthority"],
            "wireBytesPreserved": True,
            "presentation": presentation,
            "verdict": "pass",
        },
        "runtimeClaim": "selected-route-rtt-ready",
        "claimBoundary": {
            "establishes": [
                "the exact Tilden-selected SIP/UDP endpoint mapped into the exercised runtime profile",
                "a live SIP dialog on that selected route",
                "preserved RTT datagrams independently validated as the exercised RFC 4103/RFC 2198 T.140 profile",
                "selectionId correlation from routing evidence into runtime evidence",
            ],
            "doesNotEstablish": [
                "full RFC 3261 conformance",
                "full RFC 4103 conformance",
                "full T.140 conformance",
                "TLS or SIPS interoperability",
                "video or relay interoperability",
                "WebRTC interoperability",
                "end-to-end encryption",
                "production network readiness",
            ],
        },
        "verdict": "pass",
    }

    output = args.run_dir / "tilden-rtt-handoff-validation.json"
    output.write_text(json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("✓ Tilden selected route preserved as Baudot runtime target")
    print("✓ live selected route independently proved RTT-ready: presentation 'Hi'")


if __name__ == "__main__":
    main()
