#!/usr/bin/env python3
"""Validate deterministic RFC 4103 redundancy recovery vectors."""

from __future__ import annotations

import json
from pathlib import Path

from baudot_reference.rfc2198 import RedundantT140Generation, Rfc2198T140Packet
from baudot_reference.rfc4103_recovery import recover_forward_gap
from baudot_reference.t140block import T140Block

ROOT = Path(__file__).resolve().parents[1]
VECTOR_DIR = ROOT / "testkit" / "rfc4103"
REQUIRED_CASES = {
    "no-gap",
    "recover-one-gap",
    "partially-unrecoverable-gap",
    "recover-empty-block",
    "sequence-wraparound",
    "first-observed-packet",
}


def load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def main() -> None:
    paths = sorted(VECTOR_DIR.glob("recovery-*.json"))
    if not paths:
        raise SystemExit("No RFC 4103 recovery vector suites found")

    for path in paths:
        suite = load(path)
        if suite.get("status") != "baseline":
            raise ValueError(f"{path}: recovery suite must remain status=baseline")
        scope = suite.get("scope")
        if not isinstance(scope, str) or "complete RFC 4103 receiver behavior" not in scope:
            raise ValueError(f"{path}: scope must explicitly avoid complete RFC 4103 receiver behavior")

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

            raw_redundant = vector.get("redundant")
            if not isinstance(raw_redundant, list):
                raise ValueError(f"{path}: {vector_id} redundant must be a list")
            redundant = tuple(
                RedundantT140Generation(
                    item["timestampOffset"],
                    T140Block.from_text(item["text"]),
                )
                for item in raw_redundant
            )
            if not redundant:
                raise ValueError(f"{path}: {vector_id} requires at least one redundant generation")

            current_sequence = vector["packetSequence"]
            packet = Rfc2198T140Packet(
                red_payload_type=100,
                t140_payload_type=98,
                sequence_number=current_sequence,
                timestamp=(current_sequence * 300) % (1 << 32),
                ssrc=1,
                marker=False,
                redundant=redundant,
                primary=T140Block.from_text(vector["primary"]),
            )
            actual = [
                {
                    "sequence": item.sequence_number,
                    "text": item.block.text,
                    "source": item.source,
                }
                for item in recover_forward_gap(vector.get("previousSequence"), packet)
            ]
            expected = vector.get("expected")
            if actual != expected:
                raise ValueError(
                    f"{path}: {vector_id} recovery mismatch: expected {expected}, got {actual}"
                )

        missing = REQUIRED_CASES - seen
        if missing:
            raise ValueError(f"{path}: missing recovery vectors: {sorted(missing)}")

        deferred = suite.get("deferred")
        if not isinstance(deferred, list):
            raise ValueError(f"{path}: deferred must be a list")
        for boundary in {
            "one-second out-of-order waiting policy",
            "late-packet reinsertion",
            "RTCP-assisted loss detection before idle periods",
        }:
            if boundary not in deferred:
                raise ValueError(f"{path}: deferred scope must preserve boundary: {boundary}")

        print(f"✓ RFC 4103 recovery vectors {suite.get('id')}@{suite.get('version')}: {len(vectors)} cases")

    print(f"Baudot RFC 4103 deterministic recovery valid: {len(paths)} vector suite(s).")


if __name__ == "__main__":
    main()
