#!/usr/bin/env python3
"""Validate transport-neutral T140block vectors against the reference primitive."""

from __future__ import annotations

import json
from pathlib import Path

from baudot_reference.t140block import InvalidT140Block, T140Block

ROOT = Path(__file__).resolve().parents[1]
VECTOR_DIR = ROOT / "testkit" / "t140blocks"
REQUIRED_CASES = {
    "empty-block",
    "ascii-block",
    "multibyte-integral-character",
    "preferred-line-separator-block",
    "crlf-sequence-block",
    "truncated-three-byte-character",
    "invalid-utf8-octet",
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
        raise SystemExit("No T140block vector suites found")

    for path in paths:
        suite = load(path)
        if suite.get("status") != "baseline":
            raise ValueError(f"{path}: T140block suite must remain status=baseline")
        scope = suite.get("scope")
        if not isinstance(scope, str) or "full T.140 conformance" not in scope:
            raise ValueError(f"{path}: scope must explicitly avoid full T.140 conformance")

        vectors = suite.get("vectors")
        if not isinstance(vectors, list) or not vectors:
            raise ValueError(f"{path}: vectors must be a non-empty list")

        seen: set[str] = set()
        for vector in vectors:
            if not isinstance(vector, dict):
                raise ValueError(f"{path}: every vector must be an object")
            vector_id = vector.get("id")
            if not isinstance(vector_id, str) or not vector_id:
                raise ValueError(f"{path}: vector id must be a non-empty string")
            if vector_id in seen:
                raise ValueError(f"{path}: duplicate vector id {vector_id}")
            seen.add(vector_id)

            payload_hex = vector.get("payloadHex")
            if not isinstance(payload_hex, str):
                raise ValueError(f"{path}: {vector_id} payloadHex must be a string")
            valid = vector.get("valid")
            if not isinstance(valid, bool):
                raise ValueError(f"{path}: {vector_id} valid must be boolean")

            try:
                block = T140Block.from_hex(payload_hex)
            except InvalidT140Block:
                if valid:
                    raise ValueError(f"{path}: {vector_id} declared valid but primitive rejected it")
                continue

            if not valid:
                raise ValueError(f"{path}: {vector_id} declared invalid but primitive accepted it")

            expected_text = vector.get("expectedText")
            if block.text != expected_text:
                raise ValueError(
                    f"{path}: {vector_id} text mismatch: expected {expected_text!r}, got {block.text!r}"
                )
            expected_code_points = vector.get("expectedCodePoints")
            if not isinstance(expected_code_points, list):
                raise ValueError(f"{path}: {vector_id} expectedCodePoints must be a list")
            actual_code_points = [f"U+{value:04X}" for value in block.code_points]
            if actual_code_points != expected_code_points:
                raise ValueError(
                    f"{path}: {vector_id} code-point mismatch: expected {expected_code_points}, "
                    f"got {actual_code_points}"
                )

        missing = REQUIRED_CASES - seen
        if missing:
            raise ValueError(f"{path}: missing T140block vectors: {sorted(missing)}")

        deferred = suite.get("deferred")
        if not isinstance(deferred, list):
            raise ValueError(f"{path}: deferred must be a list")
        for boundary in {
            "RTP text/t140 payload headers",
            "RFC 2198 redundancy",
            "SCTP user-message grouping of multiple T140blocks",
        }:
            if boundary not in deferred:
                raise ValueError(f"{path}: deferred scope must preserve boundary: {boundary}")

        print(f"✓ T140block vectors {suite.get('id')}@{suite.get('version')}: {len(vectors)} cases")

    print(f"Baudot T140block boundary valid: {len(paths)} vector suite(s).")


if __name__ == "__main__":
    main()
