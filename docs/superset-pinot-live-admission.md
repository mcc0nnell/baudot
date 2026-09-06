# Superset -> Pinot live admission evidence

The Superset/Pinot integration is intentionally admitted in stages. A lower stage never implies the claims of a higher stage.

## Stage 0 — contract

Required PR CI proves:

- Superset 6.1.0 is the selected BI version;
- Pinot 1.5.1 is the selected live CDR analytical store;
- the custom Superset image pins `pinotdb==9.1.2`;
- the SQLAlchemy URI is the documented Pinot form;
- DML, CTAS, CVAS, and file upload are disabled;
- Superset's column set exactly equals the Pinot/OLAP privacy projection;
- forbidden TRS/subscriber/authority fields are absent; and
- opaque call/event identifiers stay off the default dashboard.

This stage does not require containers.

## Stage 1 — live connection admission

The manual `.github/workflows/superset-pinot-live-admission.yml` lane boots:

```text
Kafka 4.3.1
    -> privacy-reduced synthetic CDR corpus
    -> Pinot 1.5.1
    -> Superset 6.1.0 + pinotdb 9.1.2
```

It then uses Superset's own REST API:

```text
GET  /health
POST /api/v1/security/login
GET  /api/v1/security/csrf_token/
POST /api/v1/database/test_connection/
POST /api/v1/database/
GET  /api/v1/database/{id}/select_star/cdr_analytics_v1/
```

The admission artifact stores status, component pins, corpus identity, and response hashes. It does not preserve the returned analytical rows.

A successful Stage 1 proves only:

```text
Superset can load the pinned Pinot driver
AND Superset can connect to the synthetic Pinot endpoint
AND Superset can query cdr_analytics_v1 through its own database API
```

It does not prove chart correctness.

## Stage 2 — dataset registration

A later lane may create/register `cdr_analytics_v1` through Superset's dataset API and refresh its columns.

Required evidence should compare Superset's discovered columns against the exact nine-column privacy projection.

Stage 2 must not introduce computed fields derived from excluded subscriber or business-authority data.

## Stage 3 — chart query evidence

The four default live operational chart shapes are then executed through Superset's chart/query API:

- provider/service volume — 15 minutes;
- p50/p95 duration — 24 hours;
- outcomes by provider — 24 hours;
- hourly service trend — 30 days.

Each result must reconcile against a direct Pinot query over the same fixed window anchor.

The opaque-call technical drilldown remains outside the default dashboard.

## Stage 4 — rendered dashboard

Only after Stage 3 may a rendered `TRS Live Call Operations` dashboard be treated as validated presentation evidence.

Rendering still does not create TRS program authority.

## Permanent authority boundary

At every stage:

```text
Superset connection success
!= call truth

Superset dataset discovery
!= compensability

Superset chart equality
!= claim approval

Superset dashboard render
!= payment authorization
!= subscriber eligibility
!= accessibility verdict
```

## Privacy handling

The live admission lane uses only synthetic privacy-reduced CDR rows. The response body from `select_star` is checked for forbidden field names and then represented in the artifact by SHA-256 rather than copied into evidence JSON.

## Current claim state

The repository currently provides Stage 0 and an executable opt-in Stage 1 harness.

Until a successful Stage 1 workflow artifact exists, live Superset/Pinot connectivity remains **unproven**.

## Source basis

- Superset health endpoint: <https://superset.apache.org/admin-docs/6.1.0/configuration/configuring-superset/>
- Superset REST authentication: <https://superset.apache.org/developer-docs/6.1.0/api/>
- Superset database API: <https://superset.apache.org/developer-docs/6.1.0/api/database/>
- Superset dataset API: <https://superset.apache.org/developer-docs/6.1.0/api/datasets/>
- Superset Docker driver guidance: <https://superset.apache.org/admin-docs/6.1.0/installation/docker-builds/>
