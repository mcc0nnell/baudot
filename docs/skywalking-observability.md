# SkyWalking observability plane

Apache SkyWalking is the reference **technical observability** plane for the Apache-native TRS business stack.

It observes execution across services without becoming a business evidence ledger:

```text
trace / metric / log / alarm
!= authorization
!= protocol validity
!= call truth
!= compensability
!= claim approval
!= ledger reconciliation
!= accessibility readiness
```

## Pinned release

This profile pins Apache SkyWalking **11.0.0** at release commit `6f1fd78e872f1d380a14f271c26e8d68eb2430fc`.

## Instrumentation targets

The first profile covers the logical service boundaries around:

- iTRS service and Ranger PDP adapter;
- Camel integration;
- Kafka CDR producer/consumer;
- OFBiz equipment adapter;
- Fineract Fund adapter;
- Airflow batch runner;
- Superset backend; and
- Tika/Solr ingestion.

## Privacy boundary

Telemetry should correlate work with opaque IDs such as `baudot.correlation_id`, not with raw subscriber identifiers.

The contract forbids telephone numbers, subscriber IDs/names, raw request/response payloads, authorization headers, access/refresh tokens, and business-authority fields such as `claim_approved`, `payment_authorized`, `compensable`, and `accessibility_ready`.

SkyWalking must not become a shadow URD, CDR repository, or policy audit store.

## Technical alarms

The first alarm vocabulary is intentionally operational only: Ranger PDP error rate, Kafka consumer lag, OFBiz adapter errors, and Fineract reconciliation failures.

An alarm may trigger operator investigation or a separately authorized remediation workflow, but it does not create a program decision.

## SkyWalking 11 admin boundary

SkyWalking 11.0.0 introduces an admin-server surface that its release notes explicitly say has no built-in authentication and must be externally protected. The Baudot deployment contract therefore forbids public-internet exposure of that admin API and requires an external protection boundary.

## Validation

The stdlib validator enforces the exact release pin, non-authority flags, privacy field blacklist, technical-only alarm classification, trace profiles with no terminal business claim, and the protected-admin deployment boundary.

## Next threshold

A live lane should boot the exact pinned OAP release in an isolated environment, emit synthetic trace/metric traffic from at least the Ranger and Kafka fixture paths, query the resulting topology/telemetry, and prove that no forbidden subscriber/business-authority attributes were captured.

The evidence bundle should preserve the SkyWalking release identity, telemetry inputs, returned trace IDs, queried spans/metrics, and an independent privacy/authority reduction.

## Claim boundary

This profile does not establish production SkyWalking completeness, security accreditation, business evidence authority, subscriber-data handling approval, or accessibility readiness.
