# Kafka CDR event spine

This slice makes Apache Kafka the reference durable transport/replay layer for synthetic Baudot call detail records (CDRs) while keeping call truth, compensability, claim approval, and accessibility readiness outside Kafka.

The core boundary is:

```text
communications observations
        -> bounded CDR envelope
        -> Kafka topic
        -> durable publication / replay
        -> downstream business workflow

Kafka persisted record
!= call independently verified
!= compensable minutes
!= claim approved
```

## Pinned Kafka profile

The live CI lane uses Apache Kafka **4.3.1**, currently listed by the Apache Kafka project as a supported release.

```text
release:       4.3.1
release commit: 26b251a451ce941d3d7a55e6487bcb7f16b5ad48
Docker image:  apache/kafka:4.3.1
topic:         baudot.synthetic.cdr.v1
partitions:    1
replication:   1
record key:    callId
```

Sources:

- <https://kafka.apache.org/community/downloads/>
- <https://kafka.apache.org/documentation/>
- <https://github.com/apache/kafka/tree/trunk/docker>

The single-partition topology is intentional test infrastructure. It provides a deterministic ordered proving lane and is not a production scaling recommendation.

## CDR envelope

`testkit/business/kafka-cdr-lane-v1.json` defines `baudot.cdr@1` with the minimum fields needed for this synthetic proving slice:

```text
schema
eventId
callId
providerId
serviceType
direction
fromTn
toTn
startedAt
endedAt
durationSeconds
sourceObservationRefs
authority
```

All numbers are in the reserved synthetic `202-555-01xx` range and every source reference is explicitly synthetic.

The envelope intentionally forbids fields that would silently promote a call record into a stronger business or accessibility claim:

```text
compensable
claimApproved
paymentAuthorized
providerCertified
rttReady
accessibilityReady
```

A future claim workflow may correlate a CDR with independent policy/evidence and create a separate authorized business event. It must not mutate the original CDR into that decision.

## Live proving lane

The CI workflow boots the official `apache/kafka:4.3.1` JVM image, then:

1. creates `baudot.synthetic.cdr.v1` with one partition;
2. publishes four deterministic keyed CDRs using Kafka's console producer;
3. consumes the topic from the beginning;
4. independently parses and validates every key/envelope;
5. consumes the topic from the beginning a second time;
6. requires the semantic replay to equal the first read exactly; and
7. seals fixture, producer, consume, replay, image-ID, and verdict hashes into an evidence bundle.

The topic key is the stable synthetic `callId`. Kafka provides durable storage and replay; the Baudot contract defines what each CDR field means.

## Synthetic corpus

The first corpus includes one synthetic record each for:

```text
VRS
IP CTS
IP Relay
TTY
```

The corpus is workload only. It contains no live provider traffic, subscriber records, production CDRs, or reimbursement decisions.

## Why Kafka does not own semantics

Kafka documentation describes events as records/messages organized in topics that clients can write, store, read, and process. That is exactly the infrastructure role needed here.

Baudot still owns the event contract and authority boundary:

```text
Kafka key/value bytes
        -> transport fact

baudot.cdr@1 validation
        -> CDR semantic fact

separate program-policy authorization
        -> compensability / claim fact
```

Those layers must stay independently observable.

## Next threshold

After this lane is green, the useful next composition is:

```text
Baudot call evidence
  -> Kafka CDR
  -> explicit synthetic compensability decision
  -> approved claim event
  -> existing Fineract journal-intent lane
```

That child must prove that an unapproved CDR never reaches the Fineract payable path, and that replaying the same CDR does not create a duplicate claim or ledger posting.

A separate scale/repartitioning lane can come later; the one-partition proving profile should remain as a deterministic control.

## Claim boundary

This lane establishes only that the pinned Kafka test deployment can accept, retain, return, and replay the synthetic CDR corpus while preserving the Baudot envelope and key correlation.

It does not establish production Kafka security, production sizing, exactly-once business processing, live call truth, provider certification, compensability, claim approval, Fund authorization, or accessibility readiness.
