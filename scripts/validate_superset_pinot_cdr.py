#!/usr/bin/env python3
"""Validate the read-only Superset -> Pinot live CDR analytics profile."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / "testkit/business/superset-pinot-cdr-v1.json").read_text())
OLAP = json.loads((ROOT / "testkit/business/olap-bakeoff-v1.json").read_text())
PINOT_SCHEMA = json.loads((ROOT / "interop/olap/pinot/cdr_analytics_v1.schema.json").read_text())
CONNECTION = json.loads((ROOT / "interop/superset/pinot/database-connection-v1.json").read_text())
DOCKERFILE = (ROOT / "interop/superset/pinot/Dockerfile").read_text()
LIVE_WORKFLOW = ROOT / ".github/workflows/superset-pinot-live-admission.yml"

FIELD_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
FUNCTION_WORDS = {"COUNT", "SUM", "p50", "p95"}


def require(name: str, actual, expected=True) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"PASS {name}: {actual!r}")


def metric_fields(expression: str) -> set[str]:
    tokens = set(FIELD_TOKEN.findall(expression))
    return {token for token in tokens if token not in FUNCTION_WORDS}


def main() -> None:
    require("profile schema", PROFILE["schema"], "baudot.superset-pinot-cdr@1")
    require("Superset pin", PROFILE["stack"]["supersetVersion"], "6.1.0")
    require("Pinot pin", PROFILE["stack"]["pinotVersion"], "1.5.1")
    require("Pinot driver", PROFILE["stack"]["pinotDriver"], "pinotdb")
    require("dataset name", PROFILE["stack"]["pinotDataset"], "cdr_analytics_v1")

    require("Superset image pin", "FROM apache/superset:6.1.0" in DOCKERFILE, True)
    require("pinotdb driver pin", 'pinotdb==9.1.2' in DOCKERFILE, True)
    require("live admission workflow present", LIVE_WORKFLOW.exists(), True)

    uri = PROFILE["stack"]["sqlalchemyUri"]
    require("profile URI matches connection", uri, CONNECTION["sqlalchemy_uri"])
    require("Pinot SQLAlchemy scheme", uri.startswith("pinot://"), True)
    require("Pinot broker endpoint", "pinot-broker:8099/query" in uri, True)
    require("Pinot controller endpoint", "pinot-controller:9000" in uri, True)
    require("connection has no embedded credentials", "@" not in uri, True)

    require("database name parity", CONNECTION["database_name"], PROFILE["databaseConnection"]["databaseName"])
    for api_key, profile_key in (
        ("allow_dml", "allowDml"),
        ("allow_ctas", "allowCtas"),
        ("allow_cvas", "allowCvas"),
        ("allow_file_upload", "allowFileUpload"),
    ):
        require(f"read-only {api_key}", CONNECTION[api_key], False)
        require(f"profile read-only {profile_key}", PROFILE["databaseConnection"][profile_key], False)
    require("SQL Lab exposure", CONNECTION["expose_in_sqllab"], True)

    olap_projection = OLAP["projection"]
    allowed = set(olap_projection["fields"])
    forbidden = set(olap_projection["forbiddenFields"])
    profile_columns = set(PROFILE["dataset"]["columns"])
    profile_forbidden = set(PROFILE["dataset"]["forbiddenColumns"])

    pinot_columns = {
        item["name"]
        for group in ("dimensionFieldSpecs", "metricFieldSpecs", "dateTimeFieldSpecs")
        for item in PINOT_SCHEMA.get(group, [])
    }

    require("Superset dataset equals OLAP projection", profile_columns, allowed)
    require("Superset dataset equals Pinot schema", profile_columns, pinot_columns)
    require("forbidden field parity", profile_forbidden, forbidden)
    require("dataset excludes forbidden fields", profile_columns.isdisjoint(forbidden), True)
    require("default time column", PROFILE["dataset"]["defaultTimeColumn"], "eventTime")
    require("bounded cache", PROFILE["dataset"]["defaultCacheTimeoutSeconds"] <= 60, True)

    chart_ids = {chart["id"] for chart in PROFILE["charts"]}
    require("chart IDs unique", len(chart_ids), len(PROFILE["charts"]))

    for chart in PROFILE["charts"]:
        dimensions = set(chart["dimensions"])
        unknown_dimensions = dimensions - allowed
        if unknown_dimensions:
            raise AssertionError(f"{chart['id']}: unknown dimensions {sorted(unknown_dimensions)}")

        fields_from_metrics: set[str] = set()
        for metric in chart["metrics"]:
            fields_from_metrics.update(metric_fields(metric))
        unknown_metric_fields = fields_from_metrics - allowed
        if unknown_metric_fields:
            raise AssertionError(f"{chart['id']}: unknown metric fields {sorted(unknown_metric_fields)}")

        touched = dimensions | fields_from_metrics
        if touched & forbidden:
            raise AssertionError(f"{chart['id']}: forbidden fields referenced")

        if chart["defaultDashboard"]:
            require(f"{chart['id']} hides opaque call ID", "callId" not in touched, True)
            require(f"{chart['id']} hides event ID", "eventId" not in touched, True)
        print(f"PASS {chart['id']}: projection-safe chart")

    dashboard = PROFILE["dashboard"]
    require("dashboard dataset", dashboard["dataset"], "cdr_analytics_v1")
    require("dashboard chart refs valid", set(dashboard["chartIds"]).issubset(chart_ids), True)
    require("technical drilldown ref valid", dashboard["technicalDrilldownChartId"] in chart_ids, True)
    drilldown = next(chart for chart in PROFILE["charts"] if chart["id"] == dashboard["technicalDrilldownChartId"])
    require("technical drilldown is not default", drilldown["defaultDashboard"], False)
    require("technical drilldown purpose", drilldown["purpose"], "technical-correlation-only")

    reporting = PROFILE["reportingBoundary"]
    require("live dataset does not replace cdr_daily", reporting["liveDatasetReplacesCdrDaily"], False)
    require("cdr_daily remains stable aggregate", reporting["cdrDailyRemainsStableAggregate"], True)
    require("not regulatory source", reporting["liveDatasetIsRegulatoryReportingSource"], False)
    require("not financial source", reporting["liveDatasetIsFinancialReportingSource"], False)
    require("Superset never reads Kafka directly", reporting["supersetReadsKafkaDirectly"], False)
    require("Superset Pinot read-only", reporting["supersetQueriesPinotReadOnly"], True)

    for key, value in PROFILE["authorityBoundary"].items():
        require(f"non-authority {key}", value, False)
    for key, value in PROFILE["claimBoundary"].items():
        require(f"claim boundary {key}", value, False)

    print("Baudot Superset -> Pinot CDR profile: PASS")


if __name__ == "__main__":
    main()
