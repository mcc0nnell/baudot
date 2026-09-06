# ADR-0005: Apache-native decomposition of Atlas capabilities

- Status: Proposed
- Date: 2026-09-05
- Decision owners: Baudot maintainers

## Context

ADR-0004 defines the governed control-plane boundary for Baudot using Apache Juneau MCP at the protocol edge and Apache Camel for authorization, policy execution, orchestration, connector invocation, and control-plane receipts.

Atlas UI 3 is useful as a design donor because it combines MCP, multi-model access, tool approvals, access control, RAG, auditability, and operator workflows in one product. That integrated shape is valuable for studying the required capabilities, but importing or recreating Atlas as another monolith would unnecessarily couple Baudot to a second application architecture.

Baudot already has a stronger architectural rule:

```text
request
!= authorization
!= execution
!= observation
!= accessibility readiness
```

The same rule should be applied to the broader platform capabilities around governed AI-assisted communications. No infrastructure component should gain semantic authority merely because it performs routing, authentication, retrieval, observability, or workflow execution.

The Apache ecosystem already provides mature components for most of the infrastructure functions Atlas groups together. The useful architectural question is therefore not "how do we clone Atlas?" but "which capabilities should be delegated to independent Apache components while keeping Baudot small, portable, and evidence-oriented?"

## Decision

Baudot will **not** recreate Atlas UI 3 as a monolithic subsystem.

Instead, Atlas will be treated as a **design donor and interoperability specimen**, and its useful capabilities will be decomposed into explicit, replaceable Apache roles.

The architecture will distinguish a **required control-plane baseline** from **optional deployment profiles**.

## Required control-plane baseline

### 1. Apache Juneau MCP owns the MCP protocol boundary

Juneau MCP is the preferred typed MCP/JSON-RPC protocol implementation for the governed control-plane profile defined by ADR-0004.

Juneau may expose and consume MCP tools, resources, prompts, elicitation, subscriptions, and protocol-level metadata, but it does not define Baudot communication semantics or authorization outcomes.

```text
MCP request received
!= authorized operation
!= executed operation
!= communications observation
```

### 2. Apache Camel owns orchestration and policy execution

Camel is the workflow and integration engine behind the control plane.

Its responsibilities may include:

- authorization and approval routes;
- deterministic state transitions;
- retries, timeouts, circuit breaking, and dead-letter handling;
- connector invocation;
- correlation and idempotency;
- control-plane receipt generation;
- MCP tool exposure where useful;
- propagation of trace and correlation identifiers; and
- composition with Tilden and Baudot.

Camel route success never becomes a Baudot accessibility verdict.

```text
Camel exchange completed
!= endpoint usable
!= T.140 observed
!= rttReady
```

### 3. Apache Shiro owns in-process application security where needed

Shiro is the preferred application-level security framework for Java control-plane services that require:

- authentication;
- authorization;
- subject/role/permission checks;
- session management; and
- cryptographic support.

Shiro is an application security framework, not a complete security architecture. Deployment security still depends on trusted configuration, secure runtime boundaries, credential handling, and surrounding infrastructure.

Shiro authorization decisions may authorize an execution request, but they do not authorize Tilden route selection and do not establish any Baudot semantic result.

## Optional edge and AI-gateway profile

### 4. Apache APISIX may provide API and model-provider gateway functions

APISIX may sit at the external edge when a deployment needs shared API/AI traffic governance.

Its responsibilities may include:

- API authentication and traffic policy;
- LLM provider proxying;
- model-provider routing;
- load balancing;
- retries and fallback;
- token-aware rate limiting;
- prompt policies;
- request transformation;
- observability integration; and
- external RAG gateway plugins where explicitly chosen.

APISIX is **not required** for the normative Baudot testkit or minimal control-plane implementation.

A model response routed successfully through APISIX is an operational fact only.

```text
AI gateway success
!= tool authorization
!= tool execution correctness
!= communications evidence
```

Baudot will not create its own multi-LLM gateway merely to reproduce Atlas's provider abstraction where APISIX or another replaceable gateway can satisfy that deployment concern.

## Optional RAG profile

### 5. Apache Tika owns document extraction

Tika is the preferred content-extraction boundary for document-backed retrieval pipelines.

Its role is to extract text and metadata from heterogeneous files through a common interface.

Tika output is source material, not an assertion that the extracted content is authoritative, current, or correct.

### 6. Apache Solr owns retrieval indexes

Solr is the preferred Apache retrieval engine when a deployment requires document search or RAG.

It may provide:

- lexical search;
- metadata filtering;
- dense-vector indexing and search;
- hybrid retrieval; and
- query-time ranking.

Retrieved text does not become Baudot evidence merely because Solr returned it.

### 7. Apache NiFi may own ingestion lineage and replay

