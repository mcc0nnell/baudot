# ADR-0004: Governed MCP execution via neutral contracts and Apache control-plane components

- Status: Proposed
- Date: 2026-09-05
- Updated: 2026-09-06
- Decision owners: Baudot maintainers

## Context

Baudot is becoming an executable interoperability layer rather than a single signaling implementation. Its architecture already separates route selection, signaling observations, media observations, independent semantic reduction, program-policy decisions, financial posting, and terminal accessibility verdicts.

MCP can expose bounded Baudot capabilities to an operator or agent, but an MCP tool call must not collapse those authority boundaries.

The central invariant is:

```text
request
!= authentication
!= policy authorization
!= execution
!= observation
!= accessibility readiness
```

The business/control architecture has also matured since this ADR was first drafted:

```text
Shiro   -> application actor authentication / session context
Ranger  -> centralized resource/action/context policy decision
APISIX  -> external API edge
Camel   -> request/event orchestration and enforcement workflow
Tilden  -> route selection
Baudot  -> communications execution/evidence and bounded reducers
```

That split means Camel is no longer a second policy authority. Camel may call and enforce Ranger, but Ranger owns the policy decision for protected domain actions.

## Release reality

The architecture distinguishes a preferred protocol design from what can be qualified using released software today.

### Apache Juneau

Apache Juneau has a first-party MCP implementation on its 10.0.0 development line, with revision-neutral MCP cores and dated protocol adapters. As of this ADR update, 10.0.0 remains unreleased `-SNAPSHOT` development; the latest released Juneau line does not provide the MCP runtime assumed by the original draft.

Therefore:

```text
Juneau MCP
= preferred/reference protocol candidate
!= required released runtime today
```

Baudot must not claim a released Juneau MCP integration until an Apache Juneau release containing those modules exists and is pinned by exact release identity.

### Apache Camel

Apache Camel 4.22.0 is a released LTS line and includes preview `camel-ai-tool` and `camel-mcp-server` modules. Camel can expose selected `ai-tool` routes as MCP tools over streamable HTTP. Tool annotation hints are advisory metadata and are not authorization.

Camel 4.22.0 is therefore the first released Apache qualification lane for the neutral MCP tool contracts while Juneau remains a replaceable future/reference adapter.

## Decision

Baudot will define a **governed execution boundary** whose protocol, policy, and orchestration implementations remain separate and replaceable.

The current reference shape is:

```text
MCP host / agent / operator
          |
          v
MCP protocol adapter
  Camel 4.22 released qualification lane
  Juneau future/reference adapter
          |
          v
neutral Baudot tool / ExecutionRequest contract
          |
          v
Shiro-authenticated actor context
          |
          v
Ranger policy decision
          |
          v
Camel orchestration / enforcement
  retry / timeout / correlation
  connector invocation
  receipt creation
          |
          +------------------+
          |                  |
          v                  v
       Tilden              Baudot
   route selection     execution/evidence
```

For read-only fixed evidence tools, the path may omit a domain mutation decision when no protected resource action is requested, but actor/session and access policy remain explicit deployment concerns.

## 1. Baudot owns the governed-execution contracts

No Atlas-, Camel-, Juneau-, Ranger-, Shiro-, Teams-, Zoom-, or provider-specific object becomes canonical Baudot semantics.

The initial neutral vocabulary distinguishes:

```text
ExecutionRequest
AuthorizationReceipt
ExecutionReceipt
ObservationReference
```

A conceptual shape is:

```text
ExecutionRequest
  requestId
  correlationId
  operation
  actorRef
  requestedCapabilities
  resourceRefs
  evidenceRequirements

AuthorizationReceipt
  requestId
  correlationId
  authority
  decision
  decisionTime
  policyReference

ExecutionReceipt
  requestId
  correlationId
  executor
  startedAt
  completedAt
  resultClass
  observationRefs

ObservationReference
  correlationId
  evidenceId
  evidenceType
  sourceRef
  digest
```

The exact schemas are versioned separately from this ADR.

## 2. The first MCP surface is read-only evidence inspection

Implementation issue #92 defines the first bounded tool set:

```text
inspect_dialog
observe_sip_trace
compare_sdp
export_evidence
```

These tools adapt existing evidence/runtime boundaries; they do not recreate SIP, SDP, media, or evidence semantics inside the MCP adapter.

### `inspect_dialog`

Returns normalized dialog/transaction state for a controlled run. JAIN SIP and preserved signaling evidence remain the underlying observation authority.

### `observe_sip_trace`

