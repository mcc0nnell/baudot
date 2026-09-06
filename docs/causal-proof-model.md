# Causal proof model

Baudot already treats interoperability as an evidence problem rather than a stack-integration problem. The repository repeatedly preserves distinctions such as:

```text
connected != usable
negotiated != ready
routed != authorized
ledgered != eligible
implementation agreement != conformance
```

This document turns that discipline into an explicit **causal proof model**.

The model is intentionally small. It is not a general theorem prover and it does not replace scenario-specific reducers. Its purpose is to make one repository-wide rule mechanically checkable:

> **A stronger claim must have an explicit, acyclic derivation from evidence-bearing facts under scoped authority.**

The design method is:

```text
define -> derive -> execute -> observe -> prove
```

## Why this exists

As Baudot composes more external implementations, adapters, routing systems, application sources, fund models, and control-plane components, successful composition creates a recurring risk: a weaker observation can accidentally be promoted into a stronger claim merely because it occurred next to another successful component.

Examples:

```text
SIP 200 OK
  != usable session

m=text negotiated
  != RTT ready

Tilden route resolved
  != execution authorized

Fineract journal posted
  != claim approved

two implementations agree
  != protocol conformance

Zoom transcript observed
  != T.140 semantics

REFER accepted
  != replacement RTT ready

Camel workflow completed
  != accessibility ready
```

The causal proof model makes these invalid promotions data rather than prose.

## Vocabulary

### Fact

A **fact** is an evidence-bearing observation or authority-bound decision.

Examples:

```text
rtt.negotiated
t140.semantic.observed
route.resolved
execution.authorized
fund.claim.approved
ledger.posted
```

A fact does not become stronger because it was produced by an impressive implementation or occurred inside a successful end-to-end run.

Every source fact in the machine-readable contract therefore declares:

- a fact identifier;
- the authority allowed to assert it; and
- `evidenceRequired=true`.

### Rule

A **rule** is a deterministic derivation.

A rule declares:

```text
requiresAll -> produces
```

For example:

```text
rtt.negotiated
+
t140.semantic.observed
-----------------------
rtt.ready
```

The dependency list is explicit. A reducer may not silently substitute another observation because it is convenient, correlated, or usually present.

### Claim

A **claim** is the output of a rule.

Claims can become dependencies of later rules. That permits a bounded proof chain such as:

```text
replacement.dialog.established
+
replacement.t140.semantic.observed
        |
        v
replacement.rtt.ready
        |
        v
old-leg.safe-to-release
```

The final claim is explainable because the entire chain is retained.

### Authority

**Authority** is scoped to a fact or derivation class.

Composition does not transfer authority.

```text
external implementation
  can supply observation
  cannot mint Baudot conformance

Tilden
  can supply route-selection evidence
  cannot mint RTT readiness

control plane
  can supply authorization/execution receipts
  cannot mint accessibility readiness

ledger
  can supply posting observations
  cannot mint fund eligibility
```

### Evidence reference

An **evidence reference** binds a fact to preserved evidence.

The initial meta-contract validates that source facts require evidence. Scenario-specific schemas remain responsible for the concrete artifact reference, hash, correlation identifier, packet trace, source record, receipt, or manifest used by that lane.

### Derivation

A **derivation** is the directed acyclic graph from source facts through rules to the bounded claim.

Cycles are invalid. A claim cannot eventually justify itself.

## Canonical proof shape

```text
source implementation / authority
            |
            v
    evidence-bearing fact
            |
            | explicit rule
            v
       derived claim
            |
            | explicit rule
            v
     terminal bounded claim
            |
            v
     preserved derivation
```

The terminal result is not a side effect of the workflow. It is the output of the derivation.

## Forbidden promotion catalog

`testkit/meta/causal-proof-contract-v1.json` freezes the first repository-level forbidden promotions:

```text
signaling.connected
  -/-> session.usable

rtt.negotiated
  -/-> rtt.ready

route.resolved
  -/-> execution.authorized

ledger.posted
  -/-> fund.claim.approved

implementation.agreement.observed
  -/-> conformance

source.transcript.observed
  -/-> rtt.ready

refer.accepted
  -/-> replacement.rtt.ready

workflow.completed
  -/-> accessibility.ready
```

A forbidden promotion does not mean the weaker fact is irrelevant. It means that fact is **insufficient by itself**.

