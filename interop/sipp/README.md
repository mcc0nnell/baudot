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

The catalog is metadata. Individual cases become runnable only when a live target, preserved wire evidence, and an independent Baudot reducer are attached.

## First live gate: SIPP-HOSTILE-004

The branch makes the re-INVITE glare case executable against a standalone JAIN SIP UAS target.

```text
SIPp establishes dialog
  -> CSeq 2 re-INVITE sent
  -> JAIN target intentionally holds CSeq 2 for 800 ms
  -> SIPp waits 100 ms
  -> CSeq 3 re-INVITE sent on same dialog
  -> CSeq 3 receives 491 Request Pending
  -> CSeq 3 ACK sent
  -> held CSeq 2 receives 200 OK
  -> CSeq 2 ACK sent
  -> Baudot reducer joins SIPp wire trace + JAIN target evidence
```

The target deliberately does **not** publish the terminal glare result. SIPp deliberately does **not** publish it either. `scripts/validate_sipp_reinvite_glare.py` parses preserved SIP message blocks, verifies transaction ordering and response correlation, checks the target-side evidence boundary, and only then emits:

```text
terminalVerdict=RUNNABLE_PASS
status=runnable
rttReady=false
```

That result is narrow: the exact pinned SIPp generator successfully applied one live overlap pressure pattern to the controlled JAIN SIP target and the evidence independently reduced to the expected `491-before-200` ordering. It is not an RTT-readiness or conformance result.

Run the live gate with an exact admitted SIPp executable:

```bash
SIPP_BIN=/path/to/pinned/sipp bash scripts/run-sipp-reinvite-glare.sh
```

CI builds the exact pinned SIPp commit from source before running this gate and preserves both the source-admission bundle and the live glare evidence bundle.

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

The next useful live targets are `BAUDOT-INTEROP-004` delayed/duplicate REFER pressure and the RTT-bearing stale-SDP / signaling-only replacement-leg cases, because those scenarios already separate transaction success from accessibility readiness.

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
- independent RFC 4103/T.140 reduction when media is part of the arm; and
- outer SHA-256 evidence manifest.

A SIPp process exit code is never sufficient to publish `rttReady=true`.

## Claim boundary

This lane does not claim SIPp, SIP, REFER, re-INVITE, SDP, RFC 4103, T.140, PJSIP, Linphone, JAIN SIP, VRS, SBC/NAT, or accessibility conformance.

It establishes a disciplined external stimulus boundary and, for `SIPP-HOSTILE-004`, one controlled live signaling-pressure composition whose terminal result is independently reduced.