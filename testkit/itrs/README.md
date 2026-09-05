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

## Run it

```bash
bash scripts/run-itrs-mocks.sh
```

The runner compiles Baudot, starts the mock on loopback, waits for `/health`, executes all eight smoke cases, and tears the server down. Set `ITRS_MOCK_PORT` to override port `8799`.

Expected final line:

```text
iTRS mock probe: 8/8 PASS
```

## Architectural rule

The mock suite preserves the same separation as Tilden and Baudot:

> Resolve the logical route first. Connect second.

A fixture may contain host/port discovery observations for testing, but the stable handoff to Baudot is the logical SIP URI whenever one is available.
