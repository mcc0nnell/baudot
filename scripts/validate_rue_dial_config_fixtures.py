#!/usr/bin/env python3
"""Validate synthetic RFC 9248 ProviderConfig and two-stage dial-around inputs."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "testkit" / "vrs" / "fixtures"
PROVIDER_CONFIG = FIXTURES / "provider-config-provider-b-v1.json"
TWO_STAGE_INVITE = FIXTURES / "rue-two-stage-front-door-invite.txt"

EXPECTED_ENTRY = "provider-b.example"
EXPECTED_LANGUAGE = "ase"
EXPECTED_FRONT_DOOR = "sip:front-door@provider-b.example"
EXPECTED_ONE_STAGE = "sip:one-stage@provider-b.example"
ULTIMATE_CALLED_NUMBER = "+12025550199"


def load_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def validate_provider_config() -> None:
    value = load_object(PROVIDER_CONFIG)
    if value.get("synthetic") is not True:
        raise ValueError("ProviderConfig fixture must remain synthetic")
    if value.get("sourceShape") != "RFC 9248 ProviderConfigurationData normative OpenAPI":
        raise ValueError("ProviderConfig fixture must identify the normative OpenAPI schema")
    if value.get("providerEntryPoint") != EXPECTED_ENTRY:
        raise ValueError("ProviderConfig fixture providerEntryPoint drift")

    dial_around = value.get("dial-around")
    if not isinstance(dial_around, list) or len(dial_around) != 1:
        raise ValueError("ProviderConfig fixture must contain exactly one bounded dial-around arm")
    arm = dial_around[0]
    if not isinstance(arm, dict):
        raise ValueError("dial-around arm must be an object")
    if set(arm) != {"language", "front-door", "oneStage"}:
        raise ValueError("dial-around arm must preserve normative required fields")
    if arm.get("language") != EXPECTED_LANGUAGE:
        raise ValueError("dial-around language must remain ase for this fixture")
    if arm.get("front-door") != EXPECTED_FRONT_DOOR:
        raise ValueError("two-stage front-door drift")
    if arm.get("oneStage") != EXPECTED_ONE_STAGE:
        raise ValueError("one-stage configuration URI drift")

    print("✓ ProviderConfig: normative dial-around shape / ase / reserved domain")


def parse_sip(path: Path) -> tuple[str, dict[str, str], str]:
    raw = path.read_text(encoding="utf-8")
    lines = [line.strip() for line in raw.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not lines:
        raise ValueError("two-stage fixture contains no SIP request")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            raise ValueError(f"malformed SIP header: {line}")
        name, value = line.split(":", 1)
        headers[name.lower()] = value.strip()
    return lines[0], headers, raw


def validate_two_stage_invite() -> None:
    start_line, headers, raw = parse_sip(TWO_STAGE_INVITE)
    if start_line != f"INVITE {EXPECTED_FRONT_DOOR} SIP/2.0":
        raise ValueError("two-stage Request-URI must target the configured front-door in this fixture")
    if headers.get("to") != f"<{EXPECTED_FRONT_DOOR}>":
        raise ValueError("RFC 9248 two-stage To URI must be the configured front-door")
    from_value = headers.get("from", "")
    if "@provider-a.example;user=phone" not in from_value:
        raise ValueError("two-stage fixture must preserve the default-provider source identity")
    if ULTIMATE_CALLED_NUMBER in raw:
        raise ValueError("ultimate called-party number must not appear in the initial two-stage INVITE")
    if headers.get("content-length") != "0" or "content-type" in headers:
        raise ValueError("two-stage route fixture must remain signaling-only")
    if not headers.get("via", "").lower().startswith("sip/2.0/tls "):
        raise ValueError("static two-stage transport fixture must use TLS")

    print("✓ two-stage front-door fixture: route distinct from ultimate destination / media unclaimed")


def main() -> int:
    validate_provider_config()
    validate_two_stage_invite()
    print("RUE dial-around configuration fixtures: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
