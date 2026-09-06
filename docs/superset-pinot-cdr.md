# Superset over Pinot for live TRS call analytics

This profile wires the privacy-reduced `cdr_analytics_v1` dataset selected by the Druid-vs-Pinot bake-off into Apache Superset as a **read-only operational analytics surface**.

It is deliberately separate from the stable daily reporting projection defined by the broader Superset profile.

## Role split

```text
Kafka CDR events
    -> privacy reduction
    -> Pinot cdr_analytics_v1
    -> Superset live operational views

stable reporting projections
    -> cdr_daily
    -> Superset stable reporting views
```

The live Pinot dataset does **not** replace `cdr_daily`.

## Current pins

```text
Apache Superset 6.1.0
Apache Pinot    1.5.1
```

Superset's documented Pinot connector uses the `pinotdb` package and a `pinot://...` SQLAlchemy URI. The Baudot synthetic/container profile uses:

```text
pinot://pinot-broker:8099/query?server=http://pinot-controller:9000/
```

This URI contains no credentials and describes only the synthetic local/container topology.

## Read-only database profile

`interop/superset/pinot/database-connection-v1.json` sets:

```text
allow_dml         = false
allow_ctas        = false
allow_cvas        = false
allow_file_upload = false
```

SQL Lab exposure remains enabled for read-only analytical exploration.

The profile is shaped from Superset 6.1's database-connection schema and datasource import model. It is an integration profile, not a claim that the file has been imported into a live Superset instance yet.

## Exact privacy projection

Superset is allowed to see exactly the Pinot analytical columns:

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

It must not gain:

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

CI compares the Superset dataset contract directly with both the OLAP contract and the Pinot schema so drift cannot be hidden in a dashboard configuration.

## Live operational dashboard

The default `TRS Live Call Operations` surface contains:

1. live calls by provider and service over 15 minutes;
2. duration distribution by provider over 24 hours;
3. outcomes by provider over 24 hours;
4. hourly service trend over 30 days.

An opaque-call technical drilldown exists separately and is **not** placed on the default dashboard.

That split keeps `callId` and `eventId` out of general operational views while retaining bounded technical correlation when needed.

## Reporting boundary

```text
Pinot live metric
!= stable daily reporting record

live dashboard
!= regulatory report

live dashboard
!= financial report
```

The older `cdr_daily` projection remains the stable day/provider/service aggregate for reporting-oriented dashboards.

## Authority boundary

```text
Superset chart
!= call truth
!= subscriber eligibility
!= compensability
!= claim approval
!= payment authorization
!= accessibility verdict
```

Superset is a reader. Pinot is an analytical store. Neither becomes TRS program authority.

## CI

The dedicated validator proves:

- Superset 6.1.0 and Pinot 1.5.1 pins;
- documented Pinot SQLAlchemy URI shape;
- no embedded credentials;
- DML/CTAS/CVAS/file upload disabled;
- Superset column set exactly equals the Pinot/OLAP privacy projection;
- forbidden-field parity;
- chart dimensions/metrics remain inside the allowed projection;
- opaque identifiers stay off default dashboards;
- live Pinot does not replace `cdr_daily`; and
- every business-authority/production claim flag remains false.

## Next threshold

After the live Pinot lane exists as evidence, boot Superset 6.1.0 with `pinotdb`, create/test this connection, register `cdr_analytics_v1`, execute the four default operational chart queries, and independently reconcile the row/aggregate results against Pinot.

Until that happens, this PR establishes the **read-only connection and dataset contract**, not live Superset import/connectivity compatibility.

## Sources

- Superset 6.1 database connection documentation: <https://superset.apache.org/user-docs/6.1.0/databases/>
- Superset 6.1 database connection schema: <https://superset.apache.org/developer-docs/6.1.0/api/schemas/databaseconnectionschema/>
- Superset 6.1 datasource import/export: <https://superset.apache.org/admin-docs/6.1.0/configuration/importing-exporting-datasources/>
