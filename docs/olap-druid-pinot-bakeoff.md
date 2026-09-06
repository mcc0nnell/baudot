# Druid vs Pinot for TRS analytical serving

This profile evaluates Apache Druid and Apache Pinot as the analytical store behind the Superset plane defined by the Apache-native TRS business architecture.

## Decision for the first live CDR path

Use **Apache Pinot** as the initial real-time CDR analytical store.

Keep **Apache Druid** as the alternate candidate for a later live benchmark, particularly if the workload becomes dominated by time-series rollup, ingestion-time aggregation, or Druid-specific operational strengths.

Do **not** operate both by default.

The decision is intentionally narrow:

```text
Kafka CDR event
    -> privacy-reduced analytics projection
    -> Pinot real-time table
    -> Superset dataset
    -> dashboard/query
```

It does not make Pinot a CDR system of record or business authority.

## Current release pins

```text
Apache Pinot 1.5.1
commit 020ff0d0538b2079d4cf4cb2676a191c87c95d4d

Apache Druid 37.0.0
commit b206640c830bc2c3bdc2867cfb317c902a0e1acb
```

Pinot 1.5.1 is the current stable Pinot release as of this profile and is a security-patch release over 1.5.0. Pinot 1.5.0 added explicit Kafka 4.x support alongside continued work on its multi-stage query engine, upsert, federation, and real-time ingestion.

Druid 37.0.0 is the current stable Druid release as of this profile. Druid provides direct Kafka ingestion through its Kafka indexing service and supports real-time querying while streaming ingestion tasks are active.

Both are supported database engines in Apache Superset through SQLAlchemy/DBAPI drivers.

## Why Pinot first

The first Baudot analytical workload is a Kafka-first, low-latency, append-oriented CDR workload with simple dimensions and measures:

- provider;
- service type;
- direction;
- outcome;
- event time;
- duration;
- opaque call correlation.

Pinot is a particularly direct fit for that shape:

- real-time tables consume Kafka directly;
- Pinot 1.5.x explicitly supports Kafka 4.x connectors;
- records become queryable during real-time ingestion;
- the multi-stage query engine supports broader SQL workloads when needed;
- Superset has a maintained Pinot database engine integration.

This is a fit decision, not a claim that Pinot is universally superior to Druid.

## Why Druid remains in the bake-off

Druid also directly consumes Kafka and is designed for real-time analytics. It remains attractive when the workload emphasizes:

- time-series analytics;
- ingestion-time transformations;
- rollup-heavy aggregates;
- Druid SQL and its ingestion/query model;
- broader use of Druid segments/deep-storage lifecycle.

A live benchmark may reverse the initial decision if the measured workload says so.

## Privacy-reduced projection

The analytical store must never receive the raw Kafka CDR envelope unchanged.

The first analytical projection is `cdr_analytics_v1`:

```text
eventTime
eventId
callId
providerId
serviceType
direction
durationSeconds
outcome
sourceObservationCount
```

Explicitly excluded:

```text
fromTn
toTn
subscriberId
subscriberName
rawPayload
claimApproved
paymentAuthorized
compensable
providerCertified
accessibilityReady
```

`callId` is retained only as an opaque correlation key for technical drilldown.

## Benchmark query set

Both candidates must execute the same logical workload against the same projected corpus:

1. provider/service call volume over the trailing 15 minutes;
2. p50/p95 call duration by provider over 24 hours;
3. hourly call count and total duration by service type over 30 days;
4. outcome counts by provider over 24 hours;
5. single-call lookup by opaque `callId`.

The live bake-off records:

```text
ingestion lag
query p50
query p95
replay correctness
resource footprint
operator steps
```

No candidate wins merely by having more features.

## Superset boundary

Superset should connect to the selected OLAP store as a read-only consumer.

```text
Kafka
  -> analytical projection
  -> Pinot (initial)
  -> Superset
```

Superset dashboards do not write back to Pinot, Kafka, OFBiz, Fineract, Ranger, or any TRS authority system.

## Authority boundary

```text
OLAP row present
!= call independently verified

OLAP aggregate
!= compensable minutes

Superset chart
!= claim approval

query result
!= payment authorization

successful ingestion
!= accessibility verdict
```

The OLAP layer answers analytical questions only.

## Evidence basis

- Apache Pinot download/release page: <https://pinot.apache.org/download/>
- Apache Pinot Kafka ingestion documentation: <https://docs.pinot.apache.org/data-ingestion/pinot-stream-ingestion/import-from-apache-kafka>
- Apache Druid download page: <https://druid.apache.org/downloads/>
- Apache Druid streaming ingestion documentation: <https://druid.apache.org/docs/latest/ingestion/streaming/>
- Apache Druid Kafka ingestion documentation: <https://druid.apache.org/docs/latest/ingestion/kafka-ingestion/>
- Apache Superset Pinot support: <https://superset.apache.org/user-docs/databases/supported/apache-pinot/>
- Apache Superset database connection documentation: <https://superset.apache.org/docs/configuration/databases/>

## Next threshold

The next PR should stand up the exact pinned Pinot and Druid releases against the same pinned Kafka CDR fixture and produce a machine-readable benchmark result. Until that lane runs, this profile records an **initial implementation choice**, not a performance proof.
