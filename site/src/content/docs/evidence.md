---
title: Evidence model
description: How Baudot turns observations into scoped interoperability and systems claims.
---

The evidence model is intentionally stricter than a pass/fail integration test.

## Facts stay source-identified

A SIP stack can report that a dialog confirmed. A network probe can report that a datagram crossed a boundary. A reference parser can classify a T.140 block. Fineract can report that it accepted a journal and returned transaction IDs. Those facts remain attributable to their source.

Implementation agreement is useful evidence, but correctness is not decided by majority vote.

## Authority stays with the right layer

Baudot does not let one successful layer silently promote a broader claim.

For RTT handoff:

```text
replacement dialog established = true
RTT negotiated                 = true
first T.140 character observed = false
---------------------------------------
RTT ready                      = false
```

For the synthetic Fund lane:

```text
journal balanced               = true
Fineract accepted posting      = true
provider eligibility           = not established
payment authorization          = not established by ledger acceptance
```

The pattern is the same: **connected is not usable, and balanced is not authorized.**

## Negative controls matter

A useful proving ground asks an implementation to reject invalid behavior as well as accept valid behavior.

Current examples include stale or incomplete media-readiness states in the communications lane and a closed-accounting-period correction in the Fund lane. The latter earns `FUND-CLS-001` only after the live evidence shows the closed-date rejection, open-date acceptance, and explicit cleanup reversal.

## Preserve before reducing

Useful evidence bundles preserve the inputs needed to audit the verdict: protocol messages, media datagrams, API requests and responses, implementation identity, source hashes, build identity, transaction IDs, command logs, timestamps, scenario manifests, and reducer outputs.

Reducers operate on the preserved evidence. They do not silently upgrade runtime-local success states into broader interoperability, authorization, accounting, or conformance claims.

## Independent reconciliation

Where the external implementation is itself part of the thing being tested, Baudot avoids asking that implementation to grade its own homework.

For the Fund lane, Fineract executes the accounting instruction and returns ledger evidence. Baudot independently calculates the expected synthetic balances and reconciles them against the observed rows. For RTT, the media implementation does not publish terminal readiness; an independent reference observation must support it.

## Claim boundaries are part of the result

A passing controlled scenario may establish that one pinned implementation produced expected behavior under one declared profile. It does not automatically establish protocol conformance, production readiness, provider interoperability, program authorization, financial-statement compliance, or behavior outside that profile.

The claim boundary belongs in the evidence bundle because it tells a later reviewer what the run did **not** prove.
