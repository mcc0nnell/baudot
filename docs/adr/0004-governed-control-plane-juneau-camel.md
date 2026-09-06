# ADR-0004: Governed control plane via Apache Juneau MCP and Apache Camel

- Status: Proposed
- Date: 2026-09-05
- Decision owners: Baudot maintainers

## Context

Baudot is becoming an executable interoperability layer rather than a single signaling implementation. Its current architecture already separates routing decisions, signaling observations, media observations, independent semantic reduction, and terminal accessibility verdicts.

Recent work introduces additional application and execution surfaces:

- Tilden selects and explains a route, while Baudot executes and observes that route;
- Zoom and Microsoft Teams can contribute application/media observations without becoming semantic authority;
- MCP can expose communications capabilities to agentic clients; and
- an external control plane can provide authorization, approval, policy, session state, and audit records.

A control plane is useful, but it must not collapse Baudot's evidence boundaries.

The central invariant remains:

```text
request
!= authorization
!= execution
!= observation
!= accessibility readiness
```

The control plane may authorize and invoke work. It may not manufacture a Baudot semantic verdict from successful orchestration.

Atlas UI 3 is a useful public design donor because it combines MCP integration, access control, tool approval, auditable workflows, and agentic execution. However, importing Atlas as a required Baudot runtime would couple Baudot to a large Python/React application and its dependency graph. The useful architectural ideas can be expressed through neutral contracts instead.

Apache Juneau and Apache Camel provide a more Apache-native path:

- Apache Juneau provides first-party MCP server and client modules with typed, revision-bound protocol models over JSON-RPC, while retaining revision-neutral server/client cores.
- Apache Camel provides routing, Enterprise Integration Patterns, connectors, policy seams, error handling, correlation, observability, and its own MCP integration surface.

The combination allows MCP protocol handling and workflow orchestration to remain distinct concerns.

## Decision

Baudot will define a **governed execution boundary** whose protocol and orchestration implementations remain replaceable.

The preferred Apache-native reference architecture is:

```text
MCP host / agent / operator
          |
          v
Apache Juneau MCP boundary
  protocol revision / JSON-RPC
  typed tools and resources
  auth / trace propagation
          |
          v
Apache Camel control plane
  authorization / approval
  routing / orchestration
  retry / timeout / policy
  connector execution
  audit / correlation
          |
          +------------------+
          |                  |
          v                  v
       Tilden              Baudot
   route selection     execution/evidence
```

### 1. Baudot owns the governed-execution contract

Baudot will define implementation-neutral request and receipt contracts.

The initial vocabulary should distinguish at least:

```text
ExecutionRequest
AuthorizationReceipt
ExecutionReceipt
ObservationReference
```

A request identifies the requested operation and evidence requirements. An authorization receipt records whether a policy authority permitted the requested action. An execution receipt records what executor attempted and what it returned. Observation references bind control-plane execution to separately preserved Baudot evidence.

No Atlas-, Camel-, Juneau-, Teams-, Zoom-, or provider-specific object becomes the canonical Baudot contract.

A minimal conceptual shape is:

```text
ExecutionRequest
  correlationId
  operation
  requestedCapabilities
  policyContext
  evidenceRequirements

AuthorizationReceipt
  correlationId
  authority
  decision
  decisionTime
  policyReference

ExecutionReceipt
  correlationId
  executor
  startedAt
  completedAt
  resultClass
  evidenceRefs
```

The exact committed schema will be versioned separately from this ADR.

### 2. Apache Juneau is the preferred MCP protocol boundary

Juneau will be evaluated as the preferred reference implementation for the MCP-facing protocol layer.

Its role is deliberately narrow:

- decode and encode the supported MCP/JSON-RPC revision;
- expose typed Baudot/Tilden control-plane tools and resources;
- preserve protocol metadata and correlation identifiers;
- participate in authentication and trace propagation; and
- convert MCP calls into the neutral governed-execution contract.

Juneau does not decide whether a call is accessible, whether a route was correct, or whether media was usable.

Juneau's revision-neutral core plus dated MCP adapters is attractive because Baudot should not silently reinterpret a future MCP protocol revision as equivalent to an older one.

### 3. Apache Camel is the preferred orchestration and policy engine

Camel sits behind the MCP boundary and owns workflow execution concerns.

Camel may:

- evaluate authorization and approval policies;
- route an accepted request to Tilden, Baudot, or an external adapter;
- perform bounded retries and timeout handling;
- execute connector-specific calls;
- propagate correlation IDs;
- emit operational telemetry; and
- create control-plane receipts.

Camel does not own Baudot's terminal semantic or accessibility verdict.

The expected composition is:

```text
MCP tool call
    -> ExecutionRequest
    -> authorization policy
    -> AuthorizationReceipt
    -> Camel route
    -> external action
    -> ExecutionReceipt
    -> Baudot evidence references
    -> independent Baudot reducer
```

### 4. Camel MCP support remains a valid alternate adapter

Camel 4.22 includes an MCP server capable of exposing Camel `ai-tool` routes as MCP tools over streamable HTTP.

That capability is useful and should remain interoperable with the same neutral contracts. However, the initial architecture will not make Camel route definitions the canonical MCP protocol model.

The preferred layering is:

```text
Juneau MCP
    -> neutral Baudot execution contract
    -> Camel orchestration
```

A direct Camel MCP adapter may later prove simpler for some deployments:

```text
Camel MCP
    -> same neutral Baudot execution contract
    -> Camel orchestration
```

