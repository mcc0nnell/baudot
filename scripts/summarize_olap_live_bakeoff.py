#!/usr/bin/env python3
"""Combine Pinot and Druid live benchmark evidence without promoting performance into authority."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

EXPECTED_QUERY_ROWS = {
    "OLAP-Q001": 6,
    "OLAP-Q002": 4,
    "OLAP-Q003": 2880,
    "OLAP-Q004": 16,
    "OLAP-Q005": 1,
}


def load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pinot", required=True)
    parser.add_argument("--druid", required=True)
    parser.add_argument("--pinot-wait", required=True)
    parser.add_argument("--druid-wait", required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    pinot = load(args.pinot)
    druid = load(args.druid)
    pinot_wait = load(args.pinot_wait)
    druid_wait = load(args.druid_wait)
    corpus = load(args.corpus)

    expected_rows = corpus["rows"]
    if pinot_wait["rows"] != expected_rows or druid_wait["rows"] != expected_rows:
        raise AssertionError(
            f"ingested row mismatch: corpus={expected_rows}, pinot={pinot_wait['rows']}, druid={druid_wait['rows']}"
        )

    by_engine = {}
    for evidence in (pinot, druid):
        engine = evidence["engine"]
        queries = {item["id"]: item for item in evidence["queries"]}
        if set(queries) != set(EXPECTED_QUERY_ROWS):
            raise AssertionError(f"{engine}: benchmark query set mismatch")
        for query_id, expected in EXPECTED_QUERY_ROWS.items():
            actual = queries[query_id]["responseRows"]
            if actual != expected:
                raise AssertionError(f"{engine} {query_id}: expected {expected} response rows, got {actual}")
        by_engine[engine] = {
            "catchupMs": pinot_wait["catchupMs"] if engine == "pinot" else druid_wait["catchupMs"],
            "queryP50Ms": {item["id"]: item["p50Ms"] for item in evidence["queries"]},
            "queryP95Ms": {item["id"]: item["p95Ms"] for item in evidence["queries"]},
        }

    interactive_ids = ["OLAP-Q001", "OLAP-Q002", "OLAP-Q004", "OLAP-Q005"]
    score = {
        engine: sum(values["queryP95Ms"][query_id] for query_id in interactive_ids) / len(interactive_ids)
        for engine, values in by_engine.items()
    }
    measured_faster = min(score, key=score.get)

    result = {
        "schema": "baudot.olap-live-bakeoff-summary@1",
        "corpus": {
            "rows": corpus["rows"],
            "sha256": corpus["sha256"],
            "projection": corpus["projection"],
            "topic": corpus["topic"],
        },
        "engines": by_engine,
        "interactiveP95MeanMs": score,
        "measuredFasterEngine": measured_faster,
        "architecturalInitialChoice": "pinot",
        "automaticArchitectureFlipAllowed": False,
        "replayCorrectness": True,
        "authority": {
            "benchmarkWinnerIsCallTruth": False,
            "benchmarkWinnerIsCompensabilityDecision": False,
            "benchmarkWinnerIsProductionApproval": False,
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
