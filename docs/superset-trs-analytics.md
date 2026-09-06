# Superset TRS analytics plane

Apache Superset is the reference **business intelligence / operator analytics** layer for the synthetic TRS business stack.

It is intentionally read-only with respect to business authority:

```text
Kafka / OFBiz / Fineract / Ranger
        -> reporting projections
        -> Superset datasets
        -> charts / dashboards
```

The key invariant is:

```text
dashboard metric
!= policy decision
!= subscriber eligibility
!= call compensability
!= approved claim
!= ledger posting
!= accessibility verdict
```

## Pinned release

This profile pins Apache Superset **6.1.0** at release commit `c83fb2bb1dcfac41ac51bcebd82471f4a7180d18`.

## Reporting projections

The first profile defines four synthetic read models:

- `cdr_daily` — day/provider/service call counts and duration;
- `equipment_daily` — shipments, backorders, returns, replacements, and quarantine stock;
- `fund_monthly` — aggregate debit/credit/ending-balance reporting;
- `policy_daily` — aggregate Ranger allow/deny counts by resource/action.

Superset does **not** read Kafka directly or bind itself to OFBiz/Fineract/Ranger transactional schemas. A Camel/NiFi/batch projection may create read-only reporting views first.

## Privacy boundary

General dashboards exclude subscriber names, telephone numbers, subscriber IDs, raw policy subjects, eligibility detail, and claim/payment authority fields.

The default analytic grain is aggregated rather than subscriber-level.

## Dashboards

The first dashboard family includes:

```text
TRS Operations Overview
Provider and Call Operations
Equipment Distribution
TRS Fund
Authorization Audit
```

These dashboards are operational views only. A chart becoming green cannot authorize an underlying action.

## Validation

`scripts/validate_superset_trs_analytics.py` mechanically enforces:

- exact Superset release pin;
- SELECT-only dataset SQL;
- forbidden business-authority fields are absent;
- dashboard-to-dataset references resolve;
- all analytics authority flags remain false; and
- reporting projections remain read-only boundaries.

## Next threshold

The next useful live lane is an ephemeral Superset instance backed by a synthetic reporting database populated from the Kafka/OFBiz/Fineract/Ranger fixtures. The lane should import datasets/dashboards, render/query the aggregate metrics, and independently verify the resulting values against the source projections.

That lane must not introduce production subscriber data or turn Superset access control into the underlying business authorization model.

## Claim boundary

This profile does not establish production Superset security, regulatory-report accuracy, financial-statement accuracy, compensability correctness, eligibility correctness, or production dashboard suitability.
