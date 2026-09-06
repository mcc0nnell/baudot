# Druid vs Pinot for TRS analytical serving

This profile evaluates Apache Druid and Apache Pinot as the analytical store behind the Superset plane defined by the Apache-native TRS business architecture.

## Decision for the first live CDR path

Use **Apache Pinot** as the initial real-time CDR analytical store.

Keep **Apache Druid** as the measured alternate, particularly if the workload becomes dominated by time-series rollup, ingestion-time aggregation, or Druid-specific operational strengths.

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

Apache Kafka 4.3.1
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

## Deterministic same-corpus evidence

The live harness generates one synthetic privacy-reduced JSONL corpus and publishes it **once** to:

```text
baudot.olap.cdr.v1
```

The corpus generator deliberately covers the full provider × service and provider × outcome Cartesian sets. The generator seals:

```text
row count
SHA-256
first event time
last event time
provider/service combination count
provider/outcome combination count
```

Pinot and Druid then consume the same retained Kafka bytes from the earliest offset. The harness does not regenerate a second candidate-specific corpus.

The catch-up gate requires the analytical row count to equal the corpus row count exactly. Extra rows are a failure rather than being accepted as "caught up".

## Engine-native ingestion configs

Pinot uses:

- `cdr_analytics_v1.schema.json`;
- `cdr_analytics_v1.realtime.table.json`;
- the Kafka 4 consumer factory `org.apache.pinot.plugin.stream.kafka40.KafkaConsumerFactory`;
- `kafka:9092` and the same `baudot.olap.cdr.v1` topic.

Druid uses:

- `cdr_analytics_v1.kafka-supervisor.json`;
- Kafka indexing service ingestion;
- `useEarliestOffset: true`;
- rollup disabled so the benchmark does not erase row-level analytical observations before query time.

These files are implementation profiles, not normative CDR schemas.

## Benchmark query set

Both candidates execute the same logical workload against the same projected corpus. Time-window queries use a deterministic anchor of **2026-08-31T00:00:00Z** so results are reproducible rather than depending on runner wall-clock time:

1. provider/service call volume over the trailing 15 minutes;
2. p50/p95 call duration by provider over the trailing 24 hours;
3. hourly call count and total duration by service type over the preceding 30 days;
4. outcome counts by provider over the trailing 24 hours;
5. single-call lookup by opaque `callId`.

`interop/olap/benchmark-queries-v1.json` carries the engine-specific SQL needed to preserve those logical query shapes across Pinot and Druid.

The live bake-off records:

```text
catch-up time from retained Kafka corpus
query p50
query p95
query response shape
resource footprint
container image identity
corpus SHA-256
```

The evidence sealer requires both engines to ingest the exact corpus row count, produce the same response cardinality for each logical query, and satisfy minimum expected shapes. It does not hard-code every aggregate result count where corpus-density changes would be irrelevant to engine parity.

The final evidence summary also records a measured faster engine for the benchmark run, but it explicitly sets:

```text
automaticArchitectureFlipAllowed = false
```

A benchmark result informs the architecture; it does not silently rewrite it.

## CI split

The benchmark has two lanes.

### Required lightweight gate

Every relevant PR validates:

- both release/config profiles;
- the Kafka 4 Pinot consumer binding;
- Druid earliest-offset replay configuration;
- exact benchmark query IDs and deterministic windows;
- privacy-reduced field parity;
- forbidden-field absence from engine schemas and SQL;
- Python compilation; and
- deterministic Cartesian corpus coverage.

### Opt-in live evidence gate

`.github/workflows/olap-live-bakeoff.yml` is manually dispatched for the heavyweight run. It:

```text
generate and hash corpus
        -> Kafka 4.3.1 publish once
        -> Pinot 1.5.1 catch-up + benchmark
        -> stop Pinot
        -> Druid 37.0.0 catch-up + benchmark
        -> compare evidence
        -> seal SHA256SUMS + artifact
```

Running the live gate is intentionally not required for every Baudot PR.

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
- Apache Pinot Docker image guidance: <https://docs.pinot.apache.org/start-here/install/docker>
- Apache Druid download page: <https://druid.apache.org/downloads/>
- Apache Druid streaming ingestion documentation: <https://druid.apache.org/docs/latest/ingestion/streaming/>
- Apache Druid Kafka ingestion documentation: <https://druid.apache.org/docs/latest/ingestion/kafka-ingestion/>
- Apache Druid 37 Docker topology: `distribution/docker/docker-compose.yml` in the `druid-37.0.0` release tree.
- Apache Superset Pinot support: <https://superset.apache.org/user-docs/databases/supported/apache-pinot/>
- Apache Superset database connection documentation: <https://superset.apache.org/docs/configuration/databases/>

## Next threshold

Dispatch the live evidence lane and inspect the sealed artifact. Until a successful live artifact exists, Pinot remains the **initial implementation choice**, not a measured performance winner.

If the first live run exposes an engine-specific query incompatibility, fix the query translation while preserving the five logical query shapes rather than weakening the benchmark.
