#!/usr/bin/env python3
"""Validate baseline RFC 4103 primary RTP wire vectors."""

from __future__ import annotations

import json
from pathlib import Path

from baudot_reference.rfc4103 import PrimaryT140RtpPacket, T140_CLOCK_RATE_HZ
from baudot_reference.t140block import T140Block

ROOT = Path(__file__).resolve().parents[1]
VECTOR_DIR = ROOT / "testkit" / "rfc4103"
REQUIRED_CASES = {
    "ordinary-primary-text",
    "marker-after-idle",
    "empty-primary-block",
    "multibyte-primary-block",
}


def load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def main() -> None:
    if T140_CLOCK_RATE_HZ != 1000:
        raise ValueError("RFC 4103 T.140 RTP clock rate must remain 1000 Hz")

    paths = sorted(VECTOR_DIR.glob("primary-*.json"))
    if not paths:
        raise SystemExit("No RFC 4103 primary RTP vector suites found")

    for path in paths:
        suite = load(path)
        if suite.get("status") != "baseline":
            raise ValueError(f"{path}: RFC 4103 suite must remain status=baseline")
        scope = suite.get("scope")
        if not isinstance(scope, str) or "complete RFC 4103 sender or receiver" not in scope:
            raise ValueError(f"{path}: scope must explicitly avoid a complete RFC 4103 claim")

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
            block_hex = fields.get("t140blockHex")
            if not isinstance(block_hex, str):
                raise ValueError(f"{path}: {vector_id} t140blockHex must be a string")

            packet = PrimaryT140RtpPacket(
                payload_type=fields["payloadType"],
                sequence_number=fields["sequenceNumber"],
                timestamp=fields["timestamp"],
                ssrc=fields["ssrc"],
                marker=fields["marker"],
                block=T140Block.from_hex(block_hex),
            )
            actual_hex = packet.to_bytes().hex(" ")
            expected_hex = vector.get("packetHex")
            if actual_hex != expected_hex:
                raise ValueError(
                    f"{path}: {vector_id} wire mismatch: expected {expected_hex}, got {actual_hex}"
                )

            parsed = PrimaryT140RtpPacket.from_bytes(
                bytes.fromhex(expected_hex),
                expected_payload_type=fields["payloadType"],
            )
            if parsed != packet:
                raise ValueError(f"{path}: {vector_id} parse/serialize round trip diverged")

        missing = REQUIRED_CASES - seen
        if missing:
            raise ValueError(f"{path}: missing RFC 4103 baseline vectors: {sorted(missing)}")

        deferred = suite.get("deferred")
        if not isinstance(deferred, list):
            raise ValueError(f"{path}: deferred must be a list")
        for boundary in {
            "RFC 2198 redundancy",
            "packet-loss recovery",
            "SDP payload-type negotiation",
        }:
            if boundary not in deferred:
                raise ValueError(f"{path}: deferred scope must preserve boundary: {boundary}")

        print(f"✓ RFC 4103 primary vectors {suite.get('id')}@{suite.get('version')}: {len(vectors)} cases")

    print(f"Baudot RFC 4103 primary boundary valid: {len(paths)} vector suite(s).")


if __name__ == "__main__":
    main()
