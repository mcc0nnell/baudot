#!/usr/bin/env python3
"""Reduce TILDEN-HANDOFF-004: failed selected route, no silent fallback, explicit reselection recovery."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

INITIAL_ID = "sel-reselection-initial-0001"
RECOVERY_ID = "sel-reselection-recovery-0002"
INITIAL_ENDPOINT = "sip:unavailable@127.0.0.1:5390;transport=udp"
RECOVERY_ENDPOINT = "sip:provider-a@127.0.0.1:5310"


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


def load_events(path: Path) -> list[dict[str, str]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def candidate(selection: dict, uri: str) -> dict:
    matches = [item for item in selection.get("candidates", []) if item.get("uri") == uri]
    require(len(matches) == 1, f"candidate identity is not unique: {uri}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--initial-selection", type=Path, required=True)
    parser.add_argument("--recovery-selection", type=Path, required=True)
    args = parser.parse_args()

    out = args.out.resolve()
    initial_path = args.initial_selection.resolve()
    recovery_path = args.recovery_selection.resolve()
    initial = load_json(initial_path)
    recovery = load_json(recovery_path)
    initial_route = load_json(out / "initial-route.json")
    recovery_route = load_json(out / "recovery-route.json")
    authority = load_json(out / "reselection-authority.json")
    sentinel = load_json(out / "pre-reselection-provider-sentinel.json")

    require(initial["selectionId"] == INITIAL_ID, "unexpected initial selectionId")
    require(recovery["selectionId"] == RECOVERY_ID, "unexpected recovery selectionId")
    require(initial["selectionId"] != recovery["selectionId"], "recovery reused initial selectionId")
    require(initial["target"] == recovery["target"], "reselection target changed")
    require(initial["selectedEndpoint"] == INITIAL_ENDPOINT, "unexpected initial selected endpoint")
    require(recovery["selectedEndpoint"] == RECOVERY_ENDPOINT, "unexpected recovery selected endpoint")
    require(initial_route["selectionId"] == INITIAL_ID, "initial route selectionId drift")
    require(initial_route["selectedEndpoint"] == INITIAL_ENDPOINT, "initial route endpoint drift")
    require(recovery_route["selectionId"] == RECOVERY_ID, "recovery route selectionId drift")
    require(recovery_route["selectedEndpoint"] == RECOVERY_ENDPOINT, "recovery route endpoint drift")

    require(candidate(initial, INITIAL_ENDPOINT).get("outcome") == "selected", "initial dead route not selected")
    require(candidate(initial, RECOVERY_ENDPOINT).get("outcome") == "eligible", "recovery provider was not merely eligible initially")
    require(candidate(recovery, INITIAL_ENDPOINT).get("outcome") == "failed", "failed route not recorded failed on reselection")
    require(candidate(recovery, RECOVERY_ENDPOINT).get("outcome") == "selected", "recovery provider not explicitly selected")

    require(authority.get("initialSelectionId") == INITIAL_ID, "authority record lost initial selection")
    require(authority.get("recoverySelectionId") == RECOVERY_ID, "authority record lost recovery selection")
    require(sentinel.get("bind") == "127.0.0.1:5310", "sentinel watched wrong provider endpoint")
    require(sentinel.get("datagramCount") == 0, "eligible provider received traffic before reselection")

    initial_run = out / "initial-attempt" / "TILDEN-HANDOFF-001" / INITIAL_ID / "caller"
    initial_values = load_properties(initial_run / "result.properties")
    initial_events = load_events(initial_run / "events.jsonl")
    require(initial_values.get("tilden.selection.id") == INITIAL_ID, "initial attempt selectionId drift")
    require(initial_values.get("tilden.selected.endpoint") == INITIAL_ENDPOINT, "initial attempt endpoint drift")
    require(initial_values.get("signaling.dialog.established") == "false", "dead route unexpectedly established")
    require((out / "initial.exit-code.txt").read_text(encoding="utf-8").strip() == "3", "unexpected initial process exit")

    invites = [event for event in initial_events if event.get("type") == "sip.invite.sent"]
    require(len(invites) == 1, "initial attempt did not emit exactly one INVITE observation")
    require(invites[0].get("requestUri") == INITIAL_ENDPOINT, "initial INVITE did not use selected endpoint")
    require(
        all(event.get("requestUri") != RECOVERY_ENDPOINT for event in initial_events),
        "initial attempt evidence contains unauthorized recovery-provider signaling",
    )

    recovery_run = out / "recovery-attempt" / "TILDEN-HANDOFF-003" / RECOVERY_ID
    recovery_terminal = load_json(recovery_run / "terminal-result.json")
    recovery_facts = recovery_terminal.get("facts") or {}
    require(recovery_terminal.get("scenarioId") == "TILDEN-HANDOFF-003", "unexpected recovery scenario")
    require(recovery_terminal.get("selectionId") == RECOVERY_ID, "recovery terminal selectionId drift")
    require(recovery_terminal.get("selectedProviderEndpoint") == RECOVERY_ENDPOINT, "recovery provider endpoint drift")
    require(recovery_terminal.get("verdict") == "ready-after-transfer", "recovery transfer did not become ready")
    for fact in (
        "routeSelectionPreserved",
        "selectedProviderUsedAsOriginalRequestUri",
        "referAccepted",
        "replacementDialogEstablished",
        "replacementRttReady",
        "oldLegReleasedAfterIndependentReadiness",
    ):
        require(recovery_facts.get(fact) is True, f"recovery fact missing: {fact}")

    recovery_manifest = recovery_run / "bundle.manifest.sha256"
    require(recovery_manifest.is_file(), "recovery evidence bundle manifest missing")

    terminal = {
        "scenarioId": "TILDEN-HANDOFF-004",
        "correlationId": "reselection-recovery-0001",
        "target": initial["target"],
        "initialSelection": {
            "selectionId": INITIAL_ID,
            "selectedEndpoint": INITIAL_ENDPOINT,
            "selectionSha256": sha256(initial_path),
            "dialogEstablished": False,
        },
        "preReselectionObservation": {
            "eligibleProviderEndpoint": RECOVERY_ENDPOINT,
            "datagramCount": 0,
            "autonomousFallbackObserved": False,
        },
        "recoverySelection": {
            "selectionId": RECOVERY_ID,
            "selectedEndpoint": RECOVERY_ENDPOINT,
            "selectionSha256": sha256(recovery_path),
        },
        "facts": {
            "initialSelectedRouteAttempted": True,
            "initialSelectedRouteFailed": True,
            "eligibleProviderUntouchedBeforeReselection": True,
            "distinctRecoverySelectionRequired": True,
            "recoverySelectedProviderUsed": True,
            "recoveryReferAccepted": True,
            "recoveryReplacementRttReady": True,
            "recoveryOldLegReleasedAfterIndependentReadiness": True,
        },
        "routingAuthority": "tilden-selection-evidence",
        "failureObservationAuthority": "baudot-signaling-evidence",
        "recoveryAuthority": "distinct-tilden-selection-evidence",
        "recoveryEvidence": {
            "scenarioId": "TILDEN-HANDOFF-003",
            "terminalSha256": sha256(recovery_run / "terminal-result.json"),
            "bundleManifestSha256": sha256(recovery_manifest),
            "innerEvidence": recovery_terminal.get("innerEvidence"),
        },
        "verdict": "recovered-after-authorized-reselection",
        "claimBoundary": (
            "controlled failed selected route followed by explicit Tilden reselection and Baudot recovery; "
            "no autonomous routing, Tilden/SIP/RTP/RFC4103/T140/PJSIP/VRS conformance, provider failover, "
            "or production-readiness claim"
        ),
    }

    (out / "terminal-result.json").write_text(
        json.dumps(terminal, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(terminal, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