Both paths must produce equivalent governed-execution facts. No terminal Baudot reducer may branch on which MCP implementation was used.

### 5. Tilden retains route-selection authority

The control plane may request a route selection from Tilden and may execute the returned route, but it does not replace Tilden's selection authority.

The authority chain remains:

```text
Tilden
  owns why a route was selected

Camel / control plane
  owns whether execution was authorized and attempted

Baudot
  owns signaling/media observations and evidence reduction
```

A Camel route may not promote an eligible-but-unselected route after failure unless a new Tilden selection explicitly authorizes that route.

This preserves the existing Tilden reselection boundary.

### 6. Atlas UI 3 is a design donor and interoperability specimen

Atlas UI 3 will not be a required Baudot build-time or runtime dependency.

Its public behavior is useful as donor material for control-plane scenarios such as:

- tool discovery;
- requested tool execution;
- human/tool approval;
- group or policy authorization;
- auditable execution;
- session correlation; and
- MCP server integration.

Those behaviors should be converted into provider-neutral test questions rather than copied as Atlas-specific semantics.

The donor rule is:

```text
Atlas behavior
    -> control-plane question
    -> neutral Baudot contract
    -> Juneau/Camel reference implementation
    -> preserved execution evidence
```

Atlas may later be tested as an independent MCP/control-plane participant against the same contracts.

### 7. The control plane never becomes accessibility verdict authority

Successful authorization, execution, or tool completion is insufficient to establish a usable communications session.

Examples:

```text
MCP tool accepted=true
!= operation authorized

operation authorized=true
!= operation executed

operation executed=true
!= target observed

media observed=true
!= media usable

transcript observed=true
!= T.140 semantics

call connected=true
!= rttReady
```

The terminal accessibility verdict remains with Baudot reducers/reference code under explicit claim boundaries.

### 8. Build and runtime independence are requirements

The Baudot core and normative testkit must remain buildable and runnable without:

- Apache Juneau;
- Apache Camel;
- Atlas UI 3;
- Microsoft Teams credentials;
- Zoom credentials; or
- any production provider/network access.

A deterministic mock control-plane implementation must be sufficient for normative CI and contract validation.

Juneau and Camel reference integrations are qualification lanes, not prerequisites for expressing Baudot semantics.

## Evidence roles

| Participant | Role | May define Baudot terminal verdict? |
| --- | --- | --- |
| Baudot reducers/reference code | communications evidence reduction and terminal verdict | Yes, within explicit claim boundaries |
| Tilden | identity/routing selection and explanation | No |
| Apache Juneau MCP | MCP protocol boundary | No |
| Apache Camel | orchestration, policy, connector execution, control-plane receipts | No |
| Atlas UI 3 | design donor / independent integration specimen | No |
| Teams / Zoom / VRS / SIP endpoints | external implementation observations | No |

## Consequences

### Positive

- MCP protocol handling is separated from orchestration semantics.
- Camel can express complex execution flows without redefining Baudot's call model.
- Tilden's selection authority remains intact.
- Atlas contributes useful design evidence without becoming a dependency.
- The architecture remains replaceable at both the MCP and orchestration layers.
- Normative Baudot tests remain deterministic and independent of external SaaS credentials.
- The design is compatible with an Apache-style dependency and release boundary.

### Costs

- Two Apache layers (Juneau and Camel) create more integration work than using a single framework end-to-end.
- The neutral execution contract must be maintained independently from both implementations.
- Authorization policy semantics need explicit versioning rather than being left implicit in route code.
- Correlation and evidence references must survive across MCP, Camel, Tilden, and Baudot boundaries.

## Rejected alternatives

### Import Atlas UI 3 as the Baudot control plane

Rejected as the default architecture. Atlas is useful and permissively licensed, but making it required would introduce unnecessary application/runtime coupling and weaken implementation neutrality.

### Put MCP protocol semantics directly into Baudot reducers

Rejected. Protocol transport and semantic/accessibility verdict authority are different concerns.

### Let Camel route success define operation success

Rejected. Camel can prove that a route executed according to its orchestration rules. It cannot by itself prove that the communications result was usable.

### Let the control plane choose fallback providers after a failed route

Rejected. Tilden retains route-selection authority. Recovery requires a new Tilden selection when selection semantics require one.

### Make Juneau mandatory for all Baudot execution

Rejected. Juneau is the preferred reference MCP protocol boundary, not part of the normative communications semantics.

## Follow-up

1. Define `ExecutionRequest`, `AuthorizationReceipt`, `ExecutionReceipt`, and `ObservationReference` as versioned Baudot testkit contracts.
2. Add a deterministic mock control-plane reducer proving `request != authorization != execution`.
3. Implement a minimal Juneau MCP adapter that emits the neutral request contract.
4. Implement a minimal Camel route that consumes the contract, applies an explicit authorization policy, and emits receipts.
5. Bind receipt `correlationId` values to existing Tilden/Baudot evidence IDs without copying unnecessary private request state.
6. Add negative tests for unauthorized execution, policy timeout, duplicate request, stale authorization, execution without observation, and observation without accessibility readiness.
7. Convert selected Atlas UI 3 behaviors into donor scenarios without importing Atlas implementation code.
8. Keep direct Camel MCP as an alternate implementation lane and require equivalent governed-execution facts.

## Claim boundary

This ADR defines an architecture and authority split. It does not establish Apache Juneau MCP conformance, Apache Camel MCP conformance, authorization correctness, production security posture, Teams/Zoom/VRS interoperability, SIP/RTP/RFC 4103/T.140 conformance, or end-to-end accessibility readiness.
