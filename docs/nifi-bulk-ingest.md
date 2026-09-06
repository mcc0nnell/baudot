# Apache NiFi bulk-ingest plane

Baudot uses Apache NiFi as the bounded bulk/legacy/provider data-movement plane around the Apache-native TRS business stack.

## Pin

```text
Apache NiFi: 2.11.0
release commit: e296b299805a7e3ff4c99916b79cfba16c5e4870
```

The profile uses NiFi 2 Git-based Flow Registry Clients. Apache NiFi Registry is not required.

## Role

```text
external batch / legacy source
        -> NiFi intake
        -> provenance + schema/shape checks
        -> quarantine on invalid input
        -> bounded staging target
        -> domain service decides acceptance
```

First flows:

- provider roster import -> provider staging;
- equipment inventory import -> OFBiz staging;
- Fund contribution report import -> Fineract-intent staging;
- legacy CDR backfill -> Kafka CDR staging;
- permitted document drop -> Tika extraction staging.

## Authority boundary

NiFi moves and transforms data. It does not create program authority.

```text
flow succeeded
!= source authoritative
!= subscriber eligible
!= provider certified
!= iTRS operation authorized
!= call verified
!= compensable
!= claim approved
!= payment authorized
!= ledger posted
```

Every accepted input carries source identity, source object identity, receive time, content hash, flow identity, and correlation identity. Invalid input is quarantined rather than promoted.

## Camel / Kafka / Airflow split

```text
Camel   -> request/event integration
NiFi    -> bulk, file, legacy, provider-feed movement
Kafka   -> durable event publication/replay
Airflow -> scheduled dependency execution/reconciliation
```

A NiFi flow may feed any of those layers, but the destination remains responsible for its own contract and authority checks.

## Privacy

Production deployments should minimize raw subscriber data in flow metadata, provenance attributes, logs, and queue labels. The synthetic test profile contains no real subscriber data, production provider records, credentials, or production CDRs.

## Next threshold

Stand up a pinned NiFi 2.11.0 lane with synthetic files for one provider roster and one legacy CDR backfill, preserve content hashes/provenance, force one malformed input to quarantine, and prove only validated staged records can reach the neutral downstream adapter.

That lane still would not establish business correctness or production NiFi security.
