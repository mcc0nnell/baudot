#!/usr/bin/env python3
"""Validate the clean-room public VRS/RUE research matrix and fixtures."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VRS_DIR = ROOT / "testkit" / "vrs"
MATRIX_PATH = VRS_DIR / "public-interoperability-matrix-v1.json"
PROVIDER_LIST_PATH = VRS_DIR / "fixtures" / "provider-list-v1.json"
DIAL_AROUND_PATH = VRS_DIR / "fixtures" / "rue-one-stage-dial-around-invite.txt"

ALLOWED_ROW_STATES = {
    "planned",
    "planned-offline-only",
    "fixture-ready",
    "partially-runnable",
}
REQUIRED_AUTHORITIES = {
    "us-47cfr-64.621",
    "sipforum-twg6-2.0",
    "ietf-rfc9248",
    "ietf-rum-2019-event",
    "mitre-national-test-lab-2024",
}
REQUIRED_ROWS = {
    "RUE-REG-001",
    "RUE-DIAL-001",
    "RUE-DIAL-002",
    "RUE-MIDCALL-001",
    "RUE-RTT-001",
    "RUE-RTT-002",
    "RUE-VIDEO-001",
    "RUE-SEC-001",
    "RUE-ICE-001",
    "RUE-PROV-001",
    "RUE-OWNER-001",
    "RUE-EMERG-001",
}
E164_DIAL_AROUND = "+12025550199"
DEFAULT_PROVIDER = "provider-a.example"
DIAL_AROUND_PROVIDER = "provider-b.example"


def load_object(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be a JSON object")
    return value


def non_empty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: must be a non-empty string")
    return value


def non_empty_string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label}: must be a non-empty list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{label}: all values must be non-empty strings")
    return value


def validate_matrix() -> dict:
    matrix = load_object(MATRIX_PATH)
    if matrix.get("schema") != "baudot.vrs-public-interoperability-matrix@1":
        raise ValueError("matrix: unexpected schema")
    if matrix.get("status") != "research":
        raise ValueError("matrix: status must remain research")
    if matrix.get("generatedFromPublicSourcesOnly") is not True:
        raise ValueError("matrix: public-source boundary must remain explicit")

    authorities = matrix.get("authorities")
    if not isinstance(authorities, list) or not authorities:
        raise ValueError("matrix: authorities must be a non-empty list")
    authority_ids: set[str] = set()
    for index, authority in enumerate(authorities):
        if not isinstance(authority, dict):
            raise ValueError(f"matrix: authority {index} must be an object")
        authority_id = non_empty_string(authority.get("id"), f"matrix: authority {index} id")
        if authority_id in authority_ids:
            raise ValueError(f"matrix: duplicate authority id {authority_id}")
        authority_ids.add(authority_id)
        non_empty_string(authority.get("kind"), f"matrix: authority {authority_id} kind")
        non_empty_string(authority.get("title"), f"matrix: authority {authority_id} title")
        url = non_empty_string(authority.get("url"), f"matrix: authority {authority_id} url")
        if not url.startswith("https://"):
            raise ValueError(f"matrix: authority {authority_id} must use HTTPS")

    missing_authorities = REQUIRED_AUTHORITIES - authority_ids
    if missing_authorities:
        raise ValueError(f"matrix: missing authorities {sorted(missing_authorities)}")

    boundary = matrix.get("versionBoundary")
    if not isinstance(boundary, dict):
        raise ValueError("matrix: versionBoundary must be an object")
    if boundary.get("regulatoryProviderProfile") != "TWG-6-1.0":
        raise ValueError("matrix: regulatory provider profile must remain TWG-6-1.0")
    if boundary.get("newerRatifiedIndustryProviderProfile") != "TWG-6-2.0":
        raise ValueError("matrix: newer industry profile must remain TWG-6-2.0")
    if boundary.get("rueProfile") != "RFC 9248":
        raise ValueError("matrix: RUE profile must remain RFC 9248")

    rows = matrix.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("matrix: rows must be a non-empty list")
    row_ids: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"matrix: row {index} must be an object")
        row_id = non_empty_string(row.get("id"), f"matrix: row {index} id")
        if row_id in row_ids:
            raise ValueError(f"matrix: duplicate row id {row_id}")
        row_ids.add(row_id)
        non_empty_string(row.get("family"), f"matrix: row {row_id} family")
        state = non_empty_string(row.get("status"), f"matrix: row {row_id} status")
        if state not in ALLOWED_ROW_STATES:
            raise ValueError(f"matrix: unsupported research state {state} for {row_id}")
        non_empty_string(row.get("objective"), f"matrix: row {row_id} objective")
        row_authorities = set(non_empty_string_list(row.get("authority"), f"matrix: row {row_id} authority"))
        unknown = row_authorities - authority_ids
        if unknown:
            raise ValueError(f"matrix: row {row_id} references unknown authorities {sorted(unknown)}")
        non_empty_string_list(row.get("positiveFacts"), f"matrix: row {row_id} positiveFacts")
        non_empty_string_list(row.get("doesNotEstablish"), f"matrix: row {row_id} doesNotEstablish")

        fixture = row.get("fixture")
        if fixture is not None:
            fixture_path = (ROOT / non_empty_string(fixture, f"matrix: row {row_id} fixture")).resolve()
            if VRS_DIR.resolve() not in fixture_path.parents:
                raise ValueError(f"matrix: row {row_id} fixture escapes testkit/vrs")
            if not fixture_path.is_file():
                raise ValueError(f"matrix: row {row_id} fixture missing: {fixture}")

    missing_rows = REQUIRED_ROWS - row_ids
    extra_rows = row_ids - REQUIRED_ROWS
    if missing_rows or extra_rows:
        raise ValueError(
            f"matrix: row set drift; missing={sorted(missing_rows)} extra={sorted(extra_rows)}"
        )

    emergency = next(row for row in rows if row["id"] == "RUE-EMERG-001")
    safety_rule = non_empty_string(emergency.get("safetyRule"), "matrix: RUE-EMERG-001 safetyRule")
    if "No public Baudot test originates a real emergency call" not in safety_rule:
        raise ValueError("matrix: emergency row must preserve no-real-call boundary")

    print(f"✓ VRS matrix: {len(rows)} rows / {len(authority_ids)} authorities")
    return matrix


def validate_provider_list() -> None:
    fixture = load_object(PROVIDER_LIST_PATH)
    if fixture.get("synthetic") is not True:
        raise ValueError("provider list: fixture must remain synthetic")
    if fixture.get("sourceShape") != "RFC 9248 ProviderList normative OpenAPI":
        raise ValueError("provider list: must identify the normative RFC 9248 OpenAPI shape")

    providers = fixture.get("providers")
    if not isinstance(providers, list) or len(providers) < 2:
        raise ValueError("provider list: at least two synthetic providers required")

    names: set[str] = set()
    entry_points: set[str] = set()
    for index, provider in enumerate(providers):
        if not isinstance(provider, dict):
            raise ValueError(f"provider list: provider {index} must be an object")
        if "entryPoint" in provider:
            raise ValueError(
                "provider list: illustrative entryPoint field is forbidden; "
                "RFC 9248 Section 9.3.1 normative OpenAPI requires providerEntryPoint"
            )
        name = non_empty_string(provider.get("name"), f"provider list: provider {index} name")
        entry_point = non_empty_string(
            provider.get("providerEntryPoint"),
            f"provider list: provider {index} providerEntryPoint",
        )
        if name in names or entry_point in entry_points:
            raise ValueError("provider list: duplicate provider name or providerEntryPoint")
        names.add(name)
        entry_points.add(entry_point)
        domain = entry_point.split("/", 1)[0]
        if not domain.endswith(".example"):
            raise ValueError(f"provider list: non-reserved fixture domain {entry_point}")

    if {DEFAULT_PROVIDER, DIAL_AROUND_PROVIDER} - entry_points:
        raise ValueError("provider list: dial-around fixture providers must be present")

    print(f"✓ synthetic ProviderList: {len(providers)} normative providerEntryPoint entries")


def parse_sip_fixture(path: Path) -> tuple[str, dict[str, str]]:
    raw_lines = path.read_text(encoding="utf-8").splitlines()
    lines = [line.strip() for line in raw_lines if line.strip() and not line.lstrip().startswith("#")]
    if not lines:
        raise ValueError("dial-around fixture: no SIP message found")
    start_line = lines[0]
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            raise ValueError(f"dial-around fixture: malformed header line: {line}")
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    return start_line, headers


def validate_dial_around_fixture() -> None:
    start_line, headers = parse_sip_fixture(DIAL_AROUND_PATH)
    expected_uri = f"sip:{E164_DIAL_AROUND}@{DIAL_AROUND_PROVIDER};user=phone"
    if start_line != f"INVITE {expected_uri} SIP/2.0":
        raise ValueError("dial-around fixture: Request-URI must bind called number to selected provider")

    to_value = non_empty_string(headers.get("to"), "dial-around fixture: To")
    if f"<{expected_uri}>" not in to_value:
        raise ValueError("dial-around fixture: To must preserve called number and selected provider")

    from_value = non_empty_string(headers.get("from"), "dial-around fixture: From")
    if f"@{DEFAULT_PROVIDER};user=phone" not in from_value:
        raise ValueError("dial-around fixture: From must remain associated with default provider")
    if DIAL_AROUND_PROVIDER in from_value:
        raise ValueError("dial-around fixture: selected provider must not rewrite source identity")

    via_value = non_empty_string(headers.get("via"), "dial-around fixture: Via")
    if not re.match(r"^SIP/2\.0/TLS\s+", via_value, flags=re.IGNORECASE):
        raise ValueError("dial-around fixture: static transport fixture must use TLS")

    content_length = non_empty_string(headers.get("content-length"), "dial-around fixture: Content-Length")
    if content_length != "0":
        raise ValueError("dial-around fixture: SDP/media must remain out of scope")
    if "content-type" in headers:
        raise ValueError("dial-around fixture: signaling-only fixture must not add media")

    print("✓ one-stage dial-around fixture: selected route preserved / media unclaimed")


def main() -> int:
    validate_matrix()
    validate_provider_list()
    validate_dial_around_fixture()
    print("VRS public interoperability research inputs: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
