#!/usr/bin/env python3
"""Validate revision-pinned public iTRS implementation provenance.

This gate prevents historical ACE code from silently becoming normative or
terminal authority for Baudot. It also checks that historical corroboration is
kept separate from Baudot-authored resilience extensions.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "testkit" / "itrs" / "research" / "public-itrs-donors-v1.json"
FIXTURE = ROOT / "testkit" / "itrs" / "fixtures" / "itrs-resolution-v1.json"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_CLASSES = {"normative-authority", "terminal-verdict-authority"}

EXPECTED_CORROBORATED = {
    "direct-e2u-sip",
    "alias-then-e2u-sip",
    "naptr-priority-selection",
    "sip-service-discovery",
}
EXPECTED_EXTENSIONS = {
    "no-route",
    "malformed-e2u-sip",
    "directory-unavailable",
    "slow-authority",
}


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    if manifest.get("schema") != "baudot.itrs-public-donors@1":
        raise ValueError("unexpected iTRS donor manifest schema")

    fixture_ids = {case["id"] for case in fixture.get("cases", [])}
    if not fixture_ids:
        raise ValueError("no iTRS fixture cases found")

    donors = manifest.get("donors", [])
    if not donors:
        raise ValueError("no public iTRS donors found")

    by_id = {donor.get("id"): donor for donor in donors}
    required = {
        "mitre-ace-direct-itrs-adapter",
        "mitre-ace-direct-itrs-lookup",
    }
    missing = required - set(by_id)
    if missing:
        raise ValueError(f"missing required pinned donor(s): {sorted(missing)}")

    for donor in donors:
        revision = str(donor.get("revision", ""))
        if not SHA40.fullmatch(revision):
            raise ValueError(f"{donor.get('id')}: revision must be a full 40-hex commit SHA")

        source_classes = set(donor.get("sourceClass", []))
        forbidden = source_classes & FORBIDDEN_CLASSES
        if forbidden:
            raise ValueError(
                f"{donor.get('id')}: historical source cannot hold authority class(es) {sorted(forbidden)}"
            )

        if not donor.get("repository") or not donor.get("paths"):
            raise ValueError(f"{donor.get('id')}: repository and exact source paths are required")

        never = " ".join(donor.get("neverAuthorityFor", [])).lower()
        if "terminal baudot verdict" not in never:
            raise ValueError(f"{donor.get('id')}: terminal-verdict non-authority must be explicit")

    lookup = by_id["mitre-ace-direct-itrs-lookup"]
    corroborated = set(lookup.get("corroboratesFixtureCases", []))
    extensions = set(lookup.get("baudotExtensionsNotClaimedFromDonor", []))

    if corroborated != EXPECTED_CORROBORATED:
        raise ValueError(
            f"historically corroborated case set drifted: {sorted(corroborated)}"
        )
    if extensions != EXPECTED_EXTENSIONS:
        raise ValueError(
            f"Baudot extension case set drifted: {sorted(extensions)}"
        )
    if corroborated & extensions:
        raise ValueError("a fixture cannot be both donor-corroborated and a Baudot-only extension")
    if corroborated | extensions != fixture_ids:
        raise ValueError(
            "public provenance classification must account for every iTRS fixture exactly once"
        )

    print("iTRS public provenance boundary: PASS")
    print(f"historically corroborated fixtures: {len(corroborated)}")
    print(f"Baudot resilience extensions: {len(extensions)}")


if __name__ == "__main__":
    main()
