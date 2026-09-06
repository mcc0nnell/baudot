# iTRS database-shaped mock evidence boundary

This branch models only relationships supported by public FCC material and existing Baudot testkit behavior. It does not reproduce or infer a proprietary production schema.

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
- reverse validation by IP address, userid, or screen name;
- provisioning-to-query replication as a distinct operational boundary.

The public FCC 2024 iTRS Statement of Work also states that the desired provisioning, query, reverse-query, and porting interfaces are REST/JSON-oriented and optimized for SIP proxy/gateway addressing. The referenced iTRS Provisioning Guide V4.0 and Query Guide V4.1 are not treated as public source material here.

Architectural consequence: DNS/ENUM/NAPTR/SRV observations remain useful downstream service-discovery fixtures, but they are not the persistence model of the TRS Numbering Directory.
