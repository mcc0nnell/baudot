# ADR-0001: Interoperability ensemble and external implementation oracles

- Status: Accepted
- Date: 2026-09-05
- Decision owners: Baudot maintainers

## Context

Baudot exists to determine whether an accessible real-time communications session is actually usable, not merely whether its signaling completed successfully.

The current testkit already separates SIP state, media state, SDP freshness, target identity, continuity, and real-time text readiness. `BAUDOT-INTEROP-003` proves that a successful SIP renegotiation is not the same fact as usable RTT after renegotiation. `BAUDOT-INTEROP-004` extends that rule across a REFER handoff: REFER acceptance, NOTIFY success, and replacement-dialog establishment do not by themselves establish accessibility readiness.

The next proof threshold requires execution across more than one SIP implementation. Adding another copy of the same stack would increase coverage but would not provide strong implementation independence.

Three external systems are particularly useful:

1. **JAIN SIP** is already Baudot's primary glass-box signaling instrument. It provides explicit transaction/dialog objects, predictable message construction, and a good surface for preserving raw evidence.
2. **Elixip** provides a fully native Elixir SIP stack, a finite-state scenario language (FSL), in-dialog REFER/NOTIFY primitives, B2BUA behavior, media negotiation, and Total Conversation work including T.140/T.140RED. This makes it a materially independent SIP and call-state implementation.
3. **Apache OpenMeetings** provides a real Apache integration specimen built around JAIN SIP, Asterisk, and Kurento. Its current SIP integration also exposes useful assumptions and gaps that can be tested as interoperability behavior rather than copied into Baudot.

ACE Direct remains valuable as a historical donor corpus: production workarounds identify interoperability questions, but donor code does not define Baudot's expected behavior.

Elixip is licensed under BSL 1.1 with project-specific additional-use terms and a scenario exemption. Its scenarios may be independently licensed, but importing Elixip implementation code into Baudot would weaken both licensing clarity and the independence of the test result.

## Decision

Baudot will use an **interoperability ensemble** in which implementations have explicit evidence roles and remain replaceable.

### 1. JAIN SIP remains the primary glass-box signaling instrument

Baudot will continue to use JAIN SIP in its in-repository executable harnesses where direct access to SIP transactions, dialogs, headers, request identity, response correlation, and timing is useful.

JAIN SIP is an instrument, not the definition of correctness. A behavior is not considered proven merely because two JAIN-SIP-based applications agree.

### 2. Elixip is an external independent implementation oracle

Elixip will be integrated as an **externally installed interoperability participant**, not as a Maven dependency, vendored library, submodule, or copied implementation.

Baudot may maintain FSL scenario files and adapters that drive Elixip. Those scenario artifacts remain Baudot-owned evidence inputs and must not require Elixip source code to be copied into the Baudot repository.

Elixip results are observations from an independent implementation. They do not override Baudot's normative vectors or reducers.

The first target is `BAUDOT-INTEROP-004` in both directions:

```text
JAIN SIP -> Elixip
Elixip -> JAIN SIP
```

Each direction must preserve the same facts already required by the provider-neutral reducer:

```text
original dialog identity
REFER request identity
Refer-To target identity
REFER response
NOTIFY progression and terminal status
replacement dialog identity
replacement target correlation
RTT negotiation
first independently validated T.140 character
old-leg teardown ordering
terminal readiness verdict
```

Provider or implementation names remain configuration. Reducer semantics do not change for Elixip.

### 3. Apache OpenMeetings is an integration specimen, not a Baudot dependency

OpenMeetings will be treated as a real-world Apache SIP/media integration that Baudot can test from the outside or reproduce in a bounded lab.

Its value is different from Elixip's:

- Elixip supplies implementation independence.
- OpenMeetings supplies integration realism and historically accumulated assumptions across JAIN SIP, Asterisk, Kurento, WebSocket SIP, and browser media.

OpenMeetings behavior may become scenario donor material when a failure condition can be stated independently.

For example, current OpenMeetings code advertises `NOTIFY,REFER` in `Allow`, while its SIP request processor presently has explicit incoming handling for OPTIONS and BYE. That is a useful test target, not evidence that OpenMeetings is defective and not a reason to copy its implementation.

### 4. ACE Direct remains a donor, not a runtime

ACE Direct production workarounds continue to motivate scenarios such as re-INVITE correlation, SDP freshness, and REFER continuity.

The donor rule remains:

```text
historical behavior or workaround
        -> interoperability question
        -> provider-neutral scenario
        -> controlled execution
        -> preserved evidence
        -> bounded verdict
```

No donor implementation supplies the expected verdict by itself.

### 5. Wire evidence remains authoritative over implementation claims

Each implementation may emit its own internal state, logs, and scenario result, but Baudot will preserve externally observable evidence wherever practical.

For SIP and media scenarios this includes, as applicable:

