# iTRS database-shaped mock evidence boundary

This testkit models only relationships supported by public FCC material. It does not reproduce or infer a proprietary Neustar/iconectiv production schema or the nonpublic iTRS Provisioning/Query Guides.

## Publicly supported relationships

The FCC's 2024 iTRS Statement of Work describes the TRS Numbering Directory as a central database used to associate an iTRS user's telephone number with one or more endpoint URIs. Publicly described data/behavior includes:

- NANP telephone number;
- endpoint URI;
- service type (VRS or IP Relay);
- user type;
- default-provider responsibility represented by provider XSPID;
- URD-valid state;
- NPAC porting observations including SPID, AltSPID and/or LastAltSPID;
- calling TN, called TN, service, and direction for AllCallQuery;
- a unique transaction ID for each query;
- provisioning-to-query replication as a distinct operational boundary; and
- a Customer Test Environment separate from production but using the same code/facilities.

The SOW also describes desired provisioning, query, porting, and URD interfaces as REST/JSON-oriented. Baudot therefore uses a REST/JSON-shaped local test surface, but does not copy or claim the production endpoint contract.

## Default-provider and porting invariant

Public FCC requirements state that only the default provider may create/update the directory record for an assigned TN.

For a port, the directory monitors NPAC SPID, AltSPID and/or LastAltSPID. When the gaining provider's XSPID appears in the relevant NPAC observations, the directory allows that provider to provision the number. As soon as the gaining provider first provisions it, the losing provider loses access.

`ItrsDirectoryRepository` models exactly that ownership transition with synthetic XSPIDs.

## URD invariant

The public SOW describes a real-time per-TN URD-valid operation carrying:

- TN;
- provider XSPID;
- service type; and
- URD-valid Boolean.

If the TN does not exist, the directory creates a record carrying provider XSPID and service, and only that provider may activate it. Baudot models that record as an inactive stub until provider provisioning supplies a route. Provider provisioning preserves, rather than invents, the URD-valid state.

## Replication invariant

The public SOW defines an SLA specifically for replication from provisioning operations to the query database. Baudot therefore keeps separate provisioning and query views and makes replication delay an explicit test variable.

## Downstream discovery boundary

DNS/ENUM/NAPTR/SRV observations remain useful routing/service-discovery fixtures, but they are not treated as the persistence model of the TRS Numbering Directory.

## Excluded sources

The referenced iTRS Provisioning Guide V4.0, Query Guide V4.1, production records, credentials, live subscriber data, and any proprietary Neustar/iconectiv implementation details are outside this testkit's source boundary unless an authorized public source becomes available.
