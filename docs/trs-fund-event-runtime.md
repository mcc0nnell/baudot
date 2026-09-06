# Deterministic TRS Fund event runtime

The synthetic TRS Fund proving ground uses an **append-only scenario-event model** in front of Apache Fineract.

This runtime is an executable implementation layer beneath the canonical public Fund and lifecycle contracts. It does not become another Fund policy source.

```text
public Fund calibration / contributor rules
        |
        v
canonical journal contract
        |
        v
canonical runtime lifecycle contract
        |
        v
scenario command
        |
        v
append-only synthetic event log
        |
        +--> deterministic Fund-state fold
        |
        `--> canonical journal intent
                    |
                    v
             future Fineract adapter
```

The event log is authoritative only for **what the synthetic scenario accepted and in what order**. It does not decide compensation rates, provider eligibility, contributor liability, production payment authorization, or the chart of accounts.

## Why this layer exists

Fineract is the external financial kernel under test, not the Fund authority.

These facts remain distinct:

```text
synthetic scenario event accepted
!= public-program decision established
!= journal intent emitted
!= Fineract posting accepted
!= ledger state reconciled
```

The runtime therefore keeps the synthetic business event log independent from the eventual ledger projection.

## Runtime shape

```text
scenario command
      |
      v
idempotency gate
      |
      +-- duplicate key --> ACK existing seq; no new event
      |
      v
business invariant validation
      |
      +-- invalid --> reject; no event; no journal intent
      |
      v
append immutable synthetic Fund event
      |
      +-----------------------+
      |                       |
      v                       v
deterministic fold        journal intent
      |                       |
      v                       v
expected Fund state       Fineract adapter
      |                       |
      |                       v
      |                  Fineract GL
      |                       |
      +-----------+-----------+
                  v
        independent reconciliation
```

The executable runner is [`scripts/run_trs_fund_scenario.py`](../scripts/run_trs_fund_scenario.py).

## Authority binding

Before it accepts commands, the runner loads:

- `interop/fineract/journal-contract-v1.json`; and
- `testkit/fund/trs-fund-runtime-contract-v1.json`.

It requires the lifecycle contract to depend on the same canonical journal schema, to define neither `accounts` nor `rateProfiles`, and to retain the canonical provider approval/disbursement mappings used by `FUND-001` and `FUND-002`.

The evidence envelope records SHA-256 for both contracts. A scenario run therefore cannot silently use a different accounting or lifecycle vocabulary and still look equivalent.

## First command vocabulary

The first slice supports four commands:

```text
CONTRIBUTOR_ASSESSED  -> contributorAssessment
CONTRIBUTOR_RECEIPT   -> contributorReceipt
PROVIDER_CLAIM_APPROVED -> providerClaimApproved
PROVIDER_DISBURSED    -> providerDisbursement
```

Those journal-event names come from the canonical journal contract. The provider approval/disbursement pair is additionally bound to the lifecycle contract.

Each command carries a stable `idempotencyKey`. The first accepted occurrence receives the next event sequence number. A retry with the same key is acknowledged against the original sequence and **must not append another event or change state**.

## Pure reducer

Accepted events fold into a deliberately small synthetic state:

```text
cash
contributorReceivable
providerPayable
contributionRevenue
providerCompensationExpense
lastSeq
```

The reducer performs no HTTP calls, database writes, wall-clock reads, or Fineract operations. Given the same ordered event log, it must produce the same state.

Every run proves this twice:

1. state is updated as commands are accepted; and
2. state is rebuilt from empty state using only the immutable accepted event log.

The two results must match exactly.

## Journal intent projection

Every accepted event is projected through the canonical Fineract journal contract.

Example:

```text
CONTRIBUTOR_ASSESSED
  -> contributorAssessment
  -> Dr Contributor Receivable
  -> Cr Contribution Revenue
```

A journal intent preserves the synthetic business transaction/idempotency key, event sequence, canonical event type, posting date, amount, expected debit/credit accounts, and business-authority label. Fineract transaction fields remain empty until a live adapter produces them.

A journal intent is **not** evidence that Fineract accepted the entry.

## Evidence envelope

A scenario emits `baudot.trs-fund-scenario-evidence@1` containing:

- scenario SHA-256;
- canonical journal-contract SHA-256;
- canonical runtime-lifecycle-contract SHA-256;
- explicit authority bindings;
- immutable accepted event log;
- command ACK/replay results;
- expected Fineract journal intents;
- final folded Fund state;
- cold-start replay result; and
- claim boundaries.

## First scenario

[`testkit/fund/scenarios/year-1-smoke.json`](../testkit/fund/scenarios/year-1-smoke.json) includes:

```text
assessment       +2400 receivable
receipt          +2400 cash / -2400 receivable
receipt retry    same idempotency key -> no-op ACK
claim approved   +1650 expense / +1650 payable
disbursement     -1650 cash / -1650 payable
```

Expected terminal state:

```text
cash                         750.00
contributor receivable         0.00
provider payable               0.00
contribution revenue        2400.00
provider compensation       1650.00
accepted events                 4
idempotent retries              1
```

The amounts and actors are synthetic fixtures. The runtime does not derive them from production data or independently select compensation rates.

## Fineract adapter seam

The live Fineract lane should consume emitted **journal intents**, not raw scenario commands.

For each intent, a future adapter should resolve canonical synthetic account codes to seeded Fineract GL IDs, submit the manual journal entry, preserve returned transaction/journal IDs, read financial state back, and independently reconcile that state against the folded Baudot state.

A Fineract HTTP success response remains an intermediate observation, not the terminal verdict.

## Future event vocabulary

Corrections remain events, not mutation of history. Useful future commands include explicit contributor adjustments/credits, provider claim adjustments/recoveries, accounting-period closure, journal reversal, and program-year advancement. Each needs a canonical accounting mapping and dedicated evidence before admission.

## Claim boundary

This runtime proves deterministic **synthetic** event handling, idempotent replay, cold-start reconstruction, canonical journal-intent generation, and expected-state reconciliation for implemented scenarios.

It does not establish provider eligibility, contributor liability, FCC approval, Rolka Loube production compatibility, live Fineract posting, Fineract production suitability, payment-network operation, financial-statement compliance, audit correctness, routing authority, or accessibility readiness.
