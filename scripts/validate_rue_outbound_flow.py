#!/usr/bin/env python3
"""Independently reduce the controlled RFC 5626 outbound-flow recovery proof."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT = (
    ROOT
    / "target"
    / "evidence"
    / "RUE-REG-001"
    / "outbound-flow-recovery-v1"
    / "outbound-flow-proof"
    / "result.properties"
)

EXPECTED_PROVIDER = "provider-a.example"
EXPECTED_NUMBER = "+12025550101"
EXPECTED_INSTANCE = "<urn:uuid:00000000-0000-4000-8000-000000000001>"
EXPECTED_REG_ID = "1"


def load_properties(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError(f"missing outbound-flow evidence: {path}")
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
    result = load_properties(RESULT)

    require(result.get("scenario.id") == "RUE-REG-001", "scenario drift")
    require(
        result.get("correlation.id") == "outbound-flow-recovery-v1",
        "correlation drift",
    )
    require(result.get("provider.domain") == EXPECTED_PROVIDER, "provider domain drift")
    require(result.get("registered.number") == EXPECTED_NUMBER, "number drift")
    require(
        result.get("binding.aor") == f"sip:{EXPECTED_NUMBER}@{EXPECTED_PROVIDER}",
        "AOR drift",
    )
    require(
        result.get("binding.sip.instance") == EXPECTED_INSTANCE,
        "+sip.instance drift",
    )
    require(result.get("binding.reg.id") == EXPECTED_REG_ID, "reg-id drift")

    for key in {
        "flow1.registration.accepted",
        "flow1.require.outbound.observed",
        "flow1.crlf.ping.observed",
        "flow1.crlf.pong.observed",
        "flow1.failure.detected",
        "flow2.same.binding.key",
        "flow2.registration.accepted",
        "flow2.inbound.request.observed",
        "flow2.inbound.response.observed",
        "rfc5626.outbound.flow.proven",
    }:
        require(result.get(key) == "true", f"outbound-flow fact not true: {key}")

    require(
        result.get("rfc5626.conformance.claimed") == "false",
        "bounded flow proof must not become RFC 5626 conformance",
    )
    require(
        result.get("live.provider.probed") == "false",
        "clean-room lane must not probe a live provider",
    )
    for key in {
        "media.readiness.proven",
        "rtt.readiness.proven",
        "video.readiness.proven",
    }:
        require(result.get(key) == "false", f"flow proof promoted readiness: {key}")

    require(
        result.get("transport.claim") == "ephemeral-self-signed-loopback-tls-only",
        "transport claim boundary drift",
    )
    require(
        result.get("claim")
        == "controlled-rfc5626-outbound-flow-recovery-behavior-only",
        "outbound-flow claim boundary drift",
    )
    require(result.get("scenario.result") == "PASS", "outbound-flow execution failed")

    print("RUE-REG-001 controlled outbound-flow recovery: PASS")
    print(
        "  Require: outbound -> CRLF keepalive -> flow loss -> "
        "same binding key -> replacement flow -> inbound request"
    )
    print("  RFC 5626 conformance / media readiness: deliberately not claimed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
