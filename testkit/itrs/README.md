# iTRS mocks

Deterministic, clean-room fixtures and local services for exercising iTRS-derived routing behavior without access to the live TRS Numbering Directory.

Nothing here is production authority. The suite contains no live subscriber data, provider configuration, proprietary Neustar/iconectiv schema, production credentials, or copied ACE Direct source.

For the full progression from deterministic fixtures through the dual-ACE/Asterisk signaling lab, see [`docs/itrs-vrs-interoperability-lab.md`](../../docs/itrs-vrs-interoperability-lab.md).

## Two proving layers

### v1: resolution and service-discovery vectors

`fixtures/itrs-resolution-v1.json` preserves the original Baudot routing vectors for downstream ENUM/SIP discovery behavior. These vectors remain useful as service-discovery observations; they are **not** treated as the persistence schema of the TRS Numbering Directory.

Run:

```bash
bash scripts/run-itrs-mocks.sh
```

Expected final line:

```text
iTRS mock probe: 8/8 PASS
```

#### Public historical provenance

The clean-room v1 model has revision-pinned public historical corroboration from the MITRE ACE Direct repositories. The donor catalog lives at:

```text
testkit/itrs/research/public-itrs-donors-v1.json
```

Two sources are kept distinct:

```text
mitre-ace-direct/ace-direct
39c8f9ba73d889e743de56a2d49faf418b575c32
  -> public application-side iTRS adapter boundary
  -> sanitized test replacement for the lookup helper

mitre-ace-direct/asterisk
cbfc11e7660ed9d64c98d72336b3de3ea7b3aa33
  -> public historical scripts/itrslookup.sh
  -> reversed-number + .1 lookup owner
  -> optional CNAME hop
  -> E2U+sip selection
  -> ordinary SIP NAPTR/SRV discovery in full mode
```

That evidence corroborates the shape of four v1 fixtures:

- `direct-e2u-sip`;
- `alias-then-e2u-sip`;
- `naptr-priority-selection`; and
- `sip-service-discovery`.

The following remain deliberate Baudot resilience extensions rather than behaviors claimed from the historical donor:

- `no-route`;
- `malformed-e2u-sip`;
- `directory-unavailable`; and
- `slow-authority`.

The provenance gate enforces that distinction:

```bash
python -m scripts.validate_itrs_public_provenance
```

Historical code is not normative authority, a representation of current iTRS deployment behavior, a source of live routing data, or terminal verdict authority for Baudot. No donor code or production records are copied into the fixtures.

### v2: database-shaped CTE model

`fixtures/itrs-db-v2.json` and `ItrsDirectoryRepository` model relationships supported by public FCC rules and the 2024 iTRS Statement of Work:

- TN -> endpoint URI records;
- VRS / IP Relay service type;
- user type;
- default-provider XSPID responsibility;
- URD-valid state;
- NPAC SPID / AltSPID / LastAltSPID porting observations;
- separate provisioning and query views;
- provisioning-to-query replication delay;
- two-number AllCallQuery context;
- unique query transaction IDs;
- reverse validation by synthetic userid / IP / screen-name bindings; and
- the per-TN URD-valid operation.

The porting transition follows the public SOW invariant: when NPAC AltSPID/LastAltSPID indicates the gaining provider's XSPID, the gaining provider may provision the number; its first accepted provision transfers mock control and the losing provider loses write access.

The URD seam is separate from provider provisioning. Provider sessions cannot invoke the URD-valid operation, and provisioning never self-asserts URD validity.

## Local CTE-style HTTP surface

`ItrsCteMockServer` exposes Baudot-owned test endpoints on loopback:

```text
GET /itrs/v2/session
GET /itrs/v2/all-call-query
GET /itrs/v2/reverse-query
PUT /itrs/v2/provision
PUT /itrs/v2/urd-valid
GET /itrs/v2/record
```

The surface is intentionally REST/JSON-shaped because the public SOW expresses that design preference. Exact endpoint names, parameters, bearer tokens, and response bodies are **testkit contracts**, not claims about the production TRS Numbering Administrator API or the nonpublic iTRS Provisioning/Query Guides.

### Synthetic session boundary

The CTE uses three hard-coded **local test identities**:

```text
provider A session -> XSPID-A
provider B session -> XSPID-B
URD authority      -> URD-valid operation only
```

The tokens are not production credentials and authenticate only the loopback mock. The important invariant is structural: the server derives the provider XSPID from the authenticated session instead of trusting an `actorXspid` or `providerXspid` supplied by the caller.

### Multi-URI policy

The public model permits endpoint URI data, but this repository does not claim a production URI-selection algorithm. Baudot therefore defines an explicit deterministic **test policy**:

> Preserve fixture order and select the first URI supported by the requested service.

The `2025550109` fixture advertises three candidates:

