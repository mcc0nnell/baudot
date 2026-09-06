#!/usr/bin/env python3
"""Statically validate the live Pinot/Druid bake-off harness and privacy boundary."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "testkit/business/olap-bakeoff-v1.json").read_text())
QUERIES = json.loads((ROOT / "interop/olap/benchmark-queries-v1.json").read_text())
PINOT_SCHEMA = json.loads((ROOT / "interop/olap/pinot/cdr_analytics_v1.schema.json").read_text())
PINOT_TABLE = json.loads((ROOT / "interop/olap/pinot/cdr_analytics_v1.realtime.table.json").read_text())
DRUID = json.loads((ROOT / "interop/olap/druid/cdr_analytics_v1.kafka-supervisor.json").read_text())


def require(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"PASS {name}: {actual!r}")


def main() -> None:
    projection = CONTRACT["projection"]
    allowed = set(projection["fields"])
    forbidden = set(projection["forbiddenFields"])
    require("projection separates allowed/forbidden", allowed.isdisjoint(forbidden), True)

    pinot_fields = {
        item["name"]
        for group in ("dimensionFieldSpecs", "metricFieldSpecs", "dateTimeFieldSpecs")
        for item in PINOT_SCHEMA.get(group, [])
    }
    require("Pinot schema field set", pinot_fields, allowed)
    require("Pinot schema contains no forbidden fields", pinot_fields.isdisjoint(forbidden), True)

    stream = PINOT_TABLE["tableIndexConfig"]["streamConfigs"]
    require("Pinot table", PINOT_TABLE["tableName"], projection["name"])
    require("Pinot Kafka topic", stream["stream.kafka.topic.name"], "baudot.olap.cdr.v1")
    require("Pinot Kafka broker", stream["stream.kafka.broker.list"], "kafka:9092")
    require(
        "Pinot Kafka 4 consumer factory",
        stream["stream.kafka.consumer.factory.class.name"],
        "org.apache.pinot.plugin.stream.kafka40.KafkaConsumerFactory",
    )
    require("Pinot earliest replay", stream["stream.kafka.consumer.prop.auto.offset.reset"], "smallest")

    spec = DRUID["spec"]
    data_schema = spec["dataSchema"]
    io = spec["ioConfig"]
    druid_fields = {data_schema["timestampSpec"]["column"]}
    druid_fields.update(data_schema["dimensionsSpec"]["dimensions"])
    for metric in data_schema["metricsSpec"]:
        druid_fields.add(metric["fieldName"])
        require(f"Druid metric {metric['name']} no rename", metric["name"], metric["fieldName"])
    require("Druid source field set", druid_fields, allowed)
    require("Druid fields contain no forbidden fields", druid_fields.isdisjoint(forbidden), True)
    require("Druid rollup disabled", data_schema["granularitySpec"]["rollup"], False)
    require("Druid Kafka topic", io["topic"], "baudot.olap.cdr.v1")
    require("Druid Kafka broker", io["consumerProperties"]["bootstrap.servers"], "kafka:9092")
    require("Druid earliest replay", io["useEarliestOffset"], True)

    expected_ids = [item["id"] for item in CONTRACT["benchmarkQueries"]]
    query_ids = [item["id"] for item in QUERIES["queries"]]
    require("benchmark query IDs", query_ids, expected_ids)
    require("benchmark table", QUERIES["table"], projection["name"])

    for item in QUERIES["queries"]:
        for engine in ("pinot", "druid"):
            sql = item[engine]
            lowered = sql.lower()
            for field in forbidden:
                if field.lower() in lowered:
                    raise AssertionError(f"{item['id']} {engine}: forbidden field {field} appears in SQL")
            if projection["name"].lower() not in lowered:
                raise AssertionError(f"{item['id']} {engine}: wrong table")
            print(f"PASS {item['id']} {engine}: privacy-reduced SQL")

    boundary = CONTRACT["authorityBoundary"]
    for key, value in boundary.items():
        require(key, value, False)

    print("Baudot live OLAP harness: PASS")


if __name__ == "__main__":
    main()
