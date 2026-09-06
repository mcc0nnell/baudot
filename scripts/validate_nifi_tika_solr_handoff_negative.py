#!/usr/bin/env python3
"""Negative qualification cases for the NiFi -> Tika/Solr provenance handoff."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "testkit" / "documents" / "live" / "public-rule.txt"
REQUIRED = {
    "sourceSystem",
    "sourceObjectId",
    "receivedAt",
    "contentSha256",
    "flowId",
    "correlationId",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def admit(raw: bytes, envelope: dict[str, object]) -> tuple[bool, str]:
    if set(envelope) != REQUIRED:
        return False, "upstream-envelope-shape-changed"
    if any(not envelope[field] for field in REQUIRED):
        return False, "required-provenance-empty"
    if envelope["sourceObjectId"] != SOURCE.name:
        return False, "source-object-id-mismatch"
    if envelope["flowId"] != "document-drop-ingest":
        return False, "flow-id-mismatch"
    if envelope["contentSha256"] != sha256_bytes(raw):
        return False, "content-hash-mismatch"
    return True, "admit"


def expect_reject(name: str, raw: bytes, envelope: dict[str, object], reason: str) -> None:
    admitted, actual = admit(raw, envelope)
    if admitted or actual != reason:
        raise AssertionError(f"{name}: expected reject/{reason}, got {admitted}/{actual}")
    print(f"PASS {name}: {actual}")


def main() -> None:
    raw = SOURCE.read_bytes()
    baseline = {
        "sourceSystem": "synthetic-permitted-document-drop",
        "sourceObjectId": SOURCE.name,
        "receivedAt": "epoch-ms:1788710400000",
        "contentSha256": sha256_bytes(raw),
        "flowId": "document-drop-ingest",
        "correlationId": "synthetic-negative-qualification",
    }

    admitted, reason = admit(raw, baseline)
    if not admitted or reason != "admit":
        raise AssertionError(f"baseline unexpectedly rejected: {reason}")
    print("PASS baseline admitted")

    mutated = dict(baseline)
    mutated["sourceObjectId"] = "renamed-object.txt"
    expect_reject("mutated source object id", raw, mutated, "source-object-id-mismatch")

    mutated = dict(baseline)
    mutated["flowId"] = "other-flow"
    expect_reject("mutated flow id", raw, mutated, "flow-id-mismatch")

    mutated = dict(baseline)
    mutated["contentSha256"] = "0" * 64
    expect_reject("mutated source hash", raw, mutated, "content-hash-mismatch")

    tampered_raw = raw + b"\nTAMPERED"
    expect_reject("mutated staged bytes", tampered_raw, baseline, "content-hash-mismatch")

    mutated = dict(baseline)
    mutated.pop("correlationId")
    expect_reject("missing upstream field", raw, mutated, "upstream-envelope-shape-changed")

    mutated = dict(baseline)
    mutated["documentId"] = mutated["sourceObjectId"]
    expect_reject("forbidden provenance alias", raw, mutated, "upstream-envelope-shape-changed")

    print("Baudot NiFi -> Tika -> Solr negative provenance qualification: PASS")


if __name__ == "__main__":
    main()
