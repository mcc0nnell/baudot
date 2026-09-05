#!/usr/bin/env python3
"""Execute the deterministic right-hand boundary of BAUDOT-FED-002.

The companion shell runner gates this on successful live JAIN SIP caller ->
interpreter signaling. This process reduces the destination-facing RFC 8865
reference boundary and emits one small terminal evidence record.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from baudot_reference.federation_lab import reduce_sip_webrtc_boundary

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIO = ROOT / "testkit" / "federation" / "BAUDOT-FED-002-sip-interpreter-webrtc-boundary.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument("--arm", default="control")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    result = reduce_sip_webrtc_boundary(scenario, args.arm)
    payload = {
        "scenario": scenario["id"],
        "arm": result.arm_id,
        "sipLeftBoundary": "required-by-companion-live-runner",
        "interpreterJoined": result.interpreter_joined,
        "interpreterReady": result.interpreter_ready,
        "browserBoundaryNegotiated": result.browser_boundary_negotiated,
        "browserBoundaryProfileValid": result.browser_boundary_profile_valid,
        "browserBoundaryT140Observed": result.browser_boundary_t140_observed,
        "browserBoundaryT140Valid": result.browser_boundary_t140_valid,
        "decodedText": result.decoded_text,
        "failedFacts": list(result.failed_facts),
        "terminalVerdict": result.terminal_verdict,
        "claimBoundary": "reference RFC8865 boundary; not a real browser",
    }

    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result.terminal_verdict == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
