---
title: Scenario catalog
description: Portable interoperability scenarios and their current claim boundaries.
---

The machine-readable scenario definitions in `testkit/scenarios/` remain authoritative. This page is the human-readable index.

| Scenario | Status | Question |
| --- | --- | --- |
| `BAUDOT-INTEROP-001` | planned | Where do signaling, ICE, rendering, and RTT readiness diverge under stalled ICE? |
| `BAUDOT-INTEROP-003` | runnable | Can re-INVITE request identity, fresh SDP, and RTT readiness remain independently observable? |
| `BAUDOT-INTEROP-004` | runnable | Can a REFER handoff preserve the old leg until the intended replacement leg is accessibility-ready? |

## BAUDOT-INTEROP-001 — stalled ICE

This planned scenario preserves the point at which session establishment, ICE readiness, rendered media, and RTT readiness diverge. Historical ACE Direct behavior motivates the scenario but does not establish a current implementation defect.

## BAUDOT-INTEROP-003 — re-INVITE correlation

The runnable proving path covers message-level request correlation, live overlapping in-dialog INVITE glare, stale-SDP detection, and independent RTT readiness reduction. A successful `200` does not prove that the active media description is fresh or usable.

## BAUDOT-INTEROP-004 — REFER continuity

The runnable transfer scenario keeps REFER acceptance, NOTIFY progression, replacement-dialog establishment, target identity, RTT negotiation, first T.140 observation, and old-leg teardown as separate facts.

A signaling-only arm can therefore reach a successful transfer state while still producing:

```text
rttNegotiated=true
firstT140CharacterObserved=false
rttReady=false
oldLegPreserved=true
```

That distinction is the point of the scenario.

## Promotion rule

`planned`, `runnable`, and `proven` are evidence states, not marketing labels. Documentation cannot promote a scenario. A stronger status requires the scenario's declared evidence conditions to be satisfied.
