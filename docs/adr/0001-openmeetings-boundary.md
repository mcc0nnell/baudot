# ADR-0001: Treat Apache OpenMeetings as prior art, not a runtime dependency

- **Status:** Accepted
- **Date:** 2026-09-05

## Context

Baudot is an independent accessible real-time communications project whose core design principle is behavior before stack choice. Its current SIP vertical slice depends directly on JAIN SIP for signaling while Baudot owns its interoperability vocabulary, test vectors, evidence model, and accessible communications semantics.

Apache OpenMeetings is useful prior art for several adjacent concepts, including room/session lifecycle, participant permissions, media publication rights, SIP integration, admission, moderation, recording, and preflight checks. Those concepts are valuable to Baudot, but OpenMeetings is a complete conferencing application with its own application, persistence, UI, and media architecture.

Making OpenMeetings a platform dependency would couple Baudot's session and evidence model to a broader conferencing stack. Vendoring OpenMeetings wholesale would create the same coupling while also transferring maintenance and security burden into this repository.

## Decision

Baudot will treat Apache OpenMeetings as **upstream prior art and an optional interoperability target, not as a Baudot runtime platform dependency**.

Specifically:

1. **Baudot depends directly on the primitives it needs.** JAIN SIP remains a direct signaling dependency for the current SIP harness rather than being reached through OpenMeetings.
2. **Baudot owns its domain model.** Session, participant, capability, media-topology, admission, activation-policy, and evidence concepts are defined in Baudot terms and tested against Baudot behavior.
3. **OpenMeetings concepts may inform design.** Room/session lifecycle, capability-oriented permissions, controlled activation, preflight checks, and recording/evidence separation may be adapted when they improve Baudot's architecture.
4. **OpenMeetings will not be vendored wholesale.** If a small Apache-2.0 implementation fragment is ever worth reusing, it must be narrowly scoped, retain required provenance and notices, and be independently testable.
5. **OpenMeetings may be integrated through an adapter.** If future interoperability work requires OpenMeetings itself, Baudot should prefer an external service/API boundary or dedicated adapter over importing OpenMeetings internals into the core.

## Consequences

### Positive

- Baudot remains an independent communications and interoperability system rather than an OpenMeetings customization.
- The SIP and accessibility layers can evolve without inheriting conferencing-application assumptions.
- Session and evidence semantics remain portable across VRS, Direct Video, RTT, WebRTC, PSTN/SIP bridges, test-lab scenarios, and future adapters.
- OpenMeetings remains available as a mature source of architectural lessons and as a possible interop target.
- Dependency and attack-surface growth stays bounded to components Baudot actually uses.

### Tradeoffs

- Baudot must implement and maintain its own session abstractions instead of reusing OpenMeetings domain objects.
- Useful OpenMeetings behavior must be evaluated and translated deliberately rather than inherited automatically.
- Any future adapter introduces an explicit compatibility boundary that must be tested and versioned.

## Architectural boundary

```text
                 JAIN SIP
                 /      \
                /        \
       OpenMeetings      Baudot
        prior art          |
                           |
                  accessible real-time
                 communications behavior
```

Not:

```text
Baudot
  |
  v
OpenMeetings
  |
  v
JAIN SIP
```

## Reuse rule

When evaluating OpenMeetings material, use this order of preference:

1. Reuse the **concept** and implement it in Baudot terms.
2. Reuse a **small isolated implementation** only when the value justifies the provenance, testing, and maintenance burden.
3. Avoid importing or vendoring a **whole OpenMeetings module** into Baudot core.

This ADR does not prohibit OpenMeetings interoperability. It defines the dependency boundary so that interoperability does not become architectural ownership.
