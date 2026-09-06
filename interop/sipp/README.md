# SIPp hostile signaling lane

Baudot uses SIPp as an **external hostile signaling stimulus generator**.

SIPp is not a signaling oracle, media oracle, accessibility oracle, or terminal verdict authority. Its job in this lane is to generate controlled SIP transaction ordering, delay, retransmission, loss, timeout, and malformed-message pressure that would be awkward or misleading to encode inside Baudot's glass-box JAIN SIP instrumentation.

## Pinned candidate

```text
repository: SIPp/sipp
commit:     c496186356b9089fc70b311607be4d2853809625
observed:   2026-09-05
role:       hostile SIP stimulus generator
status:     source-admitted for scenario work; not an oracle
```

The pin is exact. A moving branch, fork, dirty checkout, or different commit is not the same candidate profile.

## Why SIPp

At the pinned commit, SIPp's documented XML scenario language exposes the pressure primitives Baudot needs without requiring SIPp to decide whether the resulting accessible session is usable:

- raw `<send>` and `<recv>` SIP message steps;
- UDP retransmission timers with `retrans`;
- deliberate send/receive loss with `lost`;
- explicit millisecond pauses;
- receive timeouts and timeout branches;
- optional receives;
- named transaction correlation through `start_txn`, `response_txn`, and `ack_txn`;
- SDP-ignore behavior useful for stale-media tests; and
- conditional flow control.

`sipp_candidate_admission.py` proves those primitives against the exact clean upstream checkout before the profile is admitted for scenario authoring.

## Boundary

The lane must keep these facts separate:

```text
SIPp emitted a request
!= peer accepted the transaction
!= replacement dialog established
!= negotiated SDP is fresh
!= media path is usable
!= T.140 was observed
!= rttReady
```

SIPp may preserve what it sent and what it received. It must not derive Baudot's semantic or accessibility verdicts.

For RTT-bearing scenarios, terminal readiness remains owned by the independent Baudot RFC 4103/T.140 reducer.

## Initial hostile catalog

`scenario-catalog.json` freezes the first pressure cases:

1. **UDP INVITE retransmission** — exercise duplicate transaction delivery without double-promoting call state.
2. **Delayed REFER NOTIFY** — REFER acceptance must not be confused with final transfer outcome.
3. **Duplicate REFER** — repeated transfer requests must remain independently attributable.
4. **re-INVITE glare** — a later in-dialog INVITE arrives while an earlier one is unresolved.
5. **Stale SDP under 200 OK** — successful signaling must not promote RTT readiness from stale media coordinates.
6. **Malformed RTT SDP** — text-media intent is present but the payload mapping is unusable or ambiguous.
7. **Successful NOTIFY without replacement RTT** — signaling success does not imply accessible replacement-leg readiness.
8. **Premature teardown pressure** — old-leg teardown is attempted before terminal readiness authority exists.

The catalog is metadata, not a claim that all eight cases have already been executed against an independent implementation.

## How this composes with existing Baudot lanes

```text
SIPp hostile stimulus
        |
        v
JAIN SIP / PJSIP / Linphone target
        |
        +--> preserved SIP transaction evidence
        +--> preserved SDP generations
        +--> preserved implementation observations
        |
        v
native or controlled RTT media path
        |
        v
independent Baudot RFC 4103/T.140 reduction
        |
        v
terminal scenario verdict
```

The natural first live targets are `BAUDOT-INTEROP-003` re-INVITE freshness and `BAUDOT-INTEROP-004` REFER/replacement-leg continuity because those scenarios already separate transaction success from RTT readiness.

## Evidence requirements for live execution

A live SIPp arm should preserve at least:

- exact SIPp source/build identity;
- clean checkout status;
- scenario XML and SHA-256;
- complete SIPp command line and transport configuration;
- bounded stdout/stderr and exit status;
- raw sent and received SIP messages;
- Call-ID, tags, CSeq, Via branch, and transaction correlation;
- raw SDP generations and hashes;
- target implementation identity;
- any resulting RTT datagrams;
- independent RFC 4103/T.140 reduction; and
- outer SHA-256 evidence manifest.

A SIPp process exit code is never sufficient to publish `rttReady=true`.

## Claim boundary

This lane does not claim SIPp, SIP, REFER, re-INVITE, SDP, RFC 4103, T.140, PJSIP, Linphone, JAIN SIP, VRS, SBC/NAT, or accessibility conformance.

It establishes that one exact external stimulus implementation exposes the controlled signaling-pressure primitives required to drive Baudot's existing evidence model.