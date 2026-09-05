#!/usr/bin/env python3
"""Validate RFC 8865 T.140 data-channel baseline vectors."""

from __future__ import annotations

import json
from pathlib import Path

from baudot_reference.rfc8865 import (
    DEFAULT_CPS,
    DEFAULT_TRANSMISSION_INTERVAL_MS,
    T140DataChannelMessage,
    T140DataChannelProfile,
)
from baudot_reference.t140block import T140Block

ROOT = Path(__file__).resolve().parents[1]
VECTOR_DIR = ROOT / "testkit" / "rfc8865"
REQUIRED_CASES = {
    "single-block-message",
    "multiple-block-message",
    "empty-block-within-message",
    "missing-text-marker-message",
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
        raise SystemExit("No RFC 8865 vector suites found")

    for path in paths:
        suite = load(path)
        if suite.get("status") != "baseline":
            raise ValueError(f"{path}: RFC 8865 suite must remain status=baseline")
        scope = suite.get("scope")
        if not isinstance(scope, str) or "complete RFC 8865 conformance" not in scope:
            raise ValueError(f"{path}: scope must explicitly avoid complete RFC 8865 conformance")

        profile = suite.get("profile")
        if not isinstance(profile, dict):
            raise ValueError(f"{path}: profile must be an object")
        reference_profile = T140DataChannelProfile()
        expected_profile = {
            "subprotocol": reference_profile.subprotocol,
            "reliable": reference_profile.reliable,
            "ordered": reference_profile.ordered,
            "defaultTransmissionIntervalMs": DEFAULT_TRANSMISSION_INTERVAL_MS,
            "defaultCps": DEFAULT_CPS,
            "usesRfc2198Redundancy": False,
        }
        if profile != expected_profile:
            raise ValueError(f"{path}: RFC 8865 profile mismatch: expected {expected_profile}, got {profile}")

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

            raw_blocks = vector.get("blocks")
            if not isinstance(raw_blocks, list) or not raw_blocks:
                raise ValueError(f"{path}: {vector_id} blocks must be a non-empty list")
            blocks = [T140Block.from_hex(item) for item in raw_blocks]
            message = T140DataChannelMessage.from_blocks(blocks)

            expected_hex = vector.get("messageHex")
            if message.utf8_hex != expected_hex:
                raise ValueError(
                    f"{path}: {vector_id} message mismatch: expected {expected_hex}, got {message.utf8_hex}"
                )
            expected_text = vector.get("expectedText")
            if message.text != expected_text:
                raise ValueError(
                    f"{path}: {vector_id} text mismatch: expected {expected_text!r}, got {message.text!r}"
                )

            received = T140DataChannelMessage.from_bytes(bytes.fromhex(expected_hex))
            if received.text != expected_text:
                raise ValueError(f"{path}: {vector_id} receive path did not preserve T.140 content")

        missing = REQUIRED_CASES - seen
        if missing:
            raise ValueError(f"{path}: missing RFC 8865 vectors: {sorted(missing)}")

        deferred = suite.get("deferred")
        if not isinstance(deferred, list):
            raise ValueError(f"{path}: deferred must be a list")
        for boundary in {
            "SDP dcmap and dcsa negotiation",
            "SCTP stream creation",
            "channel-failure detection and reestablishment",
        }:
            if boundary not in deferred:
                raise ValueError(f"{path}: deferred scope must preserve boundary: {boundary}")

        print(f"✓ RFC 8865 vectors {suite.get('id')}@{suite.get('version')}: {len(vectors)} cases")

    print(f"Baudot RFC 8865 data-channel boundary valid: {len(paths)} vector suite(s).")


if __name__ == "__main__":
    main()