- raw SIP requests and responses;
- Call-ID, tags, CSeq, Via branch, and transaction/dialog identifiers;
- raw SDP and hashes;
- raw RTP/RFC 4103 datagrams;
- Wiretap captures;
- chronological readiness observations;
- independent reference reductions; and
- terminal scenario evidence.

An implementation saying "transfer succeeded" is an observation. It is not the terminal accessibility verdict.

### 6. Licensing boundaries are architecture boundaries

Baudot will not make Elixip a required build-time or runtime dependency.

The supported integration boundary is process/network/scenario level. FSL scenario files may be maintained by Baudot where permitted by Elixip's scenario exemption, but Elixip implementation code will not be copied or linked into Baudot merely to make tests convenient.

This boundary is also technically desirable: an oracle that shares implementation code with the system under test is a weaker oracle.

## Evidence roles

| Participant | Role | May define Baudot verdict? |
| --- | --- | --- |
| Baudot reducers/reference code | Evidence reduction and terminal verdict | Yes, within explicit claim boundaries |
| JAIN SIP harness | Glass-box SIP instrument | No |
| Elixip / elixipp / FSL runtime | Independent SIP and call-state implementation | No |
| Apache OpenMeetings ensemble | Integration specimen and scenario donor | No |
| ACE Direct | Historical production donor corpus | No |
| Wiretap | External packet/evidence capture | No; supplies evidence |
| Real VRS/provider endpoints | Production-representative participants | No; supplies observations |

## Consequences

### Positive

- `BAUDOT-INTEROP-004` can satisfy its multi-implementation requirement without changing reducer semantics.
- The proving ground gains genuine implementation diversity rather than another wrapper around JAIN SIP.
- Real providers can be added later as configuration/adapters around the same evidence contract.
- Elixip's Total Conversation and RTT work can be exercised without coupling Baudot's license or build to Elixip.
- OpenMeetings becomes useful as an Apache interoperability specimen without forcing Baudot to inherit its architecture.
- Failures remain portable: an Elixip/OpenMeetings/provider disagreement becomes a new evidence case, not an implementation-specific special case.

### Costs

- External-oracle lanes require process orchestration, version pinning, and environment manifests.
- Baudot must distinguish "implementation disagrees" from "standards requirement violated" and avoid majority-vote semantics.
- Some scenarios will require heavier lab infrastructure than the current loopback JAIN SIP probes.
- OpenMeetings and Elixip integrations may evolve independently, so evidence bundles must record exact versions/commits.

## Rejected alternatives

### Replace JAIN SIP with Elixip

Rejected. JAIN SIP is already a strong glass-box instrument and has produced useful executable evidence. Elixip is more valuable precisely because it is independent.

### Vendor or link Elixip into Baudot

Rejected. It creates licensing and maintenance coupling and weakens implementation independence.

### Treat OpenMeetings as the second independent SIP implementation

Rejected. OpenMeetings is highly valuable, but its SIP layer is itself JAIN-SIP-based. It is an independent integration, not an independent SIP stack.

### Define interoperability by successful SIP status codes

Rejected. Existing Baudot scenarios already demonstrate the central counterexample: signaling success can coexist with stale SDP, failed RTT readiness, or an unusable replacement leg.

## Follow-up

1. Add a Baudot-owned FSL scenario pack for the `BAUDOT-INTEROP-004` control and signaling-only arms.
2. Add an external Elixip adapter that preserves exact Elixip version/commit and process configuration in the evidence manifest.
3. Execute `JAIN SIP -> Elixip` and `Elixip -> JAIN SIP` REFER handoffs without changing the terminal reducer.
4. Add Wiretap capture around those executions.
5. Record implementation disagreements as evidence first; only create new scenario semantics when the failure condition is independently stated.
6. Add an OpenMeetings lab profile as an integration specimen, beginning with declared REFER/NOTIFY capability and transfer behavior.
7. Do not promote `BAUDOT-INTEROP-004` from `runnable` to `proven` until its existing `requiredBeforeProven` conditions are satisfied.

## Source observations pinned for this decision

- Elixip repository: `neutrino38/elixip`, observed at commit `d5f942768213200576031346099a896fb61bef4f` / release `1.5.1`.
- Elixip FSL exposes `send_REFER(...)` and `send_NOTIFY(...)`; its session/dialog implementation recognizes in-dialog REFER and NOTIFY.
- Elixip media/SDP material includes T.140 and T.140RED / RFC 4103-style text media.
- Elixip license: BSL 1.1 with project-specific Additional Use Grant and explicit scenario exemption; see upstream `LICENSE.md`.
- Apache OpenMeetings observation: `apache/openmeetings` commit `67780b37c9bf3546db7b23035aeaafbf73233c83`; current Maven configuration pins JAIN SIP `1.2.307`.
- OpenMeetings `SipStackProcessor` advertises `ACK,CANCEL,INVITE,MESSAGE,BYE,OPTIONS,INFO,NOTIFY,REFER` while its current incoming request branch explicitly handles OPTIONS and BYE.

These observations motivate the architecture decision. They are not conformance findings about either project.