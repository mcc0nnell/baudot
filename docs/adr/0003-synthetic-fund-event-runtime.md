# ADR-0003: Synthetic Fund event runtime

## Status

Accepted for the synthetic proving ground.

## Context

The TRS Fund proving ground already separates program authority from Apache Fineract accounting execution and requires idempotent business transaction identifiers, explicit reversals, and independent reconciliation.

SF26's College Bowl runtime proved a useful operational pattern under unreliable-client conditions: immutable configuration, client-generated idempotency keys, an append-only event log, deterministic state folding, replay after restart, and read-only projections. The Fund lane needs the same class of guarantees, but not the conference-specific runtime or Cloudflare Durable Object implementation.

## Decision

Baudot adopts an infrastructure-neutral event runtime for synthetic Fund scenarios.

The event log is the source of truth for synthetic Fund business activity. Current balances and business state are projections produced by a deterministic reducer. An external ledger such as Fineract receives accounting postings derived from authorized synthetic business events and remains independently reconcilable.

The initial vocabulary covers run configuration, contributor assessments and receipts, provider claim approval and disbursement, explicit transaction reversal, adjustment events, accounting-period closure, and program-year advancement.

Every event carries a unique `transaction_id`. Duplicate delivery of the same identifier is acknowledged as already applied and does not change state. Sequence numbers are monotonic within one run.

Corrections do not delete or mutate prior events. They are represented by explicit reversal or adjustment events referencing preserved history. A reversal negates the accounting projection of its target while retaining both the original and compensating events in the evidence chain.

Program-year configuration is bound to a policy/fixture hash. Events that declare a conflicting policy hash are rejected. Advancing the program year is itself an event and installs the next policy binding without erasing prior balances or evidence.

Closed accounting periods reject new ordinary business events effective on or before the closure date. Later correction policy may permit explicit reversal or authorized open-date compensation, but silent back-dating is not allowed.

## Authority boundary

This runtime does not make Fineract, Cloudflare, a browser client, or any other transport the TRS policy authority.

```text
public policy fixtures
        -> Fund commands/events
        -> deterministic Baudot reducer
        -> expected synthetic Fund state
        -> Fineract journal adapter
        -> independent reconciliation/evidence
```

A balanced Fineract posting is evidence of accounting execution only. It does not establish provider eligibility, contributor liability, payment authorization, FCC approval, routing authority, or accessibility readiness.

## Consequences

Positive:

- five-year scenarios can be replayed from immutable history;
- duplicate retries can be tested without duplicate financial effects;
- crash/cold-start recovery becomes replay rather than special repair logic;
- reversals and retroactive changes preserve provenance;
- the same reducer can drive tests, reference projections, and future operator/debug surfaces;
- Fineract can be compared against an independent expected state rather than trusted as its own oracle.

Costs and limits:

- large scenarios may eventually require checkpoints/snapshots for performance, but snapshots are caches rather than authority;
- domain event vocabulary must remain explicit as Fund scenarios become richer;
- production financial controls are out of scope; this is a synthetic proving-ground runtime;
- the initial reference implementation is intentionally local/in-process and is not a production transaction service.

## Provenance

The architectural donor is the event-sourced `MatchDO` / deterministic fold pattern in `mcc0nnell/sf26`. Baudot ports the pattern, not the conference domain and not its deployment substrate.
