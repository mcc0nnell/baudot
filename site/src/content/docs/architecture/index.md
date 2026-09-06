---
title: System shape
description: Baudot keeps domain authority, implementation evidence, and verdict reduction separate.
---

Baudot is not one stack. It is a proving-ground architecture for systems where several implementations can contribute facts without being allowed to redefine the claim.

## Shared evidence-first shape

Both major proving lanes follow the same control pattern:

```text
declared behavior / policy
          |
          v
    deterministic scenario
          |
          v
 external implementation
          |
          v
    preserved evidence
          |
          v
 independent reduction
          |
          v
      scoped claim
```

The implementation under test is intentionally not the final verdict authority.

## Accessible communications lane

```text
T.140 semantics
      |
      v
normative vectors
      |
      v
baudot-testkit
      |
      +--> JAIN SIP / RFC 4103
      +--> Elixip
      +--> PJSIP native text media
      +--> Sandia Wiretap network substrate
      |
      v
preserved signaling / media / topology evidence
      |
      v
independent readiness reduction
```

This is why a confirmed SIP dialog and negotiated `m=text` do not automatically become `rttReady=true`. Readiness has to be earned from the evidence appropriate to the scenario.

## Synthetic TRS Fund lane

```text
public program rules / program-year inputs
          |
          v
 Baudot synthetic Fund domain
  filing / assessment / receipt /
  claim / approval / payment /
  adjustment / true-up
          |
          v
 canonical journal contract
          |
          v
 source-pinned Apache Fineract
          |
          v
transaction IDs + journal rows + closure behavior
          |
          v
independent Baudot reconciliation
```

The authority split is deliberate. Baudot owns synthetic provider and contributor identity, filing lineage, policy/rate selection, authorization state, event correlation, and expected balances. Fineract owns accounting execution: GL resource IDs, journal acceptance or rejection, reversals, closures, and observed ledger balances.

```text
Fineract journal accepted
        !=
TRS program authorized
```

That boundary prevents the banking model from quietly becoming the regulatory model.

## Implementation ensemble

The proving ground uses implementations for different roles rather than asking one system to be both the subject and the judge.

- **JAIN SIP** — glass-box signaling instrument.
- **Elixip** — independent SIP/call-state oracle.
- **PJSIP/PJPROJECT** — external native RTT media oracle for qualified profiles.
- **Sandia Wiretap** — controlled network/evidence substrate, never verdict authority.
- **Apache Fineract** — external accounting kernel for the synthetic Fund lane, never TRS program authority.
- **Apache OpenMeetings** — integration specimen and scenario donor.
- **ACE Direct** — historical donor corpus used to motivate scenarios without copying workarounds forward.

The same pattern can admit additional gateways, WebRTC runtimes, VRS mocks, hardware endpoints, legacy media implementations, and accounting engines without moving their behavior into Baudot's authority core.

## Stable domain identifiers, runtime implementation IDs

Baudot keeps its scenario vocabulary stable across implementation runs.

For the Fund lane, account numbers such as `1100` and event IDs such as `EVT-ASSESS-0001` are Baudot domain identifiers. Fineract-generated numeric account resource IDs, transaction IDs, and journal-entry IDs are execution evidence attached to that run.

For communications scenarios, the same principle applies to scenario IDs, call-leg roles, readiness facts, and implementation-local dialog or media identifiers.

## Preserve corrections rather than rewriting history

The architecture prefers explicit state transitions and evidence-bearing corrections:

- RTT handoff preserves the old leg until the replacement leg earns readiness;
- Fund disbursement correction uses explicit reversal and a distinct repost;
- revised contributor filings should create a delta rather than rewrite the original assessment; and
- later replay should preserve the policy version that applied when each event occurred.

That makes time part of the test instead of an obstacle to reproducibility.

## Claim boundaries remain first-class

A passing scenario supports only the claim declared for that scenario and evidence profile. It does not automatically establish general protocol conformance, production readiness, provider interoperability, program authorization, accounting compliance, or suitability outside the tested boundary.
