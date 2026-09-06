# iTRS database-shaped mock evidence boundary

This branch models only relationships supported by public FCC material and existing Baudot testkit behavior. It does not reproduce or infer a proprietary production schema.

## Publicly supported relationships

Public evidence establishes these logical fields and relationships for the TRS Numbering Directory:

- NANP telephone number;
- endpoint URI;
- service type (VRS or IP Relay);
- user type;
- default-provider responsibility represented by provider XSPID;
- URD-valid state;
- NPAC porting observations including SPID, AltSPID and/or LastAltSPID;
- call query context: calling TN, called TN, service, and direction;
- a unique transaction ID per query;
- reverse validation by IP address, userid, or screen name; and
- provisioning-to-query replication as a distinct operational boundary.

The public FCC 2024 iTRS Statement of Work also states that the desired provisioning, query, reverse-query, and porting interfaces are REST/JSON-oriented and optimized for SIP proxy/gateway addressing. The referenced iTRS Provisioning Guide V4.0 and Query Guide V4.1 are not treated as public source material here.

## Baudot-owned test policies

The following behaviors are intentionally **ours**, not inferred production behavior:

- local bearer tokens representing provider A, provider B, and the URD authority;
- deriving synthetic XSPID identity from that local session token;
- exact `/itrs/v2/...` endpoint names and parameter shapes;
- ordered multi-URI selection using the first service-supported URI;
- the concrete reverse-query fixture bindings;
- HTTP status-code choices; and
- the compatibility `/itrs/v1/query` bridge into the existing JAIN-SIP probe.

These policies exist to make the proving ground deterministic.

## ACE Connect Lite boundary

PR #41 identifies ACE Connect Lite as an external historical VRS implementation fixture and `/vrsverify/` as a useful adapter seam. This branch may bind its synthetic provider identities to that fixture vocabulary, but ACE behavior does not define the directory model, URD semantics, NPAC semantics, or terminal Baudot verdicts.

Architectural consequence: DNS/ENUM/NAPTR/SRV observations remain useful downstream service-discovery fixtures, but they are not the persistence model of the TRS Numbering Directory.
