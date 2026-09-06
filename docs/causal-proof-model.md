# Causal proof model

Baudot treats interoperability as an evidence problem rather than a stack-integration problem. The repository repeatedly preserves distinctions such as:

```text
connected != usable
negotiated != ready
routed != authorized
ledgered != eligible
implementation agreement != conformance
```

This document turns that discipline into an explicit **causal proof model**.

> **A stronger claim must have an explicit, acyclic derivation from evidence-bearing facts under scoped authority.**

The design method is:

```text
define -> derive -> execute -> observe -> prove
```

The model is intentionally small. It is not a general theorem prover and it does not replace scenario-specific reducers.

## Why this exists

Composition creates a recurring failure mode: a weaker observation is promoted into a stronger claim because it occurred next to another successful component.

Examples:

```text
SIP 200 OK                     != usable session
m=text negotiated              != RTT ready
Tilden route resolved          != execution authorized
Fineract journal posted        != claim approved
validated journal contract     != ledger posted
calibrated public Fund model   != claim approved
two implementations agree     != protocol conformance
Zoom transcript observed       != T.140 semantics
REFER accepted                 != replacement RTT ready
Camel workflow completed       != accessibility ready
```

The causal model makes those invalid promotions data rather than prose.

## Vocabulary

### Fact

A **fact** is an evidence-bearing observation or authority-bound decision.

Every source fact in `testkit/meta/causal-proof-contract-v1.json` declares:

- a fact identifier;
- the authority allowed to assert it; and
- `evidenceRequired=true`.

A fact does not become stronger because its producer is trusted or because the surrounding workflow succeeded.

### Rule

A **rule** is a deterministic derivation:

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

Every dependency is explicit.

### Claim

A **claim** is the output of a rule. Claims may feed later rules, which makes a bounded proof chain possible.

### Authority

Authority is scoped to a fact or derivation class. Composition does not transfer authority.

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

Fund calibration
  can establish a bounded public/synthetic model
  cannot approve a provider claim

journal contract validator
  can establish accounting shape
  cannot assert that Fineract posted anything

ledger execution observer
  can supply posting observations
  cannot mint fund eligibility or approval
```

### Evidence reference

An **evidence reference** binds a source fact to a preserved artifact. Portable proof manifests use relative artifact paths, SHA-256 digests, and the reducer that interpreted the artifact.

### Derivation

A **derivation** is the directed acyclic graph from source facts through rules to a bounded claim. A claim cannot recursively justify itself.

## Canonical proof shape

```text
source implementation / authority
            |
            v
    preserved evidence
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
       explainable trace
```

The terminal result is not a side effect of the workflow. It is the output of the derivation.

## Forbidden promotion catalog

The repository-level forbidden promotions currently include:

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

fund.public-model.calibrated
  -/-> fund.claim.approved

ledger.contract.validated
  -/-> ledger.posted
```

A forbidden promotion means the weaker fact is insufficient by itself. It may still participate in a stronger derivation with independent evidence.

## Initial derivation rules

### RTT readiness

```text
rtt.negotiated
+
t140.semantic.observed
        |
        v
rtt.ready
```

### Replacement-leg readiness and release safety

The replacement path deliberately requires **three independent facts**:

```text
replacement.dialog.established
+
replacement.rtt.negotiated
+
replacement.t140.semantic.observed
        |
        v
replacement.rtt.ready
        |
        v
old-leg.safe-to-release
```

Dialog establishment cannot substitute for RTT negotiation. RTT negotiation cannot substitute for semantic T.140 observation. REFER acceptance does not appear in the readiness rule at all.

This is the `BAUDOT-INTEROP-004` continuity discipline made explicit.

### Route execution

```text
route.resolved
+
execution.authorized
        |
        v
route.execution.permitted
```

Tilden route-selection evidence and control-plane execution authority remain different facts.

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

The current Fund proving ground is intentionally earlier in that chain:

```text
public-source calibration
        |
        v
fund.public-model.calibrated
        -/-> fund.claim.approved

journal contract validation
        |
        v
ledger.contract.validated
        -/-> ledger.posted
```

That distinction matters because the repository currently validates public arithmetic, synthetic contributor assessments, and the Fineract journal contract, but does not yet execute Fineract. A positive `fund.payable.confirmed` proof therefore remains unavailable until a later lane preserves both independently authorized claim evidence and actual ledger execution evidence.

### Implementation agreement

```text
implementation.a.observed
+
implementation.b.observed
        |
        v
implementation.agreement.observed
```

The derivation intentionally stops there. No rule promotes implementation agreement into conformance.

## Portable causal proof manifests

`baudot.causal-proof-manifest@1` binds an actual scenario run to the meta-contract.

A manifest contains:

- scenario and correlation identifiers;
- the causal contract it uses;
- an evidence root;
- source facts with declared authority;
- one or more content-addressed evidence references per source fact;
- expected claims; and/or
- claims that must remain underivable.

The verifier is:

```bash
python scripts/validate_causal_proof_manifest.py path/to/causal-proof.json
```

It checks that:

1. every source fact exists in the causal contract;
2. every source fact uses the contract's declared authority;
3. every evidence path stays within the declared evidence root;
4. every evidence file exists and matches its SHA-256 digest;
5. expected claims are derivable from only the declared source facts; and
6. forbidden claims are known and remain underivable.

The verifier recomputes the derivation. A manifest does not get to declare its own proof steps as truth.

