# ADR-0006: Apache-native TRS business stack

- Status: Proposed
- Date: 2026-09-05
- Decision owners: Baudot maintainers
- Parent: ADR-0005

## Context

ADR-0005 decomposes Atlas-style control-plane capabilities into narrow Apache roles. Baudot also needs a similarly explicit decomposition for the **business systems around a TRS service**: users, policy, equipment distribution, call records, Fund accounting, document retrieval, and cross-system workflows.

The architecture should model those domains without turning any infrastructure product into program authority.

The governing rule is:

```text
identity
!= policy authorization
!= protocol validity
!= service eligibility
!= call observation
!= compensability
!= ledger posting
```

Each Apache component therefore owns a bounded implementation concern while Baudot preserves the authority and evidence boundaries between them.

## Decision

The preferred Apache-native TRS business composition is:

```text
                       Apache Shiro
                     users / sessions
                            |
                            v
                       Apache Ranger
                  centralized policy decision
                            |
                            v
                       Apache Camel
                 workflow / integration plane
              /             |              \
             /              |               \
            v               v                v
      Apache OFBiz      Apache Kafka    Apache Fineract
       equipment        CDR/events        TRS Fund
       distribution       spine             ledger

              documents / evidence corpus
                   Tika -> Solr
```

Juneau MCP and APISIX may expose or protect these capabilities at the control-plane/API edge as defined by ADR-0005, but they do not change the business-domain ownership described here.

## 1. Apache Shiro owns application users and sessions

Shiro is the preferred in-process application security framework for authenticated operator, provider, administrator, and service-account identities where Java application services require it.

Its responsibilities may include:

- authentication;
- session management;
- subject identity;
- roles and coarse application permissions; and
- cryptographic support.

Shiro answers questions such as:

```text
who is the current authenticated subject?
which application roles does that subject hold?
is this session still valid?
```

Shiro does **not** own the full TRS policy model.

```text
Shiro-authenticated user
!= authorized iTRS operation
!= subscriber eligibility
!= provider certification
```

## 2. Apache Ranger owns centralized policy decisions

Ranger is the preferred policy decision point for resource- and context-aware authorization across Baudot business services.

A Baudot deployment may define Ranger service definitions for domain resources such as:

```text
provider
subscriber
telephone-number
registration
routing-record
call
cdr
device
shipment
claim
fund-account
```

and access types such as:

```text
query
create
update
assign
route
originate
terminate
read-cdr
fulfill
submit-claim
adjust
reconcile
audit
```

The application supplies the authenticated subject, requested resource, requested access, and relevant request context to Ranger. The application remains responsible for enforcing Ranger's returned decision.

### iTRS policy boundary

Ranger may be used to authorize iTRS-facing operations.

For example:

```text
Shiro-authenticated provider operator
        -> iTRS QUERY_SUBSCRIBER request
        -> Ranger policy decision
        -> Baudot/iTRS service enforces allow/deny
        -> resulting operation/event preserved separately
```

Ranger does **not** validate the iTRS protocol itself. It does not determine whether a message is schema-valid, whether a state transition is protocol-correct, whether routing data is true, or whether a provider is entitled to compensation.

```text
Ranger ALLOW
!= valid iTRS message
!= correct route
!= compensable call
```

## 3. Apache OFBiz owns equipment-distribution operations

OFBiz is the preferred reference business application for TRS equipment-distribution workflows because its existing ERP capabilities include product/catalog management, order management, warehousing, inventory, shipment handling, receiving, and returns.

For Baudot's synthetic TRS business profile, OFBiz may model:

- device catalog and SKUs;
- serialized and non-serialized inventory;
- warehouses and stock locations;
- fulfillment orders;
- pick/pack/ship state;
- shipment tracking references;
- returns and replacement devices;
- vendor/supplier relationships; and
- inventory reconciliation.

OFBiz executes fulfillment state after an eligibility/authorization decision exists. It does not create that authority.

```text
inventory available
!= subscriber eligible

shipment completed
!= program eligibility proven
```

## 4. Apache Kafka owns the CDR/event spine

Kafka is the preferred durable event-streaming backbone for call detail records and related service events when the deployment requires multi-consumer publication, durable retention, replay, or stream processing.

Candidate event families include:

```text
CallAttempted
CallConnected
CallEnded
CDRRecorded
RouteSelected
ProviderObserved
ClaimCandidateProduced
PolicyDecisionRecorded
EquipmentFulfilled
FundPostingObserved
```

The event contracts remain versioned Baudot contracts. Kafka is the transport and durable event spine, not the semantic authority for the records it carries.

For CDRs specifically:

```text
CDR persisted
!= call independently verified
!= minutes compensable
!= claim approved
```

A Fund workflow may consume CDR-derived evidence, but compensation requires a separate business-policy decision before any Fineract posting exists.

## 5. Apache Fineract owns the synthetic TRS Fund ledger

Fineract is the preferred reference financial-state implementation for the synthetic TRS Fund plane already established by the Baudot Fund proving ground.

Its role is bounded to financial state such as:

- chart of accounts;
- general ledger;
- journal entries;
- receivables and payables represented by the canonical Baudot journal contract;
- adjustments and reversals; and
- reconciliation/read-back evidence.

Fineract does not own:

- provider certification;
- call compensability;
- reimbursement-rate authority;
- contributor-liability authority;
- claim approval; or
- payment authorization.

```text
balanced journal entry
!= authorized claim
!= valid contributor assessment
```

## 6. Apache Tika and Solr own the document/search layer

Tika and Solr retain the document roles established by ADR-0005:

```text
source documents
      -> Tika extraction
      -> normalized text + metadata
      -> Solr index
      -> operator/agent retrieval
```

