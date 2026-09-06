# iTRS mocks

Deterministic, clean-room fixtures and local services for exercising iTRS-derived routing behavior without access to the live TRS Numbering Directory.

Nothing here is production authority. The suite contains no credentials, live subscriber data, provider configuration, proprietary Neustar/iconectiv schema, or copied ACE Direct source.

## Two proving layers

### v1: resolution and service-discovery vectors

`fixtures/itrs-resolution-v1.json` preserves the original Baudot routing vectors:

- direct `E2U+sip` NAPTR result;
- CNAME/alias forwarding before `E2U+sip` resolution;
- multiple NAPTR records with deterministic priority/order selection;
- downstream SIP NAPTR and SRV discovery metadata;
- no route found;
- malformed route data;
- authoritative service unavailable; and
- explicit fixture-driven latency.

These remain useful as downstream service-discovery observations. They are **not** treated as the persistence schema of the TRS Numbering Directory.

Run:

```bash
bash scripts/run-itrs-mocks.sh
```

Expected final line:

```text
iTRS mock probe: 8/8 PASS
```

### v2: database-shaped CTE model

`fixtures/itrs-db-v2.json` and `ItrsDirectoryRepository` model only relationships established by public FCC rules and the 2024 iTRS Statement of Work:

- TN -> endpoint URI records;
- VRS / IP Relay service type;
- user type;
- default-provider XSPID responsibility;
- URD-valid state;
- NPAC SPID / AltSPID / LastAltSPID porting observations;
- separate provisioning and query views;
- provisioning-to-query replication delay;
- two-number AllCallQuery context;
- unique query transaction IDs; and
- the per-TN URD-valid operation.

The porting transition follows the public SOW invariant: when NPAC AltSPID/LastAltSPID indicates the gaining provider's XSPID, the gaining provider may provision the number; its first provision transfers control and the losing provider loses write access.

The URD seam follows the public SOW invariant that the URD Administrator can create/update per-TN validity state and may create a non-active directory record carrying provider XSPID and service. The provider still cannot make that record query-valid by asserting the URD flag itself.

## Local CTE-style HTTP surface

`ItrsCteMockServer` exposes Baudot-owned test endpoints on loopback:

```text
GET /itrs/v2/all-call-query
PUT /itrs/v2/provision
PUT /itrs/v2/urd-valid
GET /itrs/v2/record
```

The surface is intentionally REST/JSON-shaped because the public SOW expresses that design preference. Exact endpoint names, parameters, and response bodies are **not** claims about the production TRS Numbering Administrator API or the nonpublic iTRS Provisioning/Query Guides.

A compatibility endpoint:

```text
GET /itrs/v1/query?number=...
```

bridges the v2 repository into the existing #40 JAIN-SIP handoff probe. That lets the same persistence/query state machine feed Baudot signaling without duplicating the SIP harness.

## Run the CTE slice

```bash
bash scripts/run-itrs-cte.sh
```

The runner proves:

```text
provider provisioning / URD / NPAC observations
                  |
                  v
          provisioning view
                  |
           replication seam
                  |
                  v
             query view
                  |
          AllCallQuery decision
                  |
           logical SIP URI
                  |
                  v
          JAIN-SIP INVITE
                  |
                  v
        loopback mock VRS peer
```

The repository probe currently covers:

- valid cross-provider VRS routing;
- URD-invalid fail-closed behavior;
- malformed route URI fail-closed behavior;
- non-default-provider provisioning denial;
- gaining-provider provisioning based on synthetic NPAC XSPID evidence;
- provisioning-to-query replication delay;
- losing-provider write revocation after the gaining provider's first provision;
- URD creation of an inactive directory stub; and
- proof that a provider cannot self-assert URD validity.

Expected repository result:

```text
iTRS CTE probe: 8/8 PASS
```

The same run then executes the existing JAIN-SIP handoff and expects:

```text
iTRS -> Baudot -> JAIN-SIP handoff: PASS
```

## Architectural boundary

```text
URD validity ----\
                  \
NPAC porting ------> iTRS directory/query decision -> logical route
                  /                                      |
provider writes -/                                       v
                                                        Tilden
                                                          |
                                                          v
                                             SIP service discovery
                                             NAPTR / SRV / transport
                                                          |
                                                          v
                                                        Baudot
```

> Resolve the logical route first. Connect second.

DNS/ENUM/NAPTR/SRV remain downstream discovery evidence. The iTRS mock does not collapse them into directory persistence.

## Claim limits

This is a local clean-room proving ground. It is not:

- a live TRS Numbering Directory test;
- an implementation of the proprietary Neustar or iconectiv schema;
- an implementation of the iTRS Provisioning Guide V4.0 or Query Guide V4.1;
- VRS provider interoperability certification;
- production SIP/SDP media conformance;
- emergency-call testing; or
- evidence that any production provider accepts the synthetic signaling.

See `fixtures/README-evidence.md` for the evidence boundary.