NiFi is an optional ingestion/provenance layer for deployments that need reproducible document and dataflow processing.

Its provenance model is valuable because it can record how a data object moved through a flow, why it was routed, what transformations occurred, and where replay is possible.

NiFi is not required for local development or normative CI.

```text
source artifact
    |
    v
   Tika
 extraction
    |
    v
   NiFi        optional provenance
    |
    v
   Solr
 retrieval index
```

NiFi provenance is processing lineage. It is not a Baudot terminal interoperability verdict.

## Optional observability profile

### 8. Apache SkyWalking may own operational telemetry

SkyWalking is the preferred Apache observability option for deployments requiring distributed tracing, metrics, logs, profiling, and GenAI telemetry.

It may observe:

- APISIX traffic;
- Camel routes;
- MCP calls;
- downstream service calls;
- model/provider latency;
- token usage;
- estimated model cost; and
- correlation across control-plane services.

SkyWalking answers operational questions such as:

```text
what executed?
how long did it take?
where did it fail?
which model was called?
how many tokens were used?
```

Baudot answers a different class of question:

```text
what communications behavior was actually observed?
was the relevant modality independently usable?
what evidence supports that bounded verdict?
```

SkyWalking telemetry therefore remains non-authoritative for Baudot semantic or accessibility readiness decisions.

## Optional event-scale profile

### 9. Apache Kafka may provide durable control-plane event streaming

Kafka may be introduced when a deployment needs durable, scalable publication and replay of control-plane events.

Example events include:

```text
ExecutionRequested
AuthorizationGranted
ExecutionStarted
ToolInvoked
ObservationReceived
ExecutionCompleted
BaudotVerdictProduced
```

Kafka is optional and must not become the canonical definition of those events. The versioned Baudot/control-plane contracts remain authoritative; Kafka is a transport and retention mechanism.

A minimal implementation must remain able to execute deterministically without Kafka.

## Resulting architecture

The preferred composition is:

```text
                    optional edge
                   Apache APISIX
                        |
                        v
                  Apache Juneau MCP
                        |
                        v
                    Apache Camel
              policy / orchestration
                 /        |        \
                /         |         \
             Shiro      Tilden     Baudot
           app security  selection  evidence
                        |
              optional deployment services
                /           |           \
               /            |            \
           RAG profile   telemetry    event scale
          Tika -> Solr   SkyWalking     Kafka
              ^
              |
             NiFi
          optional lineage
```

APISIX, NiFi, SkyWalking, and Kafka are deployment profiles, not required core dependencies.

## Authority boundaries

| Component | Primary role | May define Baudot terminal verdict? |
| --- | --- | --- |
| Apache Juneau MCP | MCP protocol / typed JSON-RPC boundary | No |
| Apache Camel | Policy execution, orchestration, connector invocation, receipts | No |
| Apache Shiro | Application authentication, authorization, sessions, cryptography | No |
| Apache APISIX | API/AI gateway, traffic and provider policy | No |
| Apache Tika | Content extraction | No |
| Apache Solr | Retrieval and vector/lexical search | No |
| Apache NiFi | Ingestion, transformation lineage, replay | No |
| Apache SkyWalking | Operational observability and GenAI telemetry | No |
| Apache Kafka | Optional durable event transport and replay | No |
| Tilden | Route-selection authority | No Baudot verdict authority |
| Baudot reducers/reference code | Communications evidence reduction and bounded terminal verdict | Yes, within explicit claim boundaries |

## Build and release boundary

The normative Baudot core and testkit must remain runnable without:

- APISIX;
- Shiro-backed production identity stores;
- Tika;
- Solr;
- NiFi;
- SkyWalking;
- Kafka;
- Atlas UI 3;
- external model-provider credentials;
- Teams/Zoom credentials; or
- production provider access.

The control-plane contract must have deterministic local fixtures and a mock executor sufficient to prove:

```text
request creation
authorization required
stale authorization rejected
duplicate request correlated
execution independently recorded
observation independently recorded
semantic verdict independently reduced
```

Optional Apache components strengthen a deployment profile; they do not change normative semantics.

## Atlas role

Atlas UI 3 remains useful as a design donor for questions such as:

- how tool approval is presented;
- how MCP tools are discovered and selected;
- how operator permissions are modeled;
- how tool execution is audited;
- how RAG and model providers are configured; and
- how a high-trust operator UI presents agentic workflows.

Those observations may motivate provider-neutral contracts or usability requirements.

Atlas itself will not be required by Baudot's build, runtime, normative tests, or verdict logic.

The donor rule is:

```text
Atlas behavior or design
        -> capability question
        -> Apache/neutral contract
        -> controlled implementation
        -> preserved evidence
```

## UI consequence

Baudot will not initially recreate the full Atlas operator UI.

The first user interface should be thin and evidence-oriented, presenting only the information needed to understand:

