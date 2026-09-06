---
title: Baudot
description: An open proving ground for accessible real-time communications and synthetic regulated-system evidence.
template: splash
hero:
  title: Systems should prove what they claim.
  tagline: Baudot turns accessible communications behavior and synthetic TRS Fund workflows into executable scenarios with preserved evidence and explicit authority boundaries.
  actions:
    - text: Explore scenarios
      link: /baudot/scenarios/
      icon: right-arrow
    - text: Open the Fund Lab
      link: /baudot/fund-lab/
      icon: right-arrow
    - text: View source
      link: https://github.com/mcc0nnell/baudot
      icon: external
      variant: minimal
---

## Two proving lanes, one rule

Baudot began with accessible real-time communications: specify behavior first, run it against real implementations, preserve the evidence, and never let one layer silently claim authority for another.

That same discipline now drives the Synthetic TRS Fund Lab.

| Communications lane | Fund lane |
| --- | --- |
| T.140 / RTT semantics | public Fund rules and synthetic events |
| SIP / RFC 4103 / WebRTC implementations | Apache Fineract ledger implementation |
| signaling, negotiation, transport, presentation | assessment, receipt, claim, payable, disbursement |
| independent media observation | independent balance reconciliation |
| `connected != usable` | `ledger accepted != program authorized` |

The shared design rule is simple: **a component may contribute evidence, but it does not get to redefine the claim.**

## Accessible communications

Baudot starts with portable accessibility behavior and then tests implementations against it. SIP stacks, WebRTC runtimes, gateways, network substrates, and external media implementations can supply evidence.

```text
T.140 semantics
      │
      ▼
normative vectors
      │
      ▼
baudot-testkit
      │
      ├── SIP / RFC 4103 adapters
      ├── WebRTC / application adapters
      └── external implementation oracles
                │
                ▼
         preserved evidence
                │
                ▼
        independent reducers
```

**Signaling success is not accessibility readiness.** Baudot keeps dialog establishment, negotiation, transport, presentation, and terminal readiness as separate observable facts.

## Synthetic TRS Fund Lab

The Fund lane composes a public-data-calibrated synthetic lifecycle and executes its accounting consequences against a source-pinned Apache Fineract build.

```text
public program-year inputs
        │
        ▼
assessment -> receipt -> Fund cash
        │
        ▼
claim approval -> payable -> disbursement
        │
        ▼
reversal / correction / true-up
        │
        ▼
independent reconciliation + evidence
```

Baudot owns the synthetic Fund domain, policy/rate selection, authorization state, event identity, and expected accounting result. Fineract owns journal execution, transaction IDs, reversals, accounting closure, and ledger balances.

That separation makes a useful negative assertion possible:

```text
Fineract accepted the journal = true
provider eligibility          = not established by that fact
```

The current live lane verifies a pinned Fineract source tree, builds the test container from that source, exercises a deterministic assessment-to-disbursement loop, preserves an explicit reversal, probes accounting closure, and reconciles the final state independently.

[Explore the Synthetic TRS Fund Lab →](/baudot/fund-lab/)

## Evidence is the product

A useful Baudot run preserves enough information to answer three questions later:

1. **What implementation and policy inputs were used?**
2. **What was actually observed?**
3. **What narrow claim does that evidence support?**

That means source commits, build identities, packet or API evidence, transaction IDs, scenario manifests, reducer outputs, and claim boundaries are part of the engineering result rather than cleanup after the test.

## Current proving ground

The communications corpus includes runnable scenarios around re-INVITE correlation, stale SDP, RFC 4103/T.140 readiness, REFER handoff continuity, independent SIP implementations, native PJSIP media, and controlled network evidence through Sandia Wiretap.

The financial corpus includes public Fund arithmetic, contributor assessment fixtures, a canonical journal contract, a live Fineract ledger lane, reversal evidence, accounting-closure negative controls, and the path toward revised Form 499-A true-ups and multi-program-year replay.

Baudot is independent, open source in development, and does not claim general SIP, RFC 4103, T.140, VRS, provider, Fund-administration, accounting, or Fineract conformance beyond the explicit evidence boundary of each scenario.
