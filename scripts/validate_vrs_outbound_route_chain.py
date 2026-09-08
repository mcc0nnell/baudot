#!/usr/bin/env python3
"""Join the registration-route chain with controlled RFC 5626 outbound-flow evidence."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "target" / "evidence" / "VRS-REGISTRATION-ROUTE-CHAIN" / "summary.json"
OUTBOUND = (
    ROOT
    / "target"
    / "evidence"
    / "RUE-REG-001"
    / "outbound-flow-recovery-v1"
    / "outbound-flow-proof"
    / "result.properties"
)
OUT = ROOT / "target" / "evidence" / "VRS-OUTBOUND-ROUTE-CHAIN" / "summary.json"


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"missing JSON evidence: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def load_properties(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError(f"missing properties evidence: {path}")
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"malformed result line: {raw}")
        key, value = line.split("=", 1)
        if key in result:
            raise ValueError(f"duplicate result key: {key}")
        result[key] = value
    return result


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    base = load_json(BASE)
    require(
        base.get("schema") == "baudot.vrs-registration-route-chain-evidence@1",
        "base chain schema drift",
    )
    require(base.get("result") == "PASS", "base registration-route chain not green")
    require(base.get("registrationAccepted") is True, "base registration not accepted")
    require(base.get("dialogEstablished") is True, "base dial-around dialog not established")
    require(base.get("mediaReadiness") is False, "base chain promoted media readiness")
    require(base.get("rttReadiness") is False, "base chain promoted RTT readiness")
    require(base.get("videoReadiness") is False, "base chain promoted video readiness")

    outbound = load_properties(OUTBOUND)
    require(outbound.get("scenario.result") == "PASS", "outbound-flow proof failed")
    require(
        outbound.get("rfc5626.outbound.flow.proven") == "true",
        "outbound flow not proven",
    )
    require(
        outbound.get("rfc5626.conformance.claimed") == "false",
        "bounded behavior must not become RFC 5626 conformance",
    )
    for key in {
        "flow1.require.outbound.observed",
        "flow1.crlf.ping.observed",
        "flow1.crlf.pong.observed",
        "flow1.failure.detected",
        "flow2.same.binding.key",
        "flow2.registration.accepted",
        "flow2.inbound.request.observed",
        "flow2.inbound.response.observed",
    }:
        require(outbound.get(key) == "true", f"outbound-flow fact not true: {key}")

    summary = {
        "schema": "baudot.vrs-outbound-route-chain-evidence@1",
        "scenario": "VRS-OUTBOUND-ROUTE-CHAIN",
        "registrationRouteChain": "PASS",
        "outboundFlowEstablished": True,
        "outboundRequireObserved": True,
        "keepaliveRoundTripObserved": True,
        "flowFailureDetected": True,
        "replacementBindingKeyPreserved": True,
        "replacementRegistrationAccepted": True,
        "inboundRequestTraversedReplacementFlow": True,
        "dialAroundDialogEstablished": True,
        "rfc5626Conformance": "NOT_CLAIMED",
        "perCallValidation": "NOT_COMPOSED",
        "trsBusinessAuthority": "NOT_DERIVED",
        "compensability": "NOT_DERIVED",
        "fundClaimAuthority": "NOT_DERIVED",
        "mediaReadiness": False,
        "rttReadiness": False,
        "videoReadiness": False,
        "productionProviderProbed": False,
        "claim": "synthetic-outbound-flow-and-route-composition-only",
        "result": "PASS",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("VRS outbound-flow -> dial-around route chain independently reduced: PASS")
    print(
        "  outbound registration -> keepalive -> flow replacement -> "
        "inbound route -> dial-around dialog"
    )
    print("  RFC 5626 conformance / media / business authority: not derived")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