Candidate corpora include public rules, orders, provider guidance, equipment documentation, contracts, test evidence, and other explicitly permitted source material.

Tika extracts. Solr retrieves. Neither decides that retrieved content is current, authoritative, or sufficient evidence for a business action.

## 7. Apache Camel owns cross-domain workflow and integration

Camel connects the bounded domain services without becoming the source of truth for any one of them.

Examples include:

```text
Shiro identity
   -> Ranger policy
   -> authorized iTRS request
   -> Kafka event

eligibility decision
   -> OFBiz fulfillment
   -> shipment event
   -> Kafka

call/CDR evidence
   -> business-policy decision
   -> approved claim
   -> Fineract journal intent
   -> reconciliation evidence
```

Camel may perform routing, transformation, correlation, retries, idempotency, timeouts, and connector invocation. A successful Camel route is only workflow evidence.

## Authority matrix

| Concern | Preferred Apache role | Explicit non-authority |
| --- | --- | --- |
| Users, login, sessions | Shiro | Does not define TRS policy or eligibility |
| Resource/action policy | Ranger | Does not validate iTRS semantics or compensability |
| Equipment distribution | OFBiz | Does not establish subscriber eligibility |
| CDR/event transport and replay | Kafka | Does not establish call truth or compensable minutes |
| TRS Fund accounting | Fineract | Does not approve claims, rates, or payments |
| Document extraction | Tika | Does not establish source authority |
| Retrieval/search | Solr | Does not turn retrieved text into evidence authority |
| Integration/workflow | Camel | Does not gain semantic authority from successful execution |
| Route selection | Tilden | Does not create Baudot terminal evidence verdicts |
| Communications evidence | Baudot reducers/reference code | Does not independently create business authorization or Fund policy |

## Canonical TRS business flow

The resulting business architecture can be summarized as four primary operational domains:

```text
identity -> equipment -> calls -> money
   |           |           |        |
 Shiro       OFBiz       Kafka   Fineract
   |
 Ranger policy spans authorized actions across domains
   |
 Camel connects the workflows
```

That summary is intentionally simple. The boundaries remain explicit:

```text
identity != eligibility
equipment fulfillment != eligibility
CDR != compensability
ledger posting != authorization
```

## Build boundary

No component in this ADR becomes a mandatory dependency of the normative Baudot communications testkit merely because it is selected for a business deployment profile.

The core must retain deterministic fixtures sufficient to test the contracts at each boundary without requiring production identities, live subscriber data, real CDRs, production equipment orders, production Fund transactions, or production iTRS access.

## Consequences

### Positive

- Business concerns map to existing Apache projects with narrow, understandable roles.
- iTRS authorization policy can be centralized without embedding provider-specific policy branches throughout protocol code.
- Equipment distribution is modeled as a real inventory/fulfillment problem instead of bespoke CRUD.
- CDRs gain a durable replayable event path without becoming claim authority.
- Fineract remains a financial kernel rather than being stretched into the entire TRS business application.
- Shiro user/session concerns remain distinct from Ranger's centralized policy model.
- Every domain can be mocked independently in the synthetic end-to-end TRS laboratory.

### Costs

- Identity and policy propagation must be explicit between Shiro, Ranger, Camel, and downstream services.
- Ranger service definitions become important versioned policy integration artifacts.
- Event schemas require governance so Kafka topics do not become accidental semantic contracts.
- OFBiz and Fineract overlap in generic ERP/accounting capabilities, so Baudot must preserve the chosen ownership boundary: OFBiz for equipment/fulfillment operations; Fineract for the synthetic TRS Fund ledger.
- Cross-domain reconciliation requires stable correlation identifiers and preserved receipts.

## Follow-up

1. Keep ADR-0005 as the Atlas/control-plane decomposition and land this ADR beside it.
2. Define the first synthetic Ranger service definition for iTRS resources/actions.
3. Bind Shiro subject identity into Ranger authorization fixtures without making Shiro the policy authority.
4. Define a Kafka CDR envelope that preserves provenance, correlation IDs, and source observation references.
5. Create an OFBiz equipment-distribution proving slice using only synthetic subscribers, devices, inventory, orders, shipments, and returns.
6. Continue the existing Fineract Fund lane independently and join it to CDR-derived synthetic claim candidates only through an explicit authorization boundary.
7. Add a Tika -> Solr document/evidence profile only where permitted source corpora materially improve operator or agent retrieval.
8. Use Camel to compose the cross-domain scenario while preserving independent evidence and authority at every transition.

## Source observations for this decision

Current ASF project documentation supports these bounded role assignments:

- Apache Shiro describes authentication, authorization, cryptography, and session management as its application-security core: <https://shiro.apache.org/>.
- Apache Ranger's application-integration guidance describes centralized policy-based authorization using application-defined resources/access types, user/resource/request context, plugin or PDP APIs, and application-side enforcement: <https://ranger.apache.org/blogs/integrating_applications.html>.
- Apache OFBiz describes its business suite as including CRM/order management, warehousing and inventory, supply-chain fulfillment, shipment handling, receiving, and returns: <https://ofbiz.apache.org/> and <https://ofbiz.apache.org/business-users.html>.
- Apache Kafka describes durable event streaming, storage, processing, replay, and routing of event streams: <https://kafka.apache.org/intro/>.
- Apache Fineract exposes chart-of-accounts and general-ledger capabilities through its platform/API: <https://fineract.apache.org/docs/stable/>.
- Apache Tika and Solr retain the extraction and retrieval roles documented in ADR-0005.

These observations identify suitable implementation roles. They do not establish that any component is production-ready for a TRS deployment, that any proprietary TRS interface is implemented, or that any business-policy decision is delegated to an infrastructure component.