#!/usr/bin/env python3
"""Validate the neutral Druid vs Pinot analytical-store bakeoff contract."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "testkit" / "business" / "olap-bakeoff-v1.json"


def require(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS {name}")


def main() -> None:
    data = json.loads(CONTRACT.read_text())
    require("schema", data["schema"] == "baudot.olap-bakeoff@1")

    candidates = data["candidates"]
    require("two candidates", set(candidates) == {"apache-pinot", "apache-druid"})
    require("Pinot release pin", candidates["apache-pinot"]["version"] == "1.5.1")
    require(
        "Pinot commit pin",
        candidates["apache-pinot"]["releaseCommit"]
        == "020ff0d0538b2079d4cf4cb2676a191c87c95d4d",
    )
    require("Druid release pin", candidates["apache-druid"]["version"] == "37.0.0")
    require(
        "Druid commit pin",
        candidates["apache-druid"]["releaseCommit"]
        == "b206640c830bc2c3bdc2867cfb317c902a0e1acb",
    )

    for name, candidate in candidates.items():
        require(f"{name} direct Kafka", candidate["directKafkaIngestion"] is True)
        require(f"{name} real-time serving", candidate["realTimeServing"] is True)
        require(f"{name} Superset driver declared", bool(candidate["supersetDriver"]))

    decision = data["decision"]
    require("one initial store", decision["dualStoreByDefault"] is False)
    require("initial CDR store is a candidate", decision["initialCdrAnalyticsStore"] in candidates)
    require("secondary is a candidate", decision["secondaryCandidate"] in candidates)
    require("primary/secondary differ", decision["initialCdrAnalyticsStore"] != decision["secondaryCandidate"])

    projection = data["projection"]
    fields = set(projection["fields"])
    forbidden = set(projection["forbiddenFields"])
    require("projection excludes forbidden fields", fields.isdisjoint(forbidden))
    require("opaque call drilldown retained", "callId" in fields)
    require("provider aggregate retained", "providerId" in fields)
    require("service aggregate retained", "serviceType" in fields)
    require("time dimension retained", "eventTime" in fields)

    queries = data["benchmarkQueries"]
    ids = [query["id"] for query in queries]
    require("five benchmark queries", ids == [f"OLAP-Q{index:03d}" for index in range(1, 6)])
    require("query IDs unique", len(ids) == len(set(ids)))

    gates = data["hardGates"]
    for name, value in gates.items():
        require(f"hard gate {name}", value is True)

    authority = data["authorityBoundary"]
    for name, value in authority.items():
        require(f"non-authority {name}", value is False)

    threshold = data["nextThreshold"]
    require("live bakeoff required", threshold["liveBakeoffRequired"] is True)
    require("same corpus", threshold["sameKafkaCorpus"] is True)
    require("same projection", threshold["sameProjection"] is True)
    require("same queries", threshold["sameQueries"] is True)
    require("fixed window anchor", threshold["windowAnchor"] == "2026-08-31T00:00:00Z")
    require(
        "opt-in live workflow",
        threshold["optInWorkflow"] == ".github/workflows/olap-live-bakeoff.yml",
    )
    require(
        "benchmark measurements",
        set(threshold["measure"])
        == {
            "catchupMs",
            "queryP50Ms",
            "queryP95Ms",
            "replayCorrectness",
            "resourceFootprint",
            "operationalSteps",
        },
    )

    print("Baudot OLAP Druid/Pinot bakeoff contract: PASS")


if __name__ == "__main__":
    main()
