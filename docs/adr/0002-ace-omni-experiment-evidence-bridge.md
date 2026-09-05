# ADR-0002: ACE Omni experiment and evidence bridge

- Status: Accepted
- Date: 2026-09-05

## Context

Baudot defines portable accessible real-time communications behavior before binding that behavior to one SIP, WebRTC, gateway, VRS, or application runtime. ACE Omni defines a runtime-independent experiment-control and evidence plane in which a pinned experiment becomes a deterministic run plan, commands are sent through capability-bound adapters, observations are preserved with stable identity, and replay does not rewrite prior evidence.

The two projects intentionally overlap at a seam rather than at an authority boundary.

Baudot already separates scenario intent, execution adapters, observations, assertions, and terminal verdicts. Omni already separates experiment authority from world execution and commands from observations. Re-implementing Omni's run planner or evidence ledger inside Baudot would create two competing experiment authorities. Moving Baudot's accessibility semantics into Omni would make portable behavior dependent on one research instrument.

## Decision

Baudot will expose an **ACE Omni bridge contract** for controlled execution of Baudot scenarios while preserving separate authority.

```text
Baudot scenario / vectors / assertions
              │
              │ portable behavior contract
              ▼
      Omni communications adapter
              │
              │ capability-bound commands
              ▼
      SIP / WebRTC / VRS / gateway world
              │
              │ measured facts
              ▼
        observation input
              │
              ▼
       Omni evidence ledger
              │
              │ replay / export
              ▼
      Baudot terminal reducer
```

The authority boundary is:

```text
Baudot owns what accessible communications behavior means.
Omni owns the identity and sequencing of a controlled experiment run.
Attached runtimes make communications behavior happen.
Observations report what happened.
Baudot reducers decide only the Baudot claim declared by the scenario.
```

No layer may promote its own documentation, command acceptance, or runtime state into a stronger interoperability claim than the preserved observations support.

## Authority split

### Baudot owns

- scenario identity and scenario semantics;
- T.140 and transport-independent accessibility vectors;
- modality/readiness vocabulary;
- scenario assertions and `requiredBeforeProven` conditions;
- claim scope;
- independent terminal reduction for Baudot interoperability claims; and
- the distinction between signaling success, media transport, presentation, and accessibility readiness.

### ACE Omni owns

When Omni is the research runner, Omni owns:

- `ExperimentRun` identity;
- pinned experiment and experiment-version identity;
- configuration version and run seed;
- declared adapters and capabilities;
- deterministic execution-plan sequencing;
- command identity and scheduling;
- authoritative observation-envelope creation/sequencing;
- replay conflict detection;
- evidence-ledger persistence, export, and replay; and
- experiment-level comparison and analysis.

### Attached runtimes own

JAIN SIP, Elixip, browser/WebRTC runtimes, VRS mocks, gateways, Wiretap-routed nodes, and future systems under test own external effects and runtime-local state. They do not own the experiment identity or Baudot's terminal claim semantics.

## Protocol mapping

The first bridge targets ACE Omni Emulytics protocol version 1.

A Baudot execution endpoint is represented to Omni as a `communications` adapter. It may declare additional capabilities only when the attached runtime genuinely implements them.

The mapping is:

| ACE Omni | Baudot meaning |
| --- | --- |
| `ExperimentRun.experimentId` | Baudot scenario identifier or containing experiment identifier |
| `ExperimentRun.experimentVersionId` | immutable/content-bound revision of that scenario or experiment |
| `ExecutionCommand.operation` | requested effect against the attached communications runtime |
| `ExecutionCommand.parameters` | scenario-bound parameters; never an observation |
| observation source | exact runtime, probe, or independent oracle that measured the fact |
| observation payload | one or more Baudot facts plus scenario correlation |
| Omni evidence ledger | authoritative controlled-run history |
| Baudot reducer | independent evaluation of the declared Baudot claim from preserved facts |

The machine-readable companion contract is [`testkit/contracts/omni-emulytics-bridge-v1.json`](../../testkit/contracts/omni-emulytics-bridge-v1.json).

## Observation rule

A command is never proof that an effect occurred.

For example:

```text
command: SEND_REFER
```

must not become:

```text
REFER accepted=true
```

without an observation that independently supports that fact.

Similarly:

```text
replacement dialog established=true
rttNegotiated=true
```

must not become:

```text
rttReady=true
```

unless the Baudot scenario's readiness contract is satisfied. Under the current baseline contract that requires an independently observed first T.140 character in addition to RTT negotiation.

## Observation input and authoritative envelope

Baudot adapters SHOULD submit observation inputs containing stable source identity, observation identity, observation time, scenario correlation, and a JSON payload of measured facts.