## Live binding: BAUDOT-INTEROP-004

The live JAIN SIP REFER/RTT handoff emits:

```text
target/evidence/BAUDOT-INTEROP-004/
  jain-live-refer-rtt-v1/
    control/
      result.properties
      rtt-datagram-received.bin
      ...
    signaling-only/
      result.properties
      ...
    terminal/
      refer-rtt-readiness.json
      causal-proof.json
      manifest.sha256
```

The control proof supplies:

```text
replacement.dialog.established
replacement.rtt.negotiated
replacement.t140.semantic.observed
```

and must derive:

```text
replacement.rtt.ready
old-leg.safe-to-release
```

The signaling-only proof supplies:

```text
refer.accepted
replacement.dialog.established
replacement.rtt.negotiated
```

and must **not** derive:

```text
replacement.rtt.ready
old-leg.safe-to-release
```

That negative arm is important. Successful REFER signaling, a replacement dialog, and negotiated RTT still do not authorize release of the original accessible leg without independently reduced T.140 evidence.

The live runner treats portable proof validation as a separate gate:

```text
producer
  -> scenario-specific reducer
      -> causal proof manifest
          -> causal proof verifier
```

Failures remain distinguishable.

## Bounded Fund binding

The public TRS Fund validator now emits:

```text
target/evidence/TRS-FUND-PUBLIC-MODEL/
  validation.json
  causal-proof.json
```

`validation.json` records content hashes for the public calibration fixture, contributor-assessment fixture, and Fineract journal contract. It records two facts:

```text
fund.public-model.calibrated
ledger.contract.validated
```

and also records:

```text
liveFineractExecution=false
```

The paired causal proof is deliberately negative:

```text
fund.public-model.calibrated
  -/-> fund.claim.approved

ledger.contract.validated
  -/-> ledger.posted
```

This makes the Fund lane useful before live execution exists: CI proves that successful calibration and schema/accounting validation cannot silently promote themselves into business approval or execution facts.

When a live/pinned Fineract adapter later exists, the positive proof target is already defined:

```text
fund.claim.approved
+
ledger.posted
        |
        v
fund.payable.confirmed
```

## Relationship to scenario reducers

The meta-contract does not replace existing reducers.

```text
scenario-specific evidence
        |
        v
scenario-specific reducer
        |
        v
typed source facts
        |
        v
causal proof manifest
        |
        v
repository-wide derivation rules
```

The PJSIP/JAIN/reference reducers still own SIP, RTP, RFC 4103, T.140, route, Fund, or other domain-specific interpretation. The causal layer checks the **shape of promotion across domains**.

## Executable fixtures

`python scripts/validate_causal_proof_contract.py` validates the contract itself, including:

- unique authorities, facts, rules, and fixtures;
- evidence requirements for all source facts;
- known authorities and dependencies;
- one canonical rule per derived claim;
- acyclic derivation;
- forbidden-promotion safety; and
- positive and negative forward-chaining fixtures.

The current contract has:

```text
17 evidence-bearing source facts
8 acyclic derivation rules
10 forbidden promotions
5 positive derivation fixtures
10 negative derivation fixtures
```

`python scripts/validate_causal_proof_manifest.py --self-test` exercises both positive and negative replacement-leg proofs plus digest tampering, authority mismatch, evidence-root escape, and unknown-claim rejection.

The causal contract workflow runs the meta-contract checks and portable-verifier self-test. The TRS Fund workflow separately generates and validates the bounded Fund proof.

## Relationship to repository convergence

The convergence plan says:

```text
observation != stronger claim
```

and requires each branch to make authority boundaries explicit and keep executable claims no stronger than preserved evidence.

The causal contract is the machine-readable form of that rule. Portable proof manifests are its run-level form.

## Design rule for future work

When adding a terminal result, ask five questions:

1. **Define:** What exact claim is being made?
2. **Derive:** Which independent facts are necessary to justify it?
3. **Execute:** Which component performs the operation under test?
4. **Observe:** Which authority records each source fact, and where is the evidence?
5. **Prove:** Which deterministic rule chain reaches the bounded claim?

If a terminal result cannot answer those questions, it is not ready to become a canonical Baudot claim.

The design intuition is geometric rather than rhetorical: later claims should be inspectable consequences of declared definitions, evidence, and prior facts.

## Run

```bash
python scripts/validate_causal_proof_contract.py
python scripts/validate_causal_proof_manifest.py --self-test
python scripts/validate_trs_fund_public_model.py
python scripts/validate_causal_proof_manifest.py \
  target/evidence/TRS-FUND-PUBLIC-MODEL/causal-proof.json
```

For a live `BAUDOT-INTEROP-004` run:

```bash
scripts/run-live-refer-rtt-handoff.sh
```

The runner generates and validates the portable proof bundle as part of the gate.

## Claim boundary

This is a **repository architecture guardrail**.

It does not establish:

- a general formal proof system;
- SIP, SDP, RFC 4103, T.140, REFER, WebRTC, VRS, or other protocol conformance;
- production accessibility readiness;
- production routing authority;
- production TRS Fund authority;
- live Fineract execution when no execution evidence exists; or
- correctness of evidence that a scenario-specific reducer has not independently validated.

Its claim is narrower: Baudot can make its cross-domain evidence-to-claim dependency discipline explicit, acyclic, deterministic, content-addressed, portable, and executable.
