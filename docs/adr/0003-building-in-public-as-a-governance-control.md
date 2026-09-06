# ADR-0003: Building the synthetic TRS Fund in public as a governance control

- Status: Accepted
- Date: 2026-09-06
- Decision owners: Baudot maintainers

## Context

Baudot's synthetic TRS Fund proving ground already separates the Fund domain from Apache Fineract. Baudot owns synthetic program events, policy/rate selection, authorization state, expected accounting consequences, and reconciliation. Fineract is an external accounting kernel that may accept or reject the resulting journal operation.

That separation is necessary but not sufficient for a public proving ground. A balanced journal can still represent an unauthorized payment. A provider can be authorized while the service event is invalid. A payment can be fully authorized while the ledger rejects it. A later correction can be mathematically correct while destroying the original decision history.

If those distinctions exist only in prose, the architecture is easy to collapse accidentally as the system grows.

The public repository therefore needs to make the governance model itself inspectable and executable.

## Decision

Baudot will treat **building the synthetic TRS Fund in public as part of the proving-ground control environment**.

Public development is not itself legal or program authority, and the repository does not model or disclose production Fund systems. Its governance value comes from making the declared decision boundaries, evidence requirements, negative controls, history rules, and implementation provenance independently inspectable and replayable.

### 1. Program authority and accounting execution remain separate decisions

The synthetic Fund will preserve at least these distinct facts:

```text
event authenticity
        |
        v
service validity
        |
        v
provider authority
        |
        v
program compensability
        |
        v
payment authorization
        |
        v
accounting execution
        |
        v
independent reconciliation
```

The first five facts are pre-ledger program gates. Fineract may execute accounting after those gates are satisfied, but Fineract journal acceptance, balanced debits and credits, or returned transaction IDs cannot create missing program authority.

Conversely, an authorized payment is not proven to have been executed merely because the authorization exists. Ledger rejection remains an accounting-execution fact and must be preserved as such.

### 2. Every decision boundary declares its owner and evidence

The machine-readable contract at `testkit/fund/governance-boundaries-v1.json` assigns each decision a distinct owner, required evidence, and facts that cannot substitute for it.

The ownership vocabulary is intentionally implementation-neutral. A future implementation may use Apache Shiro for application identity/session controls, Apache Ranger for policy enforcement, Kafka for evidence transport, or another component without changing the meaning of the decision itself.

The decision model must survive replacement of any implementation component.

### 3. Negative controls are first-class governance evidence

The governance lane must include cases where apparently successful downstream behavior is insufficient.

At minimum:

```text
balanced + accepted journal
without payment authorization
        => NOT AUTHORIZED FOR LEDGER

provider authorized
but service invalid
        => NOT AUTHORIZED FOR LEDGER

all program gates satisfied
but ledger rejects posting
        => AUTHORIZED FOR LEDGER
           + ACCOUNTING EXECUTION FAILED
```

These cases prevent accidental authority collapse. They also make it possible to distinguish a policy failure from an implementation failure during incident review.

### 4. History is append-only at the program boundary

Original synthetic source events and decisions are not silently rewritten.

Corrections, reversals, revised filings, rate changes, and recoveries are represented as new events that preserve correlation to the original event and the rule version in force when each decision was made.

The accounting layer may expose native reversal primitives, but a reversal does not erase the original authorization or posting evidence.

### 5. Policy and rate versions bind at decision time

Every compensability or payment-authorization decision that depends on a policy, contribution factor, compensation rate, eligibility rule, or program year must preserve the exact version used for that decision.

A replay may intentionally use a different rule version, but it must create a new run rather than mutate the historical result.

### 6. Public provenance is part of the evidence bundle

For external implementations under test, Baudot preserves enough provenance to identify what actually executed the scenario.

For the Fineract lane this includes the source release/commit, source-built container identity, toolchain, returned journal/transaction identifiers, and independently observed balances.

The same principle applies to future external policy, identity, messaging, or reporting components: version labels alone are not sufficient when stronger source/build provenance is available.