Returns a bounded structured signaling trace with correlation identifiers and source evidence references.

### `compare_sdp`

Compares preserved offer/answer evidence and reports differences. SDP comparison does not establish negotiated media usability or RTT readiness.

### `export_evidence`

Returns the preserved evidence bundle or references for a controlled run without creating new semantic claims.

The mutation surface remains absent from this first slice.

## 3. Shiro owns application actor/session context

Shiro establishes who the application actor is and whether the actor has an active authenticated session.

```text
Shiro authenticated
!= Ranger authorized
```

Only a minimal actor/session projection may cross the authentication boundary. Subscriber eligibility, TRS identity-verification state, telephone numbers, claim/payment authority, and other domain truth do not belong in Shiro session context.

A remembered principal is not treated as fresh authentication for protected TRS operations.

## 4. Ranger is the policy decision point

For protected resource/action operations, a trusted Baudot service translates the authenticated actor plus requested resource/action/context into a Ranger policy request.

```text
actor + resource + action + context
        -> Ranger
        -> ALLOW / DENY
```

Ranger failure or an ambiguous response fails closed for protected operations.

An explicit Ranger `ALLOW` remains insufficient to establish protocol validity, route correctness, subscriber eligibility, compensability, payment authorization, or accessibility readiness.

## 5. Camel owns orchestration and enforcement workflow

Camel sits behind the neutral contract and owns request/event workflow concerns.

Camel may:

- invoke Ranger and enforce its decision;
- route an accepted request to Tilden, Baudot, or another bounded adapter;
- perform bounded retries and timeout handling;
- execute connector-specific calls;
- propagate opaque correlation identifiers;
- emit technical telemetry; and
- construct execution receipts from observed workflow facts.

Camel may not:

- invent an authorization decision when Ranger is required;
- turn route success into protocol or accessibility truth;
- select a new provider/route when Tilden selection is required;
- turn a CDR into compensability or Fund authority; or
- treat workflow completion as evidence that an external target behaved correctly.

The protected composition is:

```text
MCP tool call
    -> ExecutionRequest
    -> authenticated actor context
    -> Ranger decision
    -> AuthorizationReceipt
    -> Camel route/enforcement
    -> external or Baudot evidence adapter
    -> ExecutionReceipt
    -> ObservationReference(s)
    -> independent Baudot reducer when a semantic verdict is requested
```

## 6. Camel 4.22 is the initial released MCP qualification adapter

Camel 4.22 provides:

```text
camel-ai-tool
camel-mcp-server
```

The MCP server exposes only `ai-tool` routes matching configured tags over streamable HTTP. Baudot must configure an explicit allowlist/tag set; wildcard publication of all tools is not the default profile.

The first qualification lane should expose only the four read-only tools from #92.

MCP annotations such as `readOnlyHint`, `destructiveHint`, and `idempotentHint` are useful client-facing hints, but they are not security decisions. Enforcement remains in the authenticated/policy/orchestration path.

```text
readOnlyHint=true
!= actor authorized
```

## 7. Juneau remains a replaceable protocol adapter, not a prerequisite

When a released Apache Juneau version containing the MCP modules is available, Baudot should qualify it against the same neutral contracts and fixed evidence fixtures.

The required equivalence is:

```text
Camel MCP adapter
        \
         -> same ExecutionRequest / receipts / observations
        /
Juneau MCP adapter
```

No terminal reducer may branch on which MCP implementation produced an equivalent neutral request.

Until that released threshold exists, normative CI must not depend on Juneau 10 snapshot artifacts.

## 8. Tilden retains route-selection authority

The control plane may request a route selection from Tilden and may execute the returned route, but it does not replace Tilden's selection authority.

```text
Tilden
  owns why a route was selected

Ranger
  owns whether the protected requested action is allowed

Camel
  owns whether the authorized workflow was attempted and how it was orchestrated

Baudot
  owns preserved communications observations and bounded evidence reduction
```

A Camel retry may retry the same authorized operation within the contract. It may not silently promote an eligible-but-unselected route after failure when a new Tilden selection is required.

## 9. Atlas UI 3 remains a design donor

Atlas UI 3 is not a required Baudot build-time or runtime dependency.

Its public behavior remains useful donor material for:

- tool discovery;
- requested tool execution;
- human approval UX;
- auditable execution;
- session correlation; and
- MCP integration.

Those behaviors are converted into neutral test questions instead of Atlas-specific runtime semantics.

```text
Atlas behavior
    -> control-plane question
    -> neutral Baudot contract
    -> Apache qualification adapter
    -> preserved execution evidence
```