- requested operations;
- authorization state;
- execution state;
- source observations;
- evidence references; and
- terminal Baudot verdicts.

Operational tooling supplied by Camel, APISIX, SkyWalking, Solr, NiFi, or Kafka should be used for their respective administration concerns rather than duplicated in Baudot.

A richer accessible operator experience may be built later over the same stable contracts.

## Consequences

### Positive

- Baudot avoids inheriting Atlas as a monolithic dependency.
- Major infrastructure roles align with existing ASF projects and Apache-2.0 governance.
- Each component has a narrow authority boundary.
- Optional infrastructure can scale independently.
- Normative tests remain small and reproducible.
- RAG processing can gain explicit extraction, retrieval, and provenance layers without affecting communications semantics.
- Operational telemetry remains separate from interoperability evidence.
- The architecture remains replaceable: another gateway, retrieval engine, security framework, or event transport can implement the same neutral contracts later.

### Costs

- A composed Apache deployment has more independently operated services than a bundled application such as Atlas.
- Cross-component configuration, identity propagation, trace correlation, and version management require discipline.
- The project must resist allowing infrastructure-specific fields to leak into canonical Baudot contracts.
- Optional profiles need their own integration tests and evidence manifests.
- A dedicated operator UI may eventually still be required for the communications-specific workflow.

## Rejected alternatives

### Import Atlas as a required Baudot dependency

Rejected. Atlas is useful software and a useful donor, but a required dependency would couple Baudot's build and release to Atlas's application architecture and dependency graph.

### Recreate Atlas feature-for-feature inside Baudot

Rejected. Authentication, AI gateway behavior, RAG extraction, retrieval, provenance, telemetry, event streaming, and workflow orchestration are not unique communications semantics and already have mature Apache implementations.

### Put every Apache component in the minimum runtime

Rejected. The result would be another monolith-by-deployment. APISIX, NiFi, SkyWalking, and Kafka remain optional profiles.

### Let APISIX or an LLM provider own tool authorization

Rejected. Provider/model routing and application authorization are different facts. Authorization remains an explicit control-plane event before execution.

### Treat RAG retrieval as evidence authority

Rejected. Tika extraction, Solr retrieval, and NiFi lineage can improve source traceability, but retrieved content still requires explicit source/claim handling.

### Treat SkyWalking traces as interoperability evidence

Rejected. Operational telemetry is invaluable for diagnosis but does not independently validate media semantics or accessibility readiness.

### Treat Kafka persistence as canonical event semantics

Rejected. Kafka stores and transports events; it does not define their meaning.

## Follow-up

1. Land ADR-0004 and this ADR as the architectural baseline.
2. Add versioned control-plane contracts for `ExecutionRequest`, `AuthorizationReceipt`, `ExecutionReceipt`, and `ObservationReference`.
3. Add a deterministic mock executor that requires no optional Apache service.
4. Implement the first Juneau MCP -> Camel route for one harmless Baudot test operation.
5. Add Shiro only when the first real authenticated operator profile exists.
6. Define an APISIX deployment profile for multi-model/API gateway use without making it normative.
7. Define a Tika + Solr RAG profile; add NiFi only when ingestion provenance/replay materially improves the evidence path.
8. Add SkyWalking tracing after correlation identifiers are stable across Juneau, Camel, Tilden, and Baudot.
9. Introduce Kafka only when durable multi-consumer event replay is required.
10. Keep every optional integration behind neutral contracts and verify it can be removed without changing Baudot's semantic reducers.

## Source observations for this decision

The following current Apache project capabilities motivated this decomposition:

- Apache APISIX publishes AI-gateway capabilities for LLM provider proxying, routing, load balancing, retries, fallback, token rate limiting, prompt controls, RAG plugins, security, and observability: <https://apisix.apache.org/ai-gateway/> and <https://apisix.apache.org/plugins/>.
- Apache Shiro describes authentication, authorization, session management, and cryptography as its application-security core: <https://shiro.apache.org/>.
- Apache Tika states that it detects and extracts text and metadata from over a thousand file types through a common interface: <https://tika.apache.org/>.
- Apache Solr supports dense-vector indexing and search in addition to its traditional retrieval model: <https://solr.apache.org/guide/solr/latest/query-guide/dense-vector-search.html>.
- Apache NiFi records searchable data provenance, lineage, routing information, and supports replay within flows: <https://nifi.apache.org/nifi-docs/user-guide.html>.
- Apache SkyWalking provides distributed tracing, metrics, logs, profiling, and GenAI telemetry including token and estimated-cost views: <https://skywalking.apache.org/>.
- Apache Kafka provides durable publication, storage, processing, and replay of event streams: <https://kafka.apache.org/intro/>.

These observations identify suitable infrastructure roles. They do not establish that any component is required for Baudot or that any integration is already implemented.