When ACE Omni is the runner, the **authoritative Omni `ObservationEnvelope` is created or accepted under Omni's evidence rules**, including canonical payload hashing, replay identity, and conflict detection. Baudot does not claim independent authority over Omni run sequencing or Omni ledger identity.

The Omni replay key is preserved conceptually as:

```text
runId : adapterId : sourceId : observationId
```

An exact retry is idempotent. Reuse of that identity for a different observation time or payload is a conflict, not a second measurement and not a mutation of the first.

## Minimum Baudot observation payload

A Baudot observation submitted through the bridge SHOULD contain:

```json
{
  "baudotScenarioId": "BAUDOT-INTEROP-004",
  "factType": "firstT140CharacterObserved",
  "factValue": true,
  "claimScope": "replacement-leg-rtt-readiness"
}
```

Additional protocol-specific evidence may be carried alongside the fact, but a renderer, dashboard, or attached runtime must not silently widen `claimScope`.

## Portable facts

The bridge is intentionally fact-oriented. Initial portable fact types include:

- `sessionEstablished`;
- `sipProvisionalObserved`;
- `sipDialogEstablished`;
- `referAccepted`;
- `notifyProgressObserved`;
- `replacementDialogEstablished`;
- `iceReady`;
- `audioObserved`;
- `videoObserved`;
- `videoDecoded`;
- `videoRendered`;
- `rttNegotiated`;
- `firstT140CharacterObserved`;
- `rttReady`;
- `oldLegPreserved`; and
- `oldLegReleased`.

Scenario-specific extensions remain allowed. Their semantics belong to the Baudot scenario or vector that declares them.

## Invariants

1. **Commands are not observations.** Requested effects never become evidence by issuance alone.
2. **Experiment authority is singular.** When Omni runs the experiment, Baudot does not create a competing run identity or ledger sequence.
3. **Accessibility semantics remain portable.** Omni does not redefine T.140, RFC 4103, presentation, or readiness semantics.
4. **World execution is external.** SIP stacks, VRS mocks, gateways, network substrates, and browsers perform effects and emit measurements.
5. **Sources remain identifiable.** A JAIN SIP probe, Elixip oracle, browser telemetry source, and Wiretap/network probe do not collapse into an anonymous observation stream.
6. **Replay does not rewrite history.** Stable observation identity plus conflicting content is an error.
7. **Presentation is not authority.** Operator UI, graphs, and projections may explain evidence but cannot create conformance state.
8. **Verdicts stay scoped.** A Baudot reducer decides only the claim explicitly declared by the scenario.
9. **Implementation agreement is evidence, not correctness by vote.** Independent runtimes may strengthen a claim but cannot redefine the normative behavior.

## Standalone Baudot execution

Baudot remains runnable without ACE Omni.

Standalone harnesses may preserve the same correlation fields and evidence facts, but they must not label their records as authoritative Omni run or ledger records unless they were actually produced under the Omni protocol and authority boundary.

This keeps the testkit independently useful while making later Omni ingestion deterministic.

## Consequences

### Positive

- Baudot scenarios become directly usable as controlled ACE Omni research inputs.
- Omni can compare JAIN SIP, Elixip, browser/WebRTC, VRS, gateway, and network conditions without absorbing Baudot semantics.
- Baudot can preserve its independent reducer model while benefiting from Omni's deterministic planning, replay, and evidence ledger.
- Future network-emulation or Sandia-derived components attach as worlds/adapters rather than introducing another experiment authority.
- Evidence from production-like VRS/iTRS experiments can use the same semantic vocabulary as local interoperability probes.

### Costs

- Bridge implementations must preserve two explicit namespaces: Omni run/evidence identity and Baudot scenario/claim identity.
- Observation producers must emit measured facts instead of convenient inferred `connected` states.
- Changes to the ACE Omni Emulytics protocol require versioned bridge updates rather than silent compatibility assumptions.

## Non-goals

This ADR does not:

- vendor ACE Omni into Baudot;
- make ACE Omni a required runtime dependency;
- move Baudot reducers or accessibility semantics into Cloudflare;
- replace JAIN SIP, Elixip, Wiretap, or other proving-ground components;
- claim VRS, iTRS, SIP, RFC 4103, T.140, WebRTC, or gateway conformance; or
- make a scenario `proven` merely because it can execute through Omni.

## Follow-on work

The next implementation slice should be one narrow adapter path:

1. select one existing runnable Baudot scenario;
2. bind it to an Omni `communications` adapter;
3. translate the scenario's requested effects into Omni execution commands;
4. submit source-identified Baudot facts as observation inputs;
5. preserve Omni replay/conflict behavior; and
6. run the existing Baudot reducer against the exported immutable evidence.

`BAUDOT-INTEROP-004` is a strong candidate because its claim boundary already distinguishes REFER acceptance, replacement-dialog establishment, RTT negotiation, observed T.140, old-leg handling, and terminal readiness.