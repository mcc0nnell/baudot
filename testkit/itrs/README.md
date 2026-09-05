# iTRS mocks

Deterministic fixtures and mock services for exercising iTRS-derived routing behavior without access to the live TRS Numbering Directory.

The suite models protocol behavior, not production authority. It is intentionally clean-room and contains no credentials, live subscriber data, provider configuration, or copied ACE Direct source.

## Boundary

```text
fixture
  -> mock iTRS adapter
  -> normalized routing observation
  -> Tilden-style route
  -> Baudot signaling probe
```

The mocks exist so Baudot can prove signaling and route-consumption behavior independently of live iTRS infrastructure.

## Covered cases

- direct `E2U+sip` NAPTR result;
- CNAME/alias forwarding before `E2U+sip` resolution;
- multiple NAPTR records with deterministic priority/order selection;
- downstream SIP NAPTR and SRV discovery metadata;
- no route found;
- malformed route data;
- authoritative service unavailable; and
- explicit fixture-driven latency.

## Fixture contract

`fixtures/itrs-resolution-v1.json` is the canonical mock vector set. Each case contains:

- a synthetic NANP number;
- synthetic DNS/ENUM observations;
- an expected logical SIP route or expected failure;
- optional final SIP service-discovery observations; and
- an explanation of the invariant under test.

All domains use `.invalid` and all numbers are synthetic documentation numbers. Nothing in this directory is suitable for production routing.

## Mock HTTP adapter

`ItrsMockServer` exposes a tiny local-only HTTP service:

```text
GET /itrs/v1/query?number=2025550101
```

It returns deterministic JSON for the requested fixture. The HTTP surface is deliberately a test adapter; it is not a claim about the production TRS Numbering Administrator interface.

## Run the fixture matrix

```bash
bash scripts/run-itrs-mocks.sh
```

The runner compiles Baudot, starts the mock on loopback, waits for `/health`, executes all eight smoke cases, and tears the server down. Set `ITRS_MOCK_PORT` to override port `8799`.

Expected final line:

```text
iTRS mock probe: 8/8 PASS
```

## Run the SIP handoff proof

```bash
bash scripts/run-itrs-sip-handoff.sh
```

The handoff probe performs the first executable iTRS-to-Baudot call slice:

```text
2025550101
  -> mock iTRS query
  -> sip:2025550101@vrs-a.example.invalid
  -> JAIN-SIP INVITE
  -> loopback mock VRS peer
  -> 200 OK
  -> ACK
```

The logical SIP URI remains the SIP Request-URI. A separate loose Route header directs the packet to the loopback mock VRS peer. This is deliberate: the authoritative communications route and the immediate transport destination are not collapsed into one value.

The probe succeeds only if it observes all of the following:

- the iTRS mock returns the expected logical SIP URI;
- the mock VRS peer receives the INVITE;
- the INVITE Request-URI still equals the iTRS-derived logical SIP URI;
- the caller receives `200 OK`; and
- the mock VRS peer receives the resulting ACK.

Expected final line:

```text
iTRS -> Baudot -> JAIN-SIP handoff: PASS
```

### What this proves

The handoff trial proves that Baudot can consume an iTRS-derived logical SIP route and establish a standards-shaped SIP transaction through JAIN-SIP while keeping service-discovery transport state separate from the logical Request-URI.

### What this does not prove

It is not a live TRS Numbering Directory test, VRS provider interoperability certification, SIP/SDP media conformance test, emergency-call test, or evidence that any production provider accepts the synthetic signaling. Those belong in later controlled profiles and proving-ground scenarios.

## Architectural rule

The mock suite preserves the same separation as Tilden and Baudot:

> Resolve the logical route first. Connect second.

A fixture may contain host/port discovery observations for testing, but the stable handoff to Baudot is the logical SIP URI whenever one is available.