## 10. Tool completion never becomes accessibility verdict authority

Examples:

```text
MCP tool listed
!= actor authorized

MCP tool accepted
!= policy ALLOW

policy ALLOW
!= operation executed

operation executed
!= target observed

SIP observed
!= dialog established

SDP compared
!= media usable

media observed
!= RTT ready

call connected
!= accessibility ready
```

The terminal accessibility verdict remains with explicit Baudot reducers/reference code under their claim boundaries.

## 11. Build and runtime independence are requirements

The Baudot core and normative testkit must remain buildable and runnable without:

- Apache Juneau;
- Apache Camel;
- Apache Ranger;
- Apache Shiro;
- Atlas UI 3;
- Microsoft Teams credentials;
- Zoom credentials; or
- production provider/network access.

A deterministic mock control-plane implementation is sufficient for normative contract validation.

External Apache integrations are qualification lanes, not prerequisites for expressing Baudot semantics.

## Evidence roles

| Participant | Role | May define Baudot terminal accessibility verdict? |
| --- | --- | --- |
| Baudot reducers/reference code | communications evidence reduction and bounded terminal verdict | Yes, within explicit claim boundaries |
| Tilden | route selection and explanation | No |
| Shiro | application actor/session authentication | No |
| Ranger | protected resource/action/context policy decision | No |
| Camel | orchestration/enforcement, connector invocation, execution receipts | No |
| Camel MCP 4.22 | released MCP qualification adapter | No |
| Juneau MCP | future/reference MCP protocol adapter pending released artifact | No |
| Atlas UI 3 | design donor / independent integration specimen | No |
| Teams / Zoom / VRS / SIP endpoints | external implementation observations | No |

## Consequences

### Positive

- Identity, policy, MCP transport, orchestration, route selection, and communications evidence have separate owners.
- The first tool surface is read-only and deterministic.
- Camel 4.22 provides a released Apache path for immediate MCP qualification.
- Juneau's attractive revision-bound MCP design can be adopted later without blocking current work or making snapshots normative.
- Ranger policies remain centralized instead of being duplicated in Camel routes.
- Tilden selection authority remains intact.
- Normative Baudot tests remain deterministic and external-service independent.

### Costs

- More explicit boundaries create more contracts and adapters.
- Camel MCP is marked preview in 4.22, so production suitability is not implied by qualification success.
- Juneau cannot yet be treated as a released MCP dependency.
- Correlation/evidence references must survive MCP, Shiro, Ranger, Camel, Tilden, and Baudot boundaries.

## Rejected alternatives

### Treat Camel as the policy authority

Rejected. Ranger owns centralized domain-policy decisions. Camel owns orchestration and enforcement workflow.

### Use unreleased Juneau 10 snapshots as a normative dependency

Rejected. Snapshot availability is useful for design evaluation, not a released implementation claim.

### Import Atlas UI 3 as the Baudot control plane

Rejected as the default architecture. Atlas remains donor material rather than a required runtime.

### Put MCP protocol semantics directly into Baudot reducers

Rejected. Protocol transport and communications semantic verdict authority are different concerns.

### Let Camel route success define operation success

Rejected. Camel can establish orchestration facts only.

### Let the control plane choose fallback providers after a failed route

Rejected. Tilden retains route-selection authority.

## Follow-up

1. Implement issue #92 as versioned neutral contracts for `inspect_dialog`, `observe_sip_trace`, `compare_sdp`, and `export_evidence`.
2. Add deterministic fixed-fixture equivalence tests between direct evidence inspection and tool results.
3. Add `ExecutionRequest`, `AuthorizationReceipt`, `ExecutionReceipt`, and `ObservationReference` contracts.
4. Qualify the read-only tools through released Camel 4.22 `camel-ai-tool` + `camel-mcp-server` over streamable HTTP.
5. Require explicit tool tags/allowlisting and read-only/destructive/idempotency hints without treating hints as authorization.
6. Compose protected-operation tests with Shiro subject context and Ranger policy decisions.
7. Add negative tests for denied policy, policy timeout, duplicate request, stale authorization, execution without observation, and observation without accessibility readiness.
8. Qualify a released Juneau MCP adapter against the same contracts when such a release exists.

## Claim boundary

This ADR defines architecture and authority split. It does not establish Apache Camel MCP conformance generally, future Apache Juneau MCP conformance, authorization correctness, production security posture, Teams/Zoom/VRS interoperability, SIP/RTP/RFC 4103/T.140 conformance, regulatory compliance, or end-to-end accessibility readiness.