### 7. Public-source boundaries are explicit

The governance benefit of building in public does not justify reproducing confidential or production data.

The public proving ground may use:

- public FCC rules, orders, formulas, and program-year values;
- public Rolka Loube reports and rate tables;
- Baudot-owned synthetic provider, contributor, claim, payment, adjustment, and routing records; and
- open-source implementation and CI provenance.

It must not require or reconstruct:

- nonpublic provider submissions;
- confidential provider cost or demand data;
- production Fund-administrator schemas, credentials, banking details, or internal workflows;
- live contributor filings, invoices, or account records;
- subscriber records; or
- production iTRS Numbering Directory data.

### 8. Upstream defects return to the commons without exporting TRS policy

When the synthetic Fund exposes a generic defect in an external open-source component, Baudot should reduce the finding to the smallest component-native reproducer before proposing an upstream patch.

TRS-specific policy remains in Baudot. Generic accounting, idempotency, reversal, audit, external-ID, or consistency defects may become upstream Apache Fineract contributions when they can be stated independently of the synthetic Fund.

This keeps the proving ground useful to the wider open-source ecosystem without making Fineract responsible for TRS program semantics.

## Executable contract

The first governance contract is:

```text
testkit/fund/governance-boundaries-v1.json
scripts/validate_trs_fund_governance.py
```

The validator proves structural properties of the control model and executes the declared negative controls without requiring Fineract.

It specifically checks that:

- pre-ledger decision identifiers and facts are unique;
- at least five distinct pre-ledger gates exist;
- Fineract owns no pre-ledger program decision;
- ledger acceptance cannot substitute for any program gate;
- every decision declares required evidence;
- an accepted balanced journal can remain unauthorized;
- an authorized payment can coexist with ledger rejection;
- corrections preserve original history; and
- the public source boundary declares both allowed and excluded source classes.

The live Fineract lane remains necessary to prove actual accounting execution. The governance validator does not replace it.

## Consequences

### Positive

- Governance properties become reviewable as code and fixtures rather than architectural intent alone.
- Reviewers can tell which decision failed without treating all failures as accounting failures.
- A ledger implementation can be replaced without changing TRS program authority.
- Historical policy/rate changes can be replayed without rewriting prior decisions.
- Public CI creates a reproducible record of what the synthetic model claimed and what the external implementation actually did.
- Generic defects discovered by the Fund lab can be reduced into credible upstream patches.

### Costs

- Decision and evidence schemas require versioning discipline.
- More negative controls must be maintained as new Fund lifecycle stages are added.
- Public fixtures must remain synthetic even when production analogies would make shortcuts tempting.
- A passing public governance lane proves only the declared synthetic control model; it is not certification of a production Fund system.

## Rejected alternatives

### Let the ledger define payment validity

Rejected. Double-entry correctness establishes accounting consistency, not provider entitlement, service validity, program eligibility, or payment authority.

### Put all authorization in one generic policy decision

Rejected. Event authenticity, service validity, provider authority, program compensability, and payment authorization fail for different reasons and require different evidence.

### Rewrite historical fixtures when rules change

Rejected. That destroys the ability to explain what rule produced an earlier result and makes reproducibility impossible.

### Treat public development as permission to mirror production data

Rejected. Inspectable controls do not require confidential or production records. The proving ground remains public-data-calibrated and synthetic.

## Follow-up

1. Keep the governance validator in the ordinary synthetic Fund CI lane.
2. Bind future claim/payment fixtures to explicit policy and rate-version identifiers.
3. Add an evidence manifest that carries source hash, receive time, flow/correlation IDs, authorization IDs, policy/rate versions, and returned ledger IDs through one composed payment scenario.
4. Add a negative live-lane case where a deliberately unauthorized synthetic event is never submitted to Fineract even though its journal would balance.
5. Add a second live-lane case where an authorized event reaches Fineract and is rejected for an accounting reason, preserving both facts.
6. Reduce generic defects discovered by those cases into minimal upstream Fineract reproducers before proposing patches.
