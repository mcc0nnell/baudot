#!/usr/bin/env python3
"""Run the same logical CDR analytics benchmark against Pinot or Druid."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUERY_FILE = ROOT / "interop" / "olap" / "benchmark-queries-v1.json"


def post_json(url: str, payload: dict, timeout: int = 60):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def query(engine: str, endpoint: str, sql: str):
    if engine == "pinot":
        payload = post_json(
            endpoint.rstrip("/") + "/query/sql",
            {"sql": sql, "queryOptions": "useMultistageEngine=true"},
        )
        if payload.get("exceptions"):
            raise RuntimeError(f"Pinot query failed: {payload['exceptions']}")
        table = payload.get("resultTable")
        if not table:
            raise RuntimeError(f"Pinot response missing resultTable: {payload}")
        data_schema = table.get("dataSchema", {})
        columns = data_schema.get("columnNames", [])
        rows = table.get("rows", [])
        if columns and rows and not isinstance(rows[0], dict):
            return [dict(zip(columns, row)) for row in rows]
        return rows

    if engine == "druid":
        payload = post_json(
            endpoint.rstrip("/") + "/druid/v2/sql",
            {"query": sql, "resultFormat": "object", "header": False},
        )
        if not isinstance(payload, list):
            raise RuntimeError(f"Druid SQL response is not a row list: {payload}")
        return payload

    raise ValueError(engine)


def extract_count(rows) -> int:
    if not rows:
        return 0
    row = rows[0]
    if isinstance(row, dict):
        for key in ("c", "EXPR$0", "count"):
            if key in row:
                return int(row[key])
        if len(row) == 1:
            return int(next(iter(row.values())))
    if isinstance(row, list) and row:
        return int(row[0])
    raise RuntimeError(f"unable to extract count from {rows!r}")


def percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def canonical_digest(rows) -> str:
    raw = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def wait_for_rows(engine: str, endpoint: str, expected: int, timeout_seconds: int) -> dict:
    started = time.monotonic()
    deadline = started + timeout_seconds
    attempts = 0
    last_count = -1
    while time.monotonic() < deadline:
        attempts += 1
        try:
            last_count = extract_count(query(engine, endpoint, "SELECT COUNT(*) AS c FROM cdr_analytics_v1"))
            if last_count == expected:
                elapsed = round((time.monotonic() - started) * 1000, 3)
                return {"rows": last_count, "catchupMs": elapsed, "attempts": attempts}
            if last_count > expected:
                raise RuntimeError(f"{engine}: duplicate/extra rows observed: {last_count} > {expected}")
        except (urllib.error.URLError, ValueError):
            pass
        time.sleep(2)
    raise SystemExit(f"{engine}: timed out waiting for exactly {expected} rows; last_count={last_count}")


def bench(engine: str, endpoint: str, output: Path, warmups: int, iterations: int) -> None:
    contract = json.loads(QUERY_FILE.read_text())
    evidence = {
        "schema": "baudot.olap-live-benchmark-result@1",
        "engine": engine,
        "endpoint": endpoint,
        "windowAnchor": contract["windowAnchor"],
        "warmups": warmups,
        "iterations": iterations,
        "queries": [],
        "authority": {
            "callTruth": False,
            "compensabilityDecision": False,
            "claimApproval": False,
            "paymentAuthorization": False,
            "accessibilityVerdict": False,
        },
    }

    for item in contract["queries"]:
        sql = item[engine]
        for _ in range(warmups):
            query(engine, endpoint, sql)

        samples: list[float] = []
        last_rows = None
        for _ in range(iterations):
            before = time.perf_counter_ns()
            rows = query(engine, endpoint, sql)
            after = time.perf_counter_ns()
            samples.append((after - before) / 1_000_000)
            last_rows = rows

        evidence["queries"].append(
            {
                "id": item["id"],
                "samplesMs": [round(value, 3) for value in samples],
                "p50Ms": round(statistics.median(samples), 3),
                "p95Ms": round(percentile(samples, 0.95), 3),
                "responseRows": len(last_rows or []),
                "responseSha256": canonical_digest(last_rows or []),
            }
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps(evidence, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    wait_parser = subparsers.add_parser("wait")
    wait_parser.add_argument("--engine", choices=["pinot", "druid"], required=True)
    wait_parser.add_argument("--endpoint", required=True)
    wait_parser.add_argument("--expected", type=int, required=True)
    wait_parser.add_argument("--timeout", type=int, default=300)
    wait_parser.add_argument("--out", required=True)

    bench_parser = subparsers.add_parser("bench")
    bench_parser.add_argument("--engine", choices=["pinot", "druid"], required=True)
    bench_parser.add_argument("--endpoint", required=True)
    bench_parser.add_argument("--out", required=True)
    bench_parser.add_argument("--warmups", type=int, default=2)
    bench_parser.add_argument("--iterations", type=int, default=7)

    args = parser.parse_args()
    if args.command == "wait":
        result = wait_for_rows(args.engine, args.endpoint, args.expected, args.timeout)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps(result, sort_keys=True))
    else:
        bench(args.engine, args.endpoint, Path(args.out), args.warmups, args.iterations)


if __name__ == "__main__":
    main()
