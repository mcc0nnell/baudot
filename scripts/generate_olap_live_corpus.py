#!/usr/bin/env python3
"""Generate the deterministic privacy-reduced CDR corpus for the live OLAP bake-off."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

FORBIDDEN = {
    "fromTn",
    "toTn",
    "subscriberId",
    "subscriberName",
    "claimApproved",
    "paymentAuthorized",
    "compensable",
    "providerCertified",
    "accessibilityReady",
    "rawPayload",
}

PROVIDERS = ["provider-a", "provider-b", "provider-c", "provider-d"]
SERVICES = ["VRS", "IP_CTS", "IP_RELAY", "TTY"]
DIRECTIONS = ["INBOUND", "OUTBOUND"]
OUTCOMES = ["COMPLETED", "BUSY", "NO_ANSWER", "FAILED"]
START = datetime(2026, 8, 1, tzinfo=timezone.utc)
WINDOW = timedelta(days=30)


def make_row(index: int, rows: int) -> dict:
    event_time = START + (WINDOW * index / rows)
    return {
        "eventTime": int(event_time.timestamp() * 1000),
        "eventId": f"olap-event-{index:08d}",
        "callId": f"olap-call-{index:08d}",
        "providerId": PROVIDERS[index % len(PROVIDERS)],
        "serviceType": SERVICES[(index // len(PROVIDERS)) % len(SERVICES)],
        "direction": DIRECTIONS[(index // (len(PROVIDERS) * len(SERVICES))) % len(DIRECTIONS)],
        "durationSeconds": 20 + ((index * 97) % 3580),
        "outcome": OUTCOMES[(index // (len(PROVIDERS) * len(SERVICES))) % len(OUTCOMES)],
        "sourceObservationCount": 1 + (index % 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=20000)
    parser.add_argument("--out", default="target/olap-live/cdr_analytics_v1.jsonl")
    parser.add_argument("--metadata", default="target/olap-live/corpus-metadata.json")
    args = parser.parse_args()

    if args.rows < 100:
        raise SystemExit("rows must be >= 100")

    out = Path(args.out)
    metadata_path = Path(args.metadata)
    out.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()
    first_time = None
    last_time = None
    provider_service = set()
    provider_outcome = set()

    with out.open("wb") as handle:
        for index in range(args.rows):
            row = make_row(index, args.rows)
            forbidden = FORBIDDEN.intersection(row)
            if forbidden:
                raise AssertionError(f"forbidden OLAP fields present: {sorted(forbidden)}")
            provider_service.add((row["providerId"], row["serviceType"]))
            provider_outcome.add((row["providerId"], row["outcome"]))
            raw = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            digest.update(raw)
            handle.write(raw)
            first_time = row["eventTime"] if first_time is None else first_time
            last_time = row["eventTime"]

    if len(provider_service) != len(PROVIDERS) * len(SERVICES):
        raise AssertionError("corpus does not cover full provider x service Cartesian set")
    if len(provider_outcome) != len(PROVIDERS) * len(OUTCOMES):
        raise AssertionError("corpus does not cover full provider x outcome Cartesian set")

    metadata = {
        "schema": "baudot.olap-live-corpus@1",
        "rows": args.rows,
        "sha256": digest.hexdigest(),
        "firstEventTime": first_time,
        "lastEventTime": last_time,
        "projection": "cdr_analytics_v1",
        "topic": "baudot.olap.cdr.v1",
        "providerServiceCombinations": len(provider_service),
        "providerOutcomeCombinations": len(provider_outcome),
        "forbiddenFields": sorted(FORBIDDEN),
        "synthetic": True,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(json.dumps(metadata, sort_keys=True))


if __name__ == "__main__":
    main()
