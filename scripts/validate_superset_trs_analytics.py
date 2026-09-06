#!/usr/bin/env python3
"""Validate Baudot's read-only Apache Superset analytics profile."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "testkit" / "business" / "superset-trs-analytics-v1.json"


def require(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"PASS {name}: {actual}")


def main() -> None:
    profile = json.loads(PROFILE.read_text())
    require("schema", profile["schema"], "baudot.superset-trs-analytics@1")
    require("Superset version", profile["superset"]["version"], "6.1.0")
    require("Superset release commit", profile["superset"]["releaseCommit"], "c83fb2bb1dcfac41ac51bcebd82471f4a7180d18")
    require("Superset role", profile["superset"]["role"], "business-intelligence-read-model")

    for key, value in profile["authority"].items():
        require(key, value, False)

    privacy = profile["privacyBoundary"]
    require("no subscriber TNs", privacy["subscriberLevelTelephoneNumbersExposed"], False)
    require("no subscriber names", privacy["subscriberNamesExposed"], False)
    require("synthetic only", privacy["syntheticOnly"], True)
    require("minimum aggregate grain", privacy["minimumAggregation"], "day-provider-service")

    datasets = {row["id"]: row for row in profile["datasets"]}
    require("dataset ids unique", len(datasets), len(profile["datasets"]))

    mutation = re.compile(r"\b(insert|update|delete|merge|drop|alter|truncate|create)\b", re.I)
    for dataset_id, dataset in datasets.items():
        sql = dataset["sql"].strip()
        if not sql.lower().startswith("select "):
            raise AssertionError(f"{dataset_id}: analytics SQL must be SELECT-only")
        if mutation.search(sql):
            raise AssertionError(f"{dataset_id}: mutating SQL is forbidden")
        lowered = sql.lower()
        for field in dataset["forbiddenFields"]:
            if re.search(rf"\b{re.escape(field.lower())}\b", lowered):
                raise AssertionError(f"{dataset_id}: forbidden field appears in SQL: {field}")
        if not dataset["dimensions"] or not dataset["metrics"]:
            raise AssertionError(f"{dataset_id}: dimensions and metrics are required")
        print(f"PASS dataset {dataset_id}: {dataset['grain']}")

    dashboard_ids = set()
    for dashboard in profile["dashboards"]:
        did = dashboard["id"]
        if did in dashboard_ids:
            raise AssertionError(f"duplicate dashboard id: {did}")
        dashboard_ids.add(did)
        missing = set(dashboard["datasets"]) - set(datasets)
        if missing:
            raise AssertionError(f"{did}: unknown datasets {sorted(missing)}")
        if not dashboard["charts"]:
            raise AssertionError(f"{did}: at least one chart is required")
        print(f"PASS dashboard {did}: {len(dashboard['charts'])} charts")

    source = profile["sourceProjectionBoundary"]
    require("no direct Kafka read", source["supersetReadsKafkaDirectly"], False)
    require("no direct OFBiz transaction read", source["supersetReadsOfbizTransactionalTablesDirectly"], False)
    require("no direct Fineract transaction read", source["supersetReadsFineractTransactionalTablesDirectly"], False)
    require("no direct Ranger operational read", source["supersetReadsRangerOperationalTablesDirectly"], False)
    require("read-only reporting views required", source["requiresReadOnlyReportingViews"], True)

    for key, value in profile["claimBoundary"].items():
        require(key, value, False)

    print("Superset TRS analytics profile: PASS")


if __name__ == "__main__":
    main()
