---
title: Evidence model
description: How Baudot turns observations into scoped interoperability claims.
---

The evidence model is intentionally stricter than a pass/fail integration test.

## Facts stay source-identified

A SIP stack can report that a dialog confirmed. A network probe can report that a datagram crossed a boundary. A reference parser can classify a T.140 block. Those facts remain attributable to their source.

Implementation agreement is useful evidence, but correctness is not decided by majority vote.

## Readiness is earned

For current RTT handoff scenarios, negotiation alone is insufficient. The terminal reducer can require an independently observed first non-empty T.140 character before publishing readiness.

```text
replacement dialog established = true
RTT negotiated                 = true
first T.140 character observed = false
---------------------------------------
RTT ready                      = false
```

## Preserve before reducing

Useful evidence bundles preserve the inputs needed to audit the verdict: protocol messages, media datagrams, implementation identity, source hashes, command logs, timestamps, and reducer outputs.

Reducers operate on the preserved evidence. They do not silently upgrade runtime-local success states into broader interoperability or conformance claims.

## Claim boundaries are part of the result

A passing controlled scenario may establish that one pinned implementation produced expected behavior under one declared profile. It does not automatically establish protocol conformance, production readiness, provider interoperability, or behavior outside that profile.
