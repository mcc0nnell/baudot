# Airflow TRS batch plane

Apache Airflow is the reference scheduler for **scheduled, batch, backfill, and reconciliation** workflows in Baudot's synthetic TRS business stack.

Camel remains the request/event integration plane.

```text
request/event integration -> Camel
scheduled/batch work       -> Airflow
```

A successful DAG is execution evidence only:

```text
DAG success
!= source correctness
!= claim approval
!= payment authorization
!= Fund period close
!= regulatory certification
!= accessibility readiness
```

## Pinned release

This profile pins Apache Airflow **3.3.1** at release commit `3adbbe1c58e4532df1964cb7794805e763816ee8`.

## First DAG family

The neutral contract defines:

- `cdr_daily_projection`;
- `fund_daily_reconciliation`;
- `equipment_inventory_reconciliation`;
- `policy_audit_rollup`;
- `fund_monthly_close_candidate`; and
- manual `synthetic_five_year_replay`.

The monthly workflow deliberately emits a **close candidate**, not a closed accounting period. Any actual close remains a separate authorized business action.

## Contract rules

The validator enforces unique DAG/task IDs, valid dependencies, an acyclic task graph, exact Airflow release pinning, and a forbidden-output vocabulary so batch tasks cannot claim `claimApproved`, `paymentAuthorized`, `fundPeriodClosed`, `subscriberEligible`, `compensable`, or `accessibilityReady`.

## Next threshold

The next live lane should install the exact pinned Airflow release, materialize these neutral DAGs through a small adapter, run representative daily/manual DAGs against synthetic fixture services, and preserve task-instance state plus independent output reconciliation.

Airflow task state must never replace the underlying Kafka/OFBiz/Fineract/Ranger evidence.

## Claim boundary

This profile does not establish production Airflow reliability, financial-close authority, regulatory reporting correctness, payment authorization, or production scheduler security.
