# Evidence and governance model

Baudot is designed so that interoperability claims can survive beyond one implementation, one vendor, one deployment, and one maintainer.

The project therefore treats **portable behavior, controlled execution, preserved evidence, and explicit claim boundaries** as first-class project artifacts.

This document describes that model. It is an architectural and governance direction for Baudot. It does **not** claim affiliation with, incubation by, or endorsement from the Apache Software Foundation.

## Why this matters

An interoperability project becomes difficult to govern when its most important knowledge is hidden inside one implementation or one operator's environment.

Baudot takes the opposite approach:

```text
claim
  -> portable contract
  -> deterministic or controlled inputs
  -> execution adapter
  -> observations
  -> preserved evidence
  -> independent reduction
  -> bounded verdict
```

The implementation is replaceable. The claim and the evidence model are not.

## Evidence before authority

No implementation receives correctness authority merely because it is the reference implementation, the first implementation, or the implementation used by a maintainer.

A Baudot verdict should be supportable from artifacts that another implementation can consume or reproduce:

- scenario contracts;
- protocol vectors;
- synthetic fixtures;
- controlled negative arms;
- wire or execution observations;
- independent validators and reducers;
- explicit terminal verdicts; and
- explicit statements of what the evidence does not establish.

Agreement between implementations is useful evidence, but agreement alone is not proof of correctness.

## Behavior before implementation

A durable Baudot behavior should be expressible without requiring a particular SIP stack, browser, media server, carrier, VRS provider, cloud runtime, or test laboratory.

Adapters exist to execute the behavior. They do not get to redefine it.

This gives the project a clean implementation-independence test:

> Could a second implementation consume the same contract without changing the contract to fit itself?

If the answer is no, the contract is probably still coupled to the first implementation.

## Runnable is not proven

Baudot uses an explicit scenario-state vocabulary:

- `planned` — behavior and required evidence are defined;
- `runnable` — at least one execution path exists;
- `proven` — the declared evidence threshold has been produced and verified;
- `regressed` — previously established behavior is known to diverge.

Documentation, a successful demo, or one green implementation does not promote a scenario to `proven`.

Each scenario should describe its own promotion requirements. These may include:

- multiple independent implementations;
- broader timing and failure coverage;
- production-representative gateways;
- independently parsed wire evidence;
- authorized external-system observations; and
- evidence bundles suitable for review by someone who did not author the implementation.

## Claim boundaries are part of the result

A useful interoperability result says both what happened and what was **not** established.

For example, the iTRS route-handoff proving ground can establish that a synthetic authoritative route was consumed by JAIN SIP while preserving the logical SIP Request-URI. That result does not establish live TRS Numbering Directory access, production VRS interoperability, SIP conformance, provider certification, or emergency-call correctness.

Those limits are not disclaimers added after the fact. They are part of the test contract.

## Clean-room donor discipline

Historical and external systems may expose valuable interoperability behavior.

Baudot may use those systems to identify scenarios and invariants, but donor code is not automatically imported. When licensing, provenance, or implementation coupling makes reuse inappropriate, Baudot treats the external system as behavioral prior art and reimplements the behavior from a clean specification or test description.

The ACE Direct iTRS work is an example of this boundary:

```text
historical behavior
      |
      v
portable invariant
      |
      v
synthetic Baudot fixture
      |
      v
independent implementation
```

The goal is to preserve the interoperability lesson without making the donor implementation the normative source of truth.

## Separation of authorities

Baudot intentionally separates several kinds of authority that are often collapsed in communications systems:

- **protocol authority** — what a standard or contract requires;
- **routing authority** — where a communications identity currently resolves;
- **transport discovery** — how the selected route is reached on the network;
- **implementation behavior** — what a particular stack does;
- **evidence authority** — what observations actually support the verdict; and
- **project governance** — how contracts, tests, and claims evolve.

For the Tilden/Baudot boundary this becomes:

```text
Tilden-style resolution
    -> logical communications route

Baudot
    -> signaling / transport execution

Testkit
    -> observations / evidence / verdict
```

A downstream SIP success must not retroactively redefine the authoritative route. Likewise, a routing result must not be treated as proof that media or accessibility behavior succeeded.

## Independent implementation target

The strongest interoperability evidence is not one implementation passing many tests. It is multiple independent implementations satisfying the same portable contract without provider-specific changes to the contract or reducer.

The current proving ensemble already distinguishes roles:

- **JAIN SIP** — glass-box signaling instrument;
- **Elixip** — independent SIP/call-state implementation oracle;
- **Apache OpenMeetings** — integration specimen and scenario donor;
- **ACE Direct** — historical production donor corpus; and
- **Wiretap** — controlled network/evidence substrate.

No member of the ensemble is the verdict authority by itself.

The next maturity threshold is repeated execution of the same route, signaling, readiness, and handoff contracts across independent implementations.

## Apache-style proof

Baudot uses the phrase **Apache-style proof** informally to describe an engineering direction, not project status.

In this context it means that the useful asset is becoming larger than one codebase:

1. behavior is specified independently of implementation;
2. tests are reproducible and machine-verifiable;
3. interoperability failures become portable scenarios;
4. evidence and claim limits are preserved in the repository;
5. donor provenance and licensing boundaries are explicit;
6. multiple implementations can participate without one becoming normative by default; and
7. project value can be governed around shared contracts and evidence rather than private deployment knowledge.

This is the shape required for credible shared infrastructure, regardless of where the project is ultimately governed.

## What would strengthen the case

The next evidence milestones are concrete:

- run `BAUDOT-INTEROP-005` against a second independent SIP implementation;
- replace loopback-only transport injection with deterministic NAPTR/SRV execution evidence;
- preserve route identity and transport-selection evidence separately;
- exercise additional failure and timing arms;
- add authorized external iTRS observations without exposing credentials or subscriber data;
- preserve CI artifacts and terminal reductions for review; and
- continue moving scenario semantics out of implementation-specific harness code and into portable contracts.

A future governance proposal should be built from that evidence. It should not depend on a claim that the project is important because its original author says it is.

## Non-affiliation

Baudot is currently an independent project. References to Apache projects, Apache-style engineering, or possible future community governance do not imply that Baudot is an Apache Software Foundation project, podling, proposal, or endorsed initiative.
