# Deterministic TRS Fund event runtime

The synthetic TRS Fund proving ground uses an **append-only business-event model** in front of Apache Fineract.

The runtime pattern is adapted from the event-sourced College Bowl runtime in SF26: stable idempotency keys, immutable accepted events, deterministic state folding, cold-start replay, explicit rejection, and read-only evidence projections. Baudot does not depend on SF26 at runtime and does not import its conference-specific domain model.

## Why this layer exists

Fineract is the financial kernel, not the Fund authority.

If Baudot posted directly into a ledger and then treated the ledger as the source of truth for program semantics, several independent facts would collapse into one:

```text
program event occurred
ledger accepted posting
ledger balance changed
program invariant remains true
```

Those are deliberately separate.

The synthetic Fund event log is the authoritative record of what the scenario says happened. Fineract is a projection/execution target for the accounting consequence of accepted Fund events.

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
append immutable Fund event
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

The first executable runner is [`scripts/run_trs_fund_scenario.py`](../scripts/run_trs_fund_scenario.py).

## Command and event semantics

The first slice supports four business commands:

```text
CONTRIBUTOR_ASSESSED
CONTRIBUTOR_RECEIPT
PROVIDER_CLAIM_APPROVED
PROVIDER_DISBURSED
```

Each command carries a stable `idempotencyKey`. The first accepted occurrence receives the next event sequence number. A retry with the same key is acknowledged against the original sequence and **must not append another event or change state**.

That means a payment client can safely retry after an ambiguous response without converting network uncertainty into duplicate Fund activity.

## Pure reducer

Accepted events are folded into a small synthetic accounting state:

```text
cash
contributorReceivable
providerPayable
contributionRevenue
providerCompensationExpense
lastSeq
```

The reducer performs no HTTP calls, database writes, wall-clock reads, or Fineract operations. Given the same ordered event log, it must produce the same state.

The runner proves this twice:

1. state is updated as commands are accepted; and
2. state is rebuilt from an empty process using only the immutable accepted event log.

The two results must match exactly before the scenario can pass.

## Journal intent projection

Every accepted Fund event is projected through [`interop/fineract/journal-contract-v1.json`](../interop/fineract/journal-contract-v1.json).

Example:

```text
CONTRIBUTOR_ASSESSED
  -> contributorAssessment
  -> Dr Contributor Receivable
  -> Cr Contribution Revenue
```

The resulting journal intent preserves:

- synthetic business transaction / idempotency key;
- Fund event sequence;
- event type;
- effective/posting date;
- amount;
- expected debit and credit account;
- business-authority label; and
- empty Fineract evidence fields to be populated only by the live adapter.

A journal intent is **not** evidence that Fineract accepted the entry. It is the expected accounting consequence of an accepted synthetic Fund event.

## Evidence envelope

A scenario run emits `baudot.trs-fund-scenario-evidence@1` containing:

- SHA-256 of the scenario fixture;
- SHA-256 of the journal contract;
- immutable accepted event log;
- command ACK/replay results;
- expected Fineract journal intents;
- final folded Fund state;
- cold-start replay result; and
- explicit claim boundaries.

This makes a run reproducible without elevating the runner into program authority.

## First scenario

[`testkit/fund/scenarios/year-1-smoke.json`](../testkit/fund/scenarios/year-1-smoke.json) deliberately includes one duplicate receipt retry:

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

## Fineract adapter seam

The live Fineract lane should consume the emitted journal intents; it should not consume scenario commands directly.

For each intent the adapter will:

1. resolve the synthetic account codes to seeded Fineract GL account IDs;
2. submit the manual journal entry to the pinned Fineract instance;
3. capture returned Fineract transaction and journal-entry identifiers;
4. read the resulting ledger state back from Fineract;
5. attach the Fineract evidence to the intent; and
6. independently reconcile Fineract balances against the folded Baudot Fund state.

A Fineract HTTP 2xx response is therefore an intermediate fact, not the terminal verdict.

## Next event types

The next scenario vocabulary should add these only with explicit accounting semantics and tests:

```text
CONTRIBUTOR_ASSESSMENT_ADJUSTED
CONTRIBUTOR_CREDIT_APPLIED
PROVIDER_CLAIM_ADJUSTED
PROVIDER_RECOVERY_RECOGNIZED
PROVIDER_RECOVERY_RECEIVED
ACCOUNTING_PERIOD_CLOSED
JOURNAL_REVERSED
PROGRAM_YEAR_ADVANCED
```

The important rule is the same one used by the SF26 event runtime: correction is an event, not mutation of history.

## Claim boundary

This runtime proves deterministic synthetic event handling, idempotent replay, cold-start reconstruction, journal-intent generation, and expected-state reconciliation for the implemented scenarios.

It does **not** establish provider eligibility, contributor liability, FCC approval, Rolka Loube production compatibility, Fineract production suitability, payment-network operation, financial-statement compliance, or audit correctness.
