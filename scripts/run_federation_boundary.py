#!/usr/bin/env python3
"""Join live SIP evidence to the deterministic right-hand boundary of BAUDOT-FED-002."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from baudot_reference.federation_lab import reduce_sip_webrtc_boundary

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIO = ROOT / "testkit" / "federation" / "BAUDOT-FED-002-sip-interpreter-webrtc-boundary.json"


def read_properties(path: Path) -> dict[str, str]:
    properties: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise ValueError(f"{path}: malformed property line {raw!r}")
        properties[key.strip()] = value.strip()
    return properties


def live_sip_facts(evidence_root: Path, scenario_id: str, correlation: str) -> dict[str, bool]:
    base = evidence_root / scenario_id / correlation
    caller = read_properties(base / "caller" / "result.properties")
    interpreter = read_properties(base / "callee" / "result.properties")
    return {
        "callerDialogEstablished": caller.get("signaling.dialog.established") == "true",
        "callerMediaProbeSent": caller.get("media.probe.sent") == "true",
        "interpreterInviteReceived": interpreter.get("signaling.invite.received") == "true",
        "interpreterAckReceived": interpreter.get("signaling.ack.received") == "true",
        "interpreterMediaProbeReceived": interpreter.get("media.probe.received") == "true",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument("--arm", default="control")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--live-evidence-root", type=Path)
    parser.add_argument("--correlation")
    args = parser.parse_args()

    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    result = reduce_sip_webrtc_boundary(scenario, args.arm)

    sip_facts: dict[str, bool] = {}
    live_sip_gate = True
    if args.live_evidence_root is not None:
        if not args.correlation:
            raise SystemExit("--correlation is required with --live-evidence-root")
        sip_facts = live_sip_facts(args.live_evidence_root, scenario["id"], args.correlation)
        live_sip_gate = all(sip_facts.values())

    combined_ready = live_sip_gate and result.terminal_verdict == "ready"
    failed_facts = list(result.failed_facts)
    if not live_sip_gate:
        failed_facts.extend(sorted(name for name, value in sip_facts.items() if not value))

    payload = {
        "scenario": scenario["id"],
        "arm": result.arm_id,
        "liveSipGate": live_sip_gate,
        "liveSipFacts": sip_facts,
        "interpreterJoined": result.interpreter_joined,
        "interpreterReady": result.interpreter_ready,
        "browserBoundaryNegotiated": result.browser_boundary_negotiated,
        "browserBoundaryProfileValid": result.browser_boundary_profile_valid,
        "browserBoundaryT140Observed": result.browser_boundary_t140_observed,
        "browserBoundaryT140Valid": result.browser_boundary_t140_valid,
        "decodedText": result.decoded_text,
        "failedFacts": sorted(set(failed_facts)),
        "terminalVerdict": "ready" if combined_ready else "not-ready",
        "claimBoundary": "reference RFC8865 boundary; not a real browser",
    }

    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if combined_ready else 3


if __name__ == "__main__":
    raise SystemExit(main())
