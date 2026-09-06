# ADR 0003: Deterministic synthetic TRS Fund runtime

- Status: Proposed
- Date: 2026-09-05

## Context

Baudot already separates synthetic TRS Fund program semantics from Apache Fineract accounting execution. That boundary is necessary but not sufficient for a replayable proving ground: the repository also needs one explicit authority for accepting admitted Fund events, applying program invariants, mutating synthetic Fund state, and producing evidence that can be replayed independently of external adapters.

SCUMM3/RUSTBELT provides a useful pattern: a canonical model feeds a deterministic runtime; presentation, telemetry, and assurance surround the runtime but do not become runtime authority. Baudot adopts that pattern for the Fund without importing game semantics or making SCUMM3 a dependency.

## Decision

Baudot will model the synthetic TRS Fund as a deterministic event-replay runtime.

```text
public / synthetic source evidence
            |
            v
      admission adapters
            |
            v
   canonical Fund events
            |
            v
      FundRuntimeCore
   deterministic authority
      /      |       \
     /       |        \
Fineract   telemetry   assurance
adapter    receipts    OSCAL/export
   |          |           |
 ledger     Kafka /     evidence
           Parquet /
           Cytoscape
```

Only the Fund runtime may mutate canonical synthetic Fund state. Fineract, Kafka, Ranger, Shiro, Solr, Tika, dashboards, Rolka Loube report views, OSCAL artifacts, and future UI surfaces are adapters, policy enforcement points, evidence consumers, or projections around that state.

### First canonical event vocabulary

The first executable slice admits four event types:

```text
ASSESSMENT_ISSUED
CONTRIBUTION_RECEIVED
CLAIM_APPROVED
PAYMENT_POSTED
```

This is deliberately smaller than the complete Fund lifecycle. Adjustment, reversal, recovery, accounting closure, revised filing, and multi-program-year transitions remain follow-on event types and must earn executable invariants before becoming canonical.

### Root evidence and causation

`ASSESSMENT_ISSUED` and `CLAIM_APPROVED` are authority roots in the first slice. They must carry at least one source reference identifying the synthetic/public evidence from which the admitted decision was derived.

`CONTRIBUTION_RECEIVED` must point to exactly one admitted assessment.

`PAYMENT_POSTED` must point to exactly one admitted approved claim.

The runtime rejects orphan events, duplicate event identifiers, subject mismatches, receipts above their assessment, and payments above their approved claim.

The causation graph is replayable in both directions. For any journal-relevant money movement, the proving ground must be able to recover the admitted authority root that permitted it.

### Determinism

A replay is deterministic when the same ordered canonical event sequence produces the same canonical state and SHA-256 state hash.

No runtime receipt contains wall-clock execution time, random identifiers, adapter response identifiers, or environment-specific data. Such observations may be attached outside the canonical state as evidence.

Every accepted event emits an immutable semantic receipt containing:

```text
event id
event type
event digest
pre-state hash
post-state hash
causation ids
policy version
```

Adjacent receipts form a hash chain at the state boundary: the prior receipt's post-state hash must equal the next receipt's pre-state hash.

### Accounting boundary

Apache Fineract remains the external financial kernel and ledger implementation under test. The deterministic Fund runtime decides what synthetic Fund event occurred and whether it is program-valid. The Fineract adapter translates accepted events into journal operations and returns ledger evidence for independent reconciliation.

Therefore:

```text
FundRuntime acceptance
!= Fineract journal acceptance

Fineract journal acceptance
!= TRS program authorization
```

A future live adapter should consume accepted semantic receipts, post the corresponding journal transaction, retain Fineract transaction identifiers as external evidence, and reconcile the ledger result back to the expected runtime event. Fineract response data must not be inserted into the canonical state hash.

### Identity and policy enforcement boundary

Apache Shiro may authenticate users and service principals. Apache Ranger may enforce resource/action policy at adapter and API boundaries. Neither defines Fund business semantics.

A permitted actor can still propose an invalid Fund event; `FundRuntimeCore` must reject it. Conversely, a valid event cannot bypass authentication/authorization merely because it satisfies Fund invariants.

### Telemetry and provenance boundary

Canonical semantic receipts may be projected to Kafka, OpenTelemetry, NDJSON, Parquet, DuckDB, Powerpipe, or Cytoscape. These systems make the event graph observable and queryable but do not own the event vocabulary or mutate canonical Fund state.

The control-room invariant is:

> Every admitted journal-relevant money movement has a reachable provenance path to an admitted authority root.

For the first slice:

```text
synthetic/public contributor evidence
  -> ASSESSMENT_ISSUED
  -> CONTRIBUTION_RECEIVED

synthetic/public provider claim evidence
  -> CLAIM_APPROVED
  -> PAYMENT_POSTED
```

Fund cash remains fungible; Baudot does not claim that a particular contributor dollar can be identified as the physical dollar used for a particular provider payment. Provenance establishes authorization and accounting lineage, not false earmarking.

### Assurance boundary

OSCAL describes how the proving ground demonstrates requirements. OSCAL is not a Fund event format and is never consumed as runtime state.

This mirrors the established SCUMM3 separation: the runtime consumes its canonical model while assurance evaluates the runtime and its evidence independently.

## Consequences

### Positive

- Public/synthetic Fund scenarios become replayable across machines and time.
- Fineract can be replaced, upgraded, or deliberately faulted without changing Fund semantics.
- Kafka and reporting layers can be rebuilt from receipts instead of becoming hidden sources of truth.
- Reconciliation failures can distinguish program-invalid events from ledger-invalid postings.
- Five-year scenarios can branch from a known state hash and compare policy changes reproducibly.
- Provenance becomes a graph property that can be tested rather than a dashboard convention.

### Costs and limits

- The event vocabulary must stay intentionally small until invariants are executable.
- Policy-version and source-reference discipline becomes mandatory at admission time.
- Adjustments and reversals require explicit semantics rather than mutable record editing.
- Deterministic replay does not by itself prove correctness of public inputs, policy interpretation, Fineract suitability, security controls, or production TRS administration.

## Executable reference

The first reference implementation lives in:

```text
baudot_reference/fund_runtime.py
tests/test_fund_runtime.py
```

It proves deterministic replay, receipt hash chaining, causal lineage, duplicate rejection, orphan rejection, source-evidence requirements, and assessment/claim amount ceilings. It is a proving-ground reference implementation, not a production Fund administrator.
