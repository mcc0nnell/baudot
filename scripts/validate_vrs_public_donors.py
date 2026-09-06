#!/usr/bin/env python3
"""Validate revision-pinned public VRS implementation donor metadata."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "testkit" / "vrs" / "research" / "public-implementation-donors-v1.json"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
REQUIRED = {
    "mitre-fcc-vatrp-desktop": "9f82469ba8c591869c1e9ce9fc66b866ab5983a4",
    "mitre-fcc-vatrp-webrtc": "2aa96bb7306d0482da9ca4412a6cf520ded6a6cc",
    "fcc-vtc-secure-linphone": "60f23ce7845cdaa13f442bb9fa8087336dbfd495",
}
FORBIDDEN_CLASSES = {"normative-authority", "terminal-verdict-authority", "current-provider-truth"}


def main() -> int:
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if value.get("schema") != "baudot.vrs-public-implementation-donors@1":
        raise ValueError("donor manifest schema drift")
    if value.get("status") != "research":
        raise ValueError("donor manifest must remain research")
    rule = value.get("rule", "")
    if "never supplies normative or terminal verdict authority" not in rule:
        raise ValueError("historical donor authority boundary weakened")

    donors = value.get("donors")
    if not isinstance(donors, list):
        raise ValueError("donors must be a list")
    by_id = {donor.get("id"): donor for donor in donors if isinstance(donor, dict)}
    if set(by_id) != set(REQUIRED):
        raise ValueError(f"donor set drift: {sorted(by_id)}")

    for donor_id, expected_revision in REQUIRED.items():
        donor = by_id[donor_id]
        revision = donor.get("revision")
        if revision != expected_revision or not HEX40.fullmatch(str(revision)):
            raise ValueError(f"{donor_id}: exact revision pin drift")
        repository = donor.get("repository")
        if not isinstance(repository, str) or repository.count("/") != 1:
            raise ValueError(f"{donor_id}: invalid repository identity")
        classes = donor.get("sourceClass")
        if not isinstance(classes, list) or not classes:
            raise ValueError(f"{donor_id}: sourceClass required")
        forbidden = FORBIDDEN_CLASSES.intersection(classes)
        if forbidden:
            raise ValueError(f"{donor_id}: historical source granted forbidden authority {sorted(forbidden)}")
        paths = donor.get("paths")
        if not isinstance(paths, list) or not paths or not all(isinstance(p, str) and p for p in paths):
            raise ValueError(f"{donor_id}: pinned source paths required")
        never = donor.get("neverAuthorityFor")
        if not isinstance(never, list) or "terminal Baudot verdicts" not in never:
            raise ValueError(f"{donor_id}: terminal authority exclusion required")

        for linked in donor.get("linkedSources", []):
            if not isinstance(linked, dict):
                raise ValueError(f"{donor_id}: linked source must be an object")
            linked_revision = linked.get("revision")
            if not isinstance(linked_revision, str) or not HEX40.fullmatch(linked_revision):
                raise ValueError(f"{donor_id}: linked source must use an exact 40-hex revision")

        print(f"✓ donor {donor_id}: {repository}@{revision[:12]} authority-bounded")

    print("VRS public implementation donor manifest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
