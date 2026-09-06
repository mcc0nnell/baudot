# ADR-0007: Apache analytics, batch orchestration, and observability roles

- Status: Proposed
- Date: 2026-09-05
- Decision owners: Baudot maintainers
- Parent: ADR-0006

## Context

ADR-0006 defines the core Apache-native TRS business stack around identity, policy, equipment distribution, call records, Fund accounting, documents, and integration.

Three additional concerns need explicit ownership so they do not leak authority back into the core business systems:

- business intelligence and operator dashboards;
- scheduled/batch reconciliation and reporting workflows; and
- technical observability across the distributed stack.

These concerns are implementation support planes. None of them may become a new source of TRS program authority.

## Decision

Use the following bounded Apache roles:

```text
Apache Superset   -> business intelligence / read-only operator analytics
Apache Airflow    -> scheduled and batch orchestration
Apache SkyWalking -> traces / metrics / logs / service observability
```

They sit around, not above, the authoritative business domains:

```text
                 Shiro / Ranger
                      |
                      v
                     Camel
              /        |        \
           OFBiz      Kafka     Fineract
              \        |        /
               \       |       /
                 reporting views
                       |
                    Superset

scheduled reconciliation / exports / backfills
                       ^
                    Airflow

technical telemetry from every service
                       |
                 SkyWalking
```

## 1. Apache Superset owns business intelligence presentation

Superset is the preferred operator-facing BI layer for read-only business analytics.

Candidate dashboards include:

- call volume and duration by provider/service/day;
- equipment shipments, backorders, returns, replacements, and quarantine inventory;
- Fund balances, debit/credit trends, and reconciliation status;
- policy allow/deny counts by resource/action; and
- synthetic proving-ground health summaries.

Superset should read from purpose-built reporting views or projections rather than being coupled directly to transactional schemas where avoidable.

```text
dashboard metric
!= policy decision
!= subscriber eligibility
!= call compensability
!= approved claim
!= ledger posting
!= accessibility verdict
```

Superset may apply dataset/dashboard access controls, but those controls do not replace Shiro/Ranger authority at the underlying business-service boundary.

## 2. Apache Airflow owns scheduled and batch orchestration

Airflow is the preferred scheduler for work whose primary semantics are time-based, batch-oriented, dependency-driven, or reconciliation-oriented rather than request-time service orchestration.

Candidate DAG families include:

```text
cdr_daily_projection
fund_daily_reconciliation
fund_monthly_close_candidate
equipment_inventory_reconciliation
provider_daily_summary
policy_audit_rollup
document_reindex
retention_export
synthetic_five_year_replay
```

Airflow owns scheduling, dependency ordering, retries, task state, backfills, and operator visibility for these batch jobs.

Camel remains the preferred integration layer for request/event-driven cross-domain workflows.

```text
Camel route completed
!= Airflow batch completed

Airflow DAG succeeded
!= source data correct
!= reconciliation correct
!= claim authorized
!= payment authorized
!= regulatory report certified
```

A DAG may invoke bounded services and validators, but task success never creates business authority by itself.

## 3. Apache SkyWalking owns technical observability

SkyWalking is the preferred observability plane for service/runtime telemetry such as:

- distributed traces;
- service and endpoint metrics;
- latency/error-rate telemetry;
- runtime and infrastructure metrics;
- logs where configured;
- topology/service-dependency views; and
- technical alarms.

Candidate instrumented components include:

```text
Baudot services
Tilden
Camel routes
Juneau/API services
Shiro-authenticated applications
Ranger PDP adapter
Kafka producers/consumers
OFBiz adapter/services
Fineract adapter/services
Airflow jobs
Superset backend
Tika/Solr ingestion/search
```

SkyWalking observes execution. It does not create evidence authority for the business facts being observed.

```text
trace span exists
!= operation authorized
!= protocol valid
!= call connected
!= CDR true
!= claim compensable
!= ledger reconciled
!= accessibility ready
```

Technical alarms are operational signals only. They do not become program-policy decisions.

## Camel vs Airflow

The split is intentional:

| Concern | Preferred role |
| --- | --- |
| Request-time routing/integration | Camel |
| Event-triggered cross-domain flow | Camel |
| Connector transformation/retry/idempotency | Camel |
| Daily/monthly scheduled jobs | Airflow |
| Backfills and historical recomputation | Airflow |
| Batch reconciliation chains | Airflow |
| Scheduled exports/reports | Airflow |

A workflow may use both. For example:

```text
Kafka CDR
  -> Camel projection update

02:00 daily
  -> Airflow reconciliation DAG
  -> compare projection totals to source/event evidence
  -> publish reconciliation result
```

Neither engine becomes semantic authority merely because it completed successfully.

## Superset source boundary

Superset should normally consume reporting projections such as:

```text
analytics_cdr_daily
analytics_equipment_daily
analytics_fund_monthly
analytics_policy_daily
```

rather than raw subscriber-level operational stores.

The reporting layer should minimize sensitive fields and use the coarsest useful grain. Subscriber names, telephone numbers, eligibility details, and raw authorization subjects should not appear in general operator dashboards unless a separately authorized use case requires them.

## SkyWalking data boundary

Telemetry must not accidentally become a second CDR, subscriber database, or policy audit store.

Instrumentation should prefer opaque correlation identifiers and bounded technical attributes over raw subscriber identifiers or telephone numbers.

```text
traceId / correlationId -> preferred
subscriber TN in span tag -> avoid by default
```

Where business-event evidence is required, preserve it in the authoritative Kafka/evidence/audit plane rather than relying on observability retention.

## Authority matrix extension

| Concern | Preferred Apache role | Explicit non-authority |
| --- | --- | --- |
| Business intelligence | Superset | Does not create policy, eligibility, compensability, claims, or ledger state |
| Scheduled/batch workflows | Airflow | Successful DAG does not prove source correctness or authorize business actions |
| Technical observability | SkyWalking | Telemetry does not establish business truth, protocol validity, or accessibility readiness |

## Build boundary

Superset, Airflow, and SkyWalking are deployment/reference components. None becomes a required dependency of the normative Baudot communications testkit.

Each integration should begin with a neutral Baudot-owned contract and deterministic fixtures. Live external-component lanes must pin exact versions/revisions and preserve evidence separately from semantic verdicts.

## Follow-up

1. Define a read-only Superset analytics profile over synthetic reporting projections.
2. Define an Airflow batch contract for CDR projection, Fund reconciliation, and five-year replay jobs.
3. Define a SkyWalking telemetry contract that forbids subscriber/business authority fields from observability tags.
4. Add pinned source/live lanes independently for each component.
5. Join Superset to Airflow-produced/reconciled read models only after the underlying source contracts are independently validated.
6. Instrument cross-service flows with opaque correlation IDs that also appear in Kafka/Fund/equipment evidence, without making SkyWalking the evidence ledger.

## Source observations

- Apache Superset 6.1.0 describes itself as an enterprise-ready business intelligence web application.
- Apache Airflow 3.3.1 is the current Apache Airflow release at the time of this decision and provides DAG-based workflow scheduling/orchestration.
- Apache SkyWalking 11.0.0 is the current Apache SkyWalking release at the time of this decision and provides application performance monitoring and observability capabilities.

These role assignments identify implementation candidates only. They do not establish production readiness, security accreditation, regulatory-reporting correctness, or TRS program authority.
