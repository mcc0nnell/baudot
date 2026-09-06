#!/usr/bin/env python3
"""Prepare and independently verify the synthetic Kafka CDR proving lane."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "testkit" / "business" / "kafka-cdr-lane-v1.json"
OUT = ROOT / "target" / "kafka-cdr"
PRODUCER = OUT / "producer.txt"
CONSUMED = OUT / "consumed.txt"
REPLAY = OUT / "replay.txt"
EVIDENCE = OUT / "evidence.json"
IMAGE_ID = OUT / "docker-image-id.txt"

RESERVED_TN = re.compile(r"^20255501\d\d$")


def require(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"PASS {name}: {actual}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_time(value: str) -> datetime:
    if not value.endswith("Z"):
        raise AssertionError(f"timestamp must be UTC/Z: {value}")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def canonical(record: dict) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


def validate_fixture(fixture: dict) -> None:
    require("fixture schema", fixture["schema"], "baudot.kafka-cdr-lane@1")
    kafka = fixture["kafka"]
    require("Kafka version", kafka["version"], "4.3.1")
    require("Kafka release commit", kafka["releaseCommit"], "26b251a451ce941d3d7a55e6487bcb7f16b5ad48")
    require("Kafka image", kafka["dockerImage"], "apache/kafka:4.3.1")
    require("Kafka topic", kafka["topic"], "baudot.synthetic.cdr.v1")
    require("single partition", kafka["partitions"], 1)
    require("single-node replication factor", kafka["replicationFactor"], 1)
    require("record key", kafka["recordKey"], "callId")

    envelope = fixture["cdrEnvelope"]
    required = set(envelope["requiredFields"])
    forbidden = set(envelope["forbiddenAuthorityFields"])
    records = fixture["records"]
    require("record count", len(records), fixture["expected"]["recordCount"])

    event_ids: set[str] = set()
    call_ids: set[str] = set()
    for record in records:
        rid = record["eventId"]
        cid = record["callId"]
        if rid in event_ids:
            raise AssertionError(f"duplicate eventId: {rid}")
        if cid in call_ids:
            raise AssertionError(f"duplicate callId in final-CDR corpus: {cid}")
        event_ids.add(rid)
        call_ids.add(cid)

        missing = required - set(record)
        if missing:
            raise AssertionError(f"{rid}: missing fields {sorted(missing)}")
        leaked = forbidden & set(record)
        if leaked:
            raise AssertionError(f"{rid}: forbidden authority fields {sorted(leaked)}")
        require(f"{rid} schema", record["schema"], envelope["schema"])
        require(f"{rid} authority", record["authority"], envelope["authorityValue"])

        for field in ("fromTn", "toTn"):
            if not RESERVED_TN.fullmatch(record[field]):
                raise AssertionError(f"{rid}: {field} is not in reserved synthetic 202-555-01xx range")

        started = parse_time(record["startedAt"])
        ended = parse_time(record["endedAt"])
        duration = int((ended - started).total_seconds())
        require(f"{rid} duration", duration, record["durationSeconds"])

        refs = record["sourceObservationRefs"]
        if not refs or not all(ref.startswith("synthetic:") for ref in refs):
            raise AssertionError(f"{rid}: source references must remain synthetic")

    boundary = fixture["authorityBoundary"]
    for key, value in boundary.items():
        require(key, value, False)


def prepare(fixture: dict) -> None:
    validate_fixture(fixture)
    OUT.mkdir(parents=True, exist_ok=True)
    lines = [f"{record['callId']}|{canonical(record)}" for record in fixture["records"]]
    PRODUCER.write_text("\n".join(lines) + "\n")
    print(f"Wrote {PRODUCER.relative_to(ROOT)} with {len(lines)} keyed CDRs")


def parse_wire(path: Path) -> list[tuple[str, dict]]:
    rows: list[tuple[str, dict]] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        if "|" not in line:
            raise AssertionError(f"{path.name}: missing key separator")
        key, raw = line.split("|", 1)
        rows.append((key, json.loads(raw)))
    return rows


def verify(fixture: dict) -> None:
    validate_fixture(fixture)
    expected = [(record["callId"], record) for record in fixture["records"]]
    consumed = parse_wire(CONSUMED)
    replay = parse_wire(REPLAY)

    require("consumed record count", len(consumed), len(expected))
    require("replayed record count", len(replay), len(expected))
    require("single-partition keyed order", consumed, expected)
    require("replay equals original consume", replay, consumed)

    evidence = {
        "schema": "baudot.kafka-cdr-evidence@1",
        "fixtureSha256": sha256(FIXTURE),
        "producerSha256": sha256(PRODUCER),
        "consumedSha256": sha256(CONSUMED),
        "replaySha256": sha256(REPLAY),
        "kafka": fixture["kafka"],
        "dockerImageId": IMAGE_ID.read_text().strip() if IMAGE_ID.exists() else None,
        "recordCount": len(consumed),
        "keys": [key for key, _ in consumed],
        "replayIdentical": replay == consumed,
        "authority": {
            "cdrPersistenceProvesCompensability": False,
            "cdrPersistenceApprovesClaim": False,
            "kafkaDefinesEventSemantics": False
        },
        "verdict": "PASS"
    }
    EVIDENCE.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print("Kafka CDR publication/replay evidence: PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "verify"))
    args = parser.parse_args()
    fixture = json.loads(FIXTURE.read_text())

    if args.mode == "prepare":
        prepare(fixture)
    else:
        verify(fixture)


if __name__ == "__main__":
    main()
