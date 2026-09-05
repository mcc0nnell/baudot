# ADR-0003: Baudot parent reactor and provider fixtures

- Status: Proposed
- Date: 2026-09-05

## Context

Baudot began as a single Maven/JAIN SIP testkit while its interoperability evidence model matured. The repository now has multiple independent implementation lanes, iTRS mock work, federated-call scenarios, and external provider candidates.

ACE Connect Lite is a particularly useful historical VRS interoperability fixture. Its public MITRE/FCC implementation includes Asterisk-backed call handling and an explicitly emulated VRS-number verification seam. Baudot should be able to exercise that implementation without making ACE-specific behavior part of Baudot's semantic core.

At the same time, the current root `pom.xml` is operational infrastructure. Existing scripts invoke Maven directly from the repository root and several active branches depend on that shape. Converting the root project immediately from a JAR into a `pom`-packaged aggregator would create avoidable churn across active evidence work.

## Decision

Introduce a dedicated Java 21 Maven parent reactor at `parent/pom.xml` and a provider-neutral fixture SPI under `providers/spi`.

The first provider module is `providers/ace-connect-lite`.

```text
parent/                         baudot-parent
  pom.xml
      |
      +-- providers/spi         baudot-provider-spi
      |
      `-- providers/ace-connect-lite
                                baudot-provider-ace-connect-lite
```

The existing root `baudot-testkit` project remains unchanged in this slice. That preserves current `mvn ... exec:java` entry points and avoids rebasing unrelated signaling/media work through a packaging migration.

The parent reactor establishes:

- Java 21 as the target for newly extracted modules;
- common compiler/test plugin versions;
- dependency-management space for future shared libraries; and
- an explicit module boundary for provider fixtures.

Provider modules implement the provider-neutral `ProviderFixture` contract. The contract records implementation identity, source identity, and observable capabilities. A provider fixture is an implementation under test, not a source of normative truth.

## ACE Connect Lite boundary

ACE Connect Lite is modeled as the first historical VRS fixture because the upstream code exposes:

- Asterisk-backed SIP behavior;
- SIP-over-WebSocket/video configuration;
- agent/queue state; and
- a legacy `/vrsverify/` lookup seam described upstream as an emulated VRS check.

Baudot should adapt deterministic iTRS fixtures into that legacy lookup seam rather than modify its iTRS semantic model to match ACE Connect Lite.

The intended topology is:

```text
Baudot scenario
      |
      v
Baudot iTRS model/mock
      |
      v
ACE compatibility adapter
      |
      v
/vrsverify/
      |
      v
ACE Connect Lite / Asterisk
```

Two isolated ACE fixture identities can then represent synthetic Provider A and Provider B for cross-provider test scenarios.

## Evidence and claim boundary

No provider fixture gets verdict authority. Baudot reducers remain responsible for terminal interpretation within each scenario's explicit claim boundary.

A successful ACE fixture run does not establish production VRS interoperability or standards conformance. It establishes only the observations actually preserved and independently reduced by the scenario.

## Consequences

### Positive

- Provider-specific code is kept below a stable Baudot SPI.
- New modules can use Java 21 without breaking the currently operational root testkit.
- ACE Connect Lite can become executable evidence rather than merely historical documentation.
- The same SPI can later host other VRS/provider fixtures without branching Baudot semantics by provider.

### Negative

- The repository temporarily has two Maven entry points: the existing root testkit and `mvn -f parent/pom.xml ...` for extracted modules.
- Shared code remains split until the root testkit is migrated under the parent.

## Follow-up

After active root-level evidence branches settle:

1. migrate the root Java testkit into a child module without changing scenario semantics;
2. place iTRS mocks behind a stable module/API boundary;
3. pin an exact ACE Connect Lite upstream commit;
4. automate two isolated ACE/Asterisk fixture instances; and
5. connect the deterministic iTRS mock to the ACE `/vrsverify/` compatibility adapter.
