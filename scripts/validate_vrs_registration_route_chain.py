#!/usr/bin/env python3
"""Independently reduce the synthetic TND -> discovery -> REGISTER -> dial-around chain."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXECUTION = ROOT / "testkit" / "vrs" / "executions" / "RUE-REG-001-tls.json"
DISCOVERY = ROOT / "target" / "evidence" / "RUE-REG-001" / "discovery.json"
REGISTRATION_RESULT = (
    ROOT / "target" / "evidence" / "RUE-REG-001" / "tls-register-v1" / "registration-proof" / "result.properties"
)
SELECTION = ROOT / "target" / "evidence" / "RUE-PROV-001" / "provider-b-selection.json"
DIAL_RESULT = (
    ROOT / "target" / "evidence" / "RUE-DIAL-001" / "jain-one-stage-dial-around-v1" / "route-proof" / "result.properties"
)
OUT = ROOT / "target" / "evidence" / "VRS-REGISTRATION-ROUTE-CHAIN" / "summary.json"

EXPECTED_NUMBER = "+12025550101"
EXPECTED_DEFAULT_PROVIDER = "provider-a.example"
EXPECTED_DIAL_PROVIDER = "provider-b.example"


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
    execution = load_json(EXECUTION)
    require(execution.get("matrixRow") == "RUE-REG-001", "execution matrix row drift")
    require(execution.get("status") == "runnable-candidate", "registration execution status drift")
    require(execution.get("entrypoint") == "org.mcc0nnell.baudot.harness.RueRegistrationTlsProbe", "entrypoint drift")

    discovery = load_json(DISCOVERY)
    require(discovery.get("schema") == "baudot.rue-registration-discovery-evidence@1", "discovery schema drift")
    require(discovery.get("nanpNumber") == EXPECTED_NUMBER, "registration number drift")
    require(discovery.get("providerDomain") == EXPECTED_DEFAULT_PROVIDER, "default provider drift")
    require(discovery.get("tndUri") == f"sip:{EXPECTED_NUMBER}@{EXPECTED_DEFAULT_PROVIDER}", "TND URI drift")
    require(discovery.get("tndRouteOwner") == EXPECTED_DEFAULT_PROVIDER, "TND route owner drift")
    require(discovery.get("naptrService") == "SIPS+D2T", "TLS-preferred NAPTR service not selected")
    require(discovery.get("selectedTransport") == "tls", "registration discovery did not select TLS")
    require(discovery.get("tlsPreferredDiscoveryObserved") is True, "TLS preference evidence missing")
    require(discovery.get("liveDnsQueried") is False, "live DNS must not be queried in clean-room lane")
    require(discovery.get("liveTndQueried") is False, "live TND must not be queried in clean-room lane")

    registration = load_properties(REGISTRATION_RESULT)
    for key in {
        "tls.handshake.observed",
        "tls.provider.domain.certificate.bound",
        "register.initial.observed",
        "register.digest.challenge.observed",
        "register.digest.response.verified",
        "register.authenticated.observed",
        "register.accepted",
        "sip.supported.outbound.observed",
        "contact.ob.parameter.observed",
        "authorization.evidence.redacted",
    }:
        require(registration.get(key) == "true", f"registration fact not true: {key}")
    require(registration.get("provider.domain") == EXPECTED_DEFAULT_PROVIDER, "registered provider domain drift")
    require(registration.get("registered.number") == EXPECTED_NUMBER, "registered number drift")
    require(registration.get("discovery.transport") == discovery.get("selectedTransport"), "discovery/registration transport mismatch")
    require(registration.get("rfc5626.outbound.flow.proven") == "false", "outbound markers must not become RFC 5626 flow proof")
    require(registration.get("live.tnd.queried") == "false", "registration must not claim live TND")
    require(registration.get("live.dns.queried") == "false", "registration must not claim live DNS")
    require(registration.get("transport.claim") == "ephemeral-self-signed-loopback-tls-only", "TLS claim boundary drift")
    require(registration.get("claim") == "challenged-rue-registration-observation-only", "registration claim boundary drift")
    require(registration.get("scenario.result") == "PASS", "registration execution failed")

    selection = load_json(SELECTION)
    require(selection.get("schema") == "baudot.rue-provider-selection@1", "dial provider-selection schema drift")
    require(selection.get("providerEntryPoint") == EXPECTED_DIAL_PROVIDER, "dial-around provider selection drift")

    dial = load_properties(DIAL_RESULT)
    require(dial.get("default.provider.domain") == EXPECTED_DEFAULT_PROVIDER, "dial source default-provider identity drift")
    require(dial.get("selected.provider.domain") == EXPECTED_DIAL_PROVIDER, "dial selected-provider identity drift")
    require(dial.get("dialog.established") == "true", "dial-around dialog not established")
    require(dial.get("providerB.inviteObserved") == "true", "selected provider did not observe INVITE")
    require(dial.get("providerB.sourcePreserved") == "true", "default-provider source identity did not survive dial-around")
    require(dial.get("media.readiness.proven") == "false", "dialog success must not become media readiness")
    require(dial.get("rtt.readiness.proven") == "false", "dialog success must not become RTT readiness")
    require(dial.get("video.readiness.proven") == "false", "dialog success must not become video readiness")

    summary = {
        "schema": "baudot.vrs-registration-route-chain-evidence@1",
        "scenario": "VRS-REGISTRATION-ROUTE-CHAIN",
        "numberAssigned": True,
        "tndRouteResolved": True,
        "providerDomainPreserved": True,
        "tlsPreferredServiceSelected": True,
        "tlsHandshakeObserved": True,
        "digestChallengeObserved": True,
        "digestResponseVerified": True,
        "registrationAccepted": True,
        "dialAroundProviderSelected": EXPECTED_DIAL_PROVIDER,
        "selectedProviderInviteObserved": True,
        "dialogEstablished": True,
        "perCallValidation": "NOT_COMPOSED",
        "trsBusinessAuthority": "NOT_DERIVED",
        "compensability": "NOT_DERIVED",
        "fundClaimAuthority": "NOT_DERIVED",
        "mediaReadiness": False,
        "rttReadiness": False,
        "videoReadiness": False,
        "liveTndQueried": False,
        "liveDnsQueried": False,
        "productionProviderProbed": False,
        "claim": "synthetic-registration-and-route-composition-only",
        "result": "PASS",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("VRS registration -> route chain independently reduced: PASS")
    print("  TND route -> SIPS discovery -> challenged TLS REGISTER -> Provider-B dial-around dialog")
    print("  per-call validation / business authority / media readiness: deliberately not derived")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
