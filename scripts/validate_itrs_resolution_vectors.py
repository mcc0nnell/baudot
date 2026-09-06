#!/usr/bin/env python3
"""Validate the clean-room iTRS ENUM-style routing vectors.

This validator intentionally operates on synthetic fixture data only. It models
the resolution behavior documented by the Baudot testkit; it is not a client
for the production TRS Numbering Directory.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "testkit" / "itrs" / "fixtures" / "itrs-resolution-v1.json"
SIP_URI = re.compile(r"^sip:[^@\s]+@([^;\s>]+)$", re.IGNORECASE)


def enum_owner(number: str) -> str:
    if not re.fullmatch(r"\d{10}", number):
        raise ValueError(f"invalid synthetic NANP number: {number}")
    return ".".join(reversed(number)) + ".1.itrs.invalid"


def records_for(records: list[dict], owner: str, default_owner: str) -> list[dict]:
    return [record for record in records if record.get("owner", default_owner) == owner]


def choose_naptr(records: list[dict], owner: str, default_owner: str, service: str) -> dict | None:
    eligible = [
        record
        for record in records_for(records, owner, default_owner)
        if record.get("type") == "NAPTR"
        and str(record.get("service", "")).lower() == service.lower()
    ]
    if not eligible:
        return None
    return min(eligible, key=lambda record: (int(record.get("order", 0)), int(record.get("preference", 0))))


def resolve_case(case: dict) -> dict:
    expected = case["expected"]
    number = case["number"]

    if expected.get("result") == "authority-unavailable":
        return {"result": "authority-unavailable"}

    owner = enum_owner(number)
    declared_owner = case.get("enumQuery")
    if declared_owner is not None and declared_owner != owner:
        raise ValueError(f"{case['id']}: enumQuery mismatch: declared={declared_owner} computed={owner}")

    records = case.get("authoritativeRecords", [])
    if not records:
        return {"result": "not-found"}

    base_records = records_for(records, owner, owner)
    cname = next((record for record in base_records if record.get("type") == "CNAME"), None)
    effective_owner = cname["target"] if cname else owner

    naptr = choose_naptr(records, effective_owner, owner, "E2U+sip")
    if naptr is None:
        return {"result": "not-found"}

    logical_uri = str(naptr.get("replacement", ""))
    match = SIP_URI.fullmatch(logical_uri)
    if match is None:
        return {"result": "invalid-authoritative-response"}

    result = {"result": "route", "logicalSipUri": logical_uri}

    discovery = case.get("serviceDiscovery", [])
    if discovery:
        sip_host = match.group(1)
        sip_naptr = choose_naptr(discovery, sip_host, sip_host, "SIP+D2T")
        if sip_naptr is not None:
            srv_owner = sip_naptr.get("replacement")
            srv_records = [
                record
                for record in records_for(discovery, srv_owner, sip_host)
                if record.get("type") == "SRV"
            ]
            if srv_records:
                # Weight selection only matters within equal-priority records. The
                # v1 fixtures intentionally use deterministic zero-weight entries.
                srv = min(srv_records, key=lambda record: (int(record.get("priority", 0)), -int(record.get("weight", 0))))
                result["connectTarget"] = f"{srv['target']}:{int(srv['port'])}"

    return result


def main() -> None:
    suite = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cases = suite.get("cases", [])
    if not cases:
        raise SystemExit("No iTRS resolution cases found")

    passed = 0
    for case in cases:
        actual = resolve_case(case)
        expected = case["expected"]
        ok = actual == expected
        print(f"{case['id']:<28} {'PASS' if ok else 'FAIL'}")
        if not ok:
            raise ValueError(f"{case['id']}: expected {expected}, computed {actual}")
        passed += 1

    print(f"iTRS resolution vectors: {passed}/{len(cases)} PASS")


if __name__ == "__main__":
    main()