```text
tel:+12025550109
sip:2025550109@provider-b.invalid
h323:2025550109@h323.provider-b.invalid
```

For VRS, the unsupported `tel:` candidate is skipped and the SIP URI is selected. This is a testkit rule, not an iconectiv/Neustar behavior claim.

### Reverse query policy

The CTE has synthetic reverse bindings for userid, IP address, and screen name. These exercise the public reverse-validation concept while avoiding any inference about production indexing or storage.

A compatibility endpoint:

```text
GET /itrs/v1/query?number=...
```

remains unauthenticated and loopback-only so the v2 repository can feed the existing JAIN-SIP handoff probe without creating a second signaling oracle.

## Run the CTE slice

```bash
bash scripts/run-itrs-cte.sh
```

The runner proves:

```text
provider session A / B        URD authority
          \                       /
           \                     /
            v                   v
          provider writes / URD / NPAC
                    |
                    v
            provisioning view
                    |
             replication seam
                    |
                    v
               query view
                 /     \
                v       v
        AllCallQuery   reverse query
                |
         deterministic URI
                |
                v
        existing JAIN-SIP probe
                |
                v
          mock VRS peer
```

The repository probe currently covers:

- provider-session isolation and unauthenticated rejection;
- valid cross-provider VRS routing;
- URD-invalid fail-closed behavior;
- malformed route URI fail-closed behavior;
- deterministic multi-URI selection;
- userid/IP reverse-query fixtures;
- non-default-provider provisioning denial;
- gaining-provider provisioning based on synthetic NPAC XSPID evidence;
- provisioning-to-query replication delay;
- losing-provider write revocation after the gaining provider's first provision;
- provider-session denial at the URD authority boundary;
- URD creation of an inactive directory stub;
- proof that provider provisioning cannot self-assert URD validity; and
- record inspection of all URI candidates plus the selected route.

Expected repository result:

```text
iTRS CTE probe: 13/13 PASS
```

The same run then executes the existing JAIN-SIP handoff and expects:

```text
iTRS -> Baudot -> JAIN-SIP handoff: PASS
```

## Two-provider ACE Connect Lite and Asterisk slices

The historical implementation fixture is pinned to public `mitrefccace/aceconnectlite` source at commit `da74e6450193be1456ce2cdf65dd5ffdf0e92f1e`.

The source-observed `/vrsverify/?vrsnum=...` call is treated only as an ACE **classification seam**. Baudot's compatibility adapter returns the fields the historical consumer demonstrably reads; it does not invent a logical route field. AllCallQuery remains the route authority.

The evidence ladder is:

```text
public-evidence iTRS CTE
        |
        +--> ACE /vrsverify/ compatibility adapter
        |
        +--> two pinned ACE Connect Lite runtimes
                    |
                    +--> real AMI
                           |
                           v
                    controlled Asterisk A/B
                           |
                    authenticated AllCallQuery
                           |
                     exact logical URI
                           |
                     PJSIP + proxy
                           |
                           v
                      JAIN-SIP peer
```

The dual-ACE runtime slice boots two isolated, unmodified ACE Connect Lite application instances and drives their real historical `outbound-call` handlers.

The Asterisk slice replaces the AMI stubs with two controlled Asterisk instances. Its dialplan performs an authenticated AllCallQuery after ACE selects `outbound-CA`, then sends the exact returned logical SIP URI through PJSIP to a separate loopback JAIN-SIP evidence peer.

Expected positive routes are:

```text
provider A -> 2025550103 -> sip:2025550103@provider-b.invalid
provider B -> 2025550101 -> sip:2025550101@vrs-a.example.invalid
```

The `2025550105` negative control is URD-invalid and must remain on ACE's `from-phones` path without reaching the route AGI or JAIN-SIP peer.

Target terminal verdicts are:

```text
Dual ACE Connect Lite runtime lab: 5/5 PASS
Dual ACE -> Asterisk -> JAIN-SIP lab: 8/8 PASS
```

Those strings remain targets until actually emitted by completed workflows for the exact commit under evaluation. Queue state, expected output, syntax checks, or local compilation do not promote a runtime claim.

ACE remains an implementation under test, never the authority for iTRS semantics or the terminal Baudot verdict.

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
- a reconstruction of production authentication or authorization;
- a claim about production multi-URI selection;
- VRS provider interoperability certification;
- production SIP/SDP media conformance;
- emergency-call testing; or
- evidence that any production provider accepts the synthetic signaling.

Even after a signaling workflow is independently verified, RTT/T.140/RFC 4103 media remains a separate evidence layer.

See `fixtures/README-evidence.md` for the public-source boundary and [`docs/itrs-vrs-interoperability-lab.md`](../../docs/itrs-vrs-interoperability-lab.md) for the full evidence ladder and promotion rules.