For example, `rtt.negotiated` is a required input to the first RTT rule, but it needs independent T.140 semantic observation before `rtt.ready` can be derived.

## Initial derivation rules

The first contract deliberately uses existing Baudot boundaries rather than inventing a new application model.

### RTT readiness

```text
rtt.negotiated
+
t140.semantic.observed
        |
        v
rtt.ready
```

### Replacement-leg release safety

```text
replacement.dialog.established
+
replacement.t140.semantic.observed
        |
        v
replacement.rtt.ready
        |
        v
old-leg.safe-to-release
```

This captures the existing `BAUDOT-INTEROP-004` discipline: REFER acceptance and replacement signaling are not enough to authorize teardown of the original accessible leg.

### Route execution

```text
route.resolved
+
execution.authorized
        |
        v
route.execution.permitted
```

Tilden routing evidence and control-plane authorization remain different facts.

### Fund payable confirmation

```text
fund.claim.approved
+
ledger.posted
        |
        v
fund.payable.confirmed
```

A ledger posting cannot create its own upstream program authority.

### Implementation agreement

```text
implementation.a.observed
+
implementation.b.observed
        |
        v
implementation.agreement.observed
```

The derivation intentionally stops there. No rule promotes agreement into conformance.

## Executable fixtures

The contract includes both positive and negative derivation fixtures.

Positive fixtures prove that the intended dependency graph can derive:

- RTT readiness;
- replacement-leg safe release;
- authorized route execution;
- a claim-backed ledger payable observation; and
- implementation agreement.

Negative fixtures prove that the forward-chaining reducer cannot derive stronger claims from:

- connection alone;
- negotiation alone;
- routing alone;
- ledger posting alone;
- implementation agreement;
- application transcript observation;
- REFER acceptance; or
- orchestration completion.

The validator also rejects:

- duplicate authorities, facts, rules, or fixture identifiers;
- facts without evidence requirements;
- unknown authorities;
- unknown dependencies;
- duplicate canonical rules for one derived claim;
- facts that are simultaneously declared as derived claims;
- self-dependencies;
- recursive/cyclic derivations; and
- any canonical rule that becomes satisfiable solely from a declared forbidden weaker source set.

## Relationship to scenario reducers

This meta-contract does **not** replace the existing reducers.

Instead:

```text
scenario-specific evidence
        |
        v
scenario-specific reducer
        |
        v
typed facts / claims
        |
        v
causal dependency discipline
```

A PJSIP native-media reducer still owns the actual RFC 4103/T.140 observation logic. A Tilden handoff reducer still owns route-selection correlation. A Fund reducer still owns its synthetic business rules.

The causal model checks the **shape of promotion** across those domains.

## Relationship to the repository convergence plan

The convergence plan says:

```text
observation != stronger claim
```

and requires each branch to make its authority boundary explicit and keep executable claims no stronger than preserved evidence.

This contract is the machine-readable form of that rule.

As more proving lanes converge on `main`, new repository-wide distinctions should be added here only when they are stable across domains. Scenario-specific details should remain in their own contracts.

## Design rule for future work

When adding a new terminal result, ask five questions:

1. **Define:** What exact claim is being made?
2. **Derive:** Which independent facts are necessary to justify it?
3. **Execute:** Which component performs the operation under test?
4. **Observe:** Which authority records each required fact, and where is the evidence?
5. **Prove:** Which deterministic reducer joins those facts into the bounded claim?

If a terminal result cannot answer those questions, it is not ready to become a canonical Baudot claim.

The design intuition is geometric rather than rhetorical: later claims should be inspectable consequences of declared definitions, evidence, and prior facts.

## Run

```bash
python scripts/validate_causal_proof_contract.py
```

Expected terminal output includes:

```text
causal proof contract: PASS
```

## Claim boundary

This contract is a **repository architecture guardrail**.

It does not establish:

- a general formal proof system;
- SIP, SDP, RFC 4103, T.140, REFER, WebRTC, VRS, or other protocol conformance;
- production accessibility readiness;
- production routing authority;
- production TRS Fund authority; or
- correctness of evidence that a scenario-specific reducer has not independently validated.

Its claim is narrower: Baudot can make its cross-domain evidence-to-claim dependency discipline explicit, acyclic, deterministic, and executable.
