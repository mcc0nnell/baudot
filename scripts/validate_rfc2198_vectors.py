#!/usr/bin/env python3
"""Validate RFC 2198 RED wire vectors specialized for T140blocks."""

from __future__ import annotations

import json
from pathlib import Path

from baudot_reference.rfc2198 import RedundantT140Generation, Rfc2198T140Packet
from baudot_reference.t140block import T140Block

ROOT = Path(__file__).resolve().parents[1]
VECTOR_DIR = ROOT / "testkit" / "rfc2198"
REQUIRED_CASES = {
    "one-redundant-generation",
    "two-redundant-generations",
    "empty-redundant-generation",
}


def load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def main() -> None:
    paths = sorted(VECTOR_DIR.glob("*.json"))
    if not paths:
        raise SystemExit("No RFC 2198 T.140 vector suites found")

    for path in paths:
        suite = load(path)
        if suite.get("status") != "baseline":
            raise ValueError(f"{path}: RFC 2198 suite must remain status=baseline")
        scope = suite.get("scope")
        if not isinstance(scope, str) or "complete RFC 4103 conformance" not in scope:
            raise ValueError(f"{path}: scope must explicitly avoid complete RFC 4103 conformance")

        vectors = suite.get("vectors")
        if not isinstance(vectors, list) or not vectors:
            raise ValueError(f"{path}: vectors must be a non-empty list")

        seen: set[str] = set()
        for vector in vectors:
            if not isinstance(vector, dict):
                raise ValueError(f"{path}: vector must be an object")
            vector_id = vector.get("id")
            if not isinstance(vector_id, str) or not vector_id:
                raise ValueError(f"{path}: vector id must be a non-empty string")
            if vector_id in seen:
                raise ValueError(f"{path}: duplicate vector id {vector_id}")
            seen.add(vector_id)

            fields = vector.get("fields")
            if not isinstance(fields, dict):
                raise ValueError(f"{path}: {vector_id} fields must be an object")
            redundant_fields = fields.get("redundant")
            if not isinstance(redundant_fields, list) or not redundant_fields:
                raise ValueError(f"{path}: {vector_id} must declare redundant generations")

            redundant = tuple(
                RedundantT140Generation(
                    item["timestampOffset"],
                    T140Block.from_hex(item["blockHex"]),
                )
                for item in redundant_fields
            )
            packet = Rfc2198T140Packet(
                red_payload_type=fields["redPayloadType"],
                t140_payload_type=fields["t140PayloadType"],
                sequence_number=fields["sequenceNumber"],
                timestamp=fields["timestamp"],
                ssrc=fields["ssrc"],
                marker=fields["marker"],
                redundant=redundant,
                primary=T140Block.from_hex(fields["primaryHex"]),
            )

            actual_hex = packet.to_bytes().hex(" ")
            expected_hex = vector.get("packetHex")
            if actual_hex != expected_hex:
                raise ValueError(
                    f"{path}: {vector_id} wire mismatch: expected {expected_hex}, got {actual_hex}"
                )

            parsed = Rfc2198T140Packet.from_bytes(
                bytes.fromhex(expected_hex),
                expected_red_payload_type=fields["redPayloadType"],
                expected_t140_payload_type=fields["t140PayloadType"],
            )
            if parsed != packet:
                raise ValueError(f"{path}: {vector_id} parse/serialize round trip diverged")

        missing = REQUIRED_CASES - seen
        if missing:
            raise ValueError(f"{path}: missing RFC 2198 T.140 vectors: {sorted(missing)}")

        deferred = suite.get("deferred")
        if not isinstance(deferred, list):
            raise ValueError(f"{path}: deferred must be a list")
        for boundary in {
            "lost-packet detection",
            "redundant-block recovery",
            "out-of-order buffering",
        }:
            if boundary not in deferred:
                raise ValueError(f"{path}: deferred scope must preserve boundary: {boundary}")

        print(f"✓ RFC 2198 T.140 vectors {suite.get('id')}@{suite.get('version')}: {len(vectors)} cases")

    print(f"Baudot RFC 2198 T.140 wire boundary valid: {len(paths)} vector suite(s).")


if __name__ == "__main__":
    main()
