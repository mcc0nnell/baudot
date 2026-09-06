# iTRS / VRS interoperability lab

Baudot's iTRS work is an evidence ladder, not a single mock service. Each layer adds a stronger execution boundary while preserving the distinction between public routing semantics, historical implementation behavior, transport, and terminal verdicts.

## Current verification status

Status snapshot: **2026-09-05 21:12 America/New_York**.

The implementation is ahead of the hosted CI evidence right now.

- PR #59 implements the clean-room iTRS Customer Test Environment (CTE), provider-session boundary, AllCallQuery, reverse query, provisioning/replication/porting behavior, and the ACE `/vrsverify/` compatibility adapter.
- PR #69 implements two pinned, unmodified ACE Connect Lite application instances driven through their real historical `outbound-call` path.
- PR #70 implements two controlled Asterisk instances and a JAIN-SIP signaling evidence peer.
- The GitHub Actions jobs for the new dual-ACE and dual-ACE/Asterisk slices are currently **queued**. They have not acquired a runner, executed steps, produced logs, or uploaded artifacts.

Therefore the correct claim today is **implemented and runnable, awaiting hosted runtime verification**. Do not describe PR #69 or PR #70 as CI-proven or green until the corresponding workflow completes successfully and its evidence artifacts exist.

## Evidence ladder

### Layer 1: deterministic iTRS resolution

The original iTRS vectors exercise clean-room number-to-route behavior and downstream ENUM/SIP discovery cases.

```text
synthetic TN
    -> mock resolution
    -> logical SIP URI
    -> JAIN-SIP handoff
```

This layer is useful for deterministic regression coverage. It is not a model of the production TRS Numbering Directory schema.

### Layer 2: public-evidence CTE model

The CTE models relationships supported by public FCC rules and the public 2024 iTRS Statement of Work:

```text
URD-derived state ----\
                       \
NPAC porting state ----> directory / query decision
                       /
provider provisioning-/
          |
          v
  replication boundary
          |
          v
      query view
       /      \
AllCallQuery  reverse query
       |
       v
logical route URI
```

The model intentionally keeps URD PII, Registered Location, proprietary administrator schema, production credentials, and nonpublic interface guides outside the source boundary.

### Layer 3: historical ACE consumer seam

The pinned public ACE Connect Lite source is:

```text
mitrefccace/aceconnectlite
da74e6450193be1456ce2cdf65dd5ffdf0e92f1e
```

At that source pin, ACE consumes:

```text
GET /vrsverify/?vrsnum=<number>
```

and branches on `message === "success"`. Incoming enrichment also consumes `data[0].vrs`.

Baudot's adapter reproduces only that observed consumer shape. It does **not** invent a logical route field in `/vrsverify/` and does not claim to reconstruct the original verifier service.

This preserves the boundary:

```text
/vrsverify/ = historical ACE classification seam
AllCallQuery = logical route authority
```

### Layer 4: two real ACE application instances

The dual-ACE runtime slice boots two isolated copies of the pinned historical Node application without patching `server.js`.

```text
ACE A                         ACE B
  |                             |
  | real outbound-call handler  | real outbound-call handler
  v                             v
adapter A                     adapter B
       \                       /
            shared iTRS CTE
```

Each instance has a separate application port, login identity, adapter, provider identity, and AMI peer.

The intended evidence is not merely that ACE boots. The assertion is that the real historical handler consumes the CTE-backed classification and submits the expected AMI `Originate` context:

```text
routable VRS -> outbound-CA
failed lookup -> from-phones
```

Until its Actions job runs successfully, this remains an implemented runtime proof awaiting hosted verification.

### Layer 5: real Asterisk and JAIN-SIP signaling

PR #70 replaces the deterministic AMI peers with two controlled Asterisk instances.

```text
ACE A / ACE B
    |
    | real AMI Originate
    v
Asterisk A / Asterisk B
    |
    | outbound-CA
    v
authenticated CTE route AGI
    |
    v
exact logical SIP URI
    |
    | PJSIP explicit URI
    | separate outbound proxy
    v
JAIN-SIP evidence peer
```

The Asterisk dialplan does not hard-code the destination provider domain. After ACE classifies the call as VRS, the dialplan performs an authenticated AllCallQuery using the synthetic provider session. The returned `routeUri` becomes the SIP Request-URI.

The loopback JAIN-SIP peer is a separate transport fact. A successful run must preserve the logical `.invalid` URI while completing a signaling-only exchange:

```text
INVITE -> 200 OK -> ACK -> BYE -> 200 OK
```

Positive routes:

```text
provider A -> 2025550103 -> sip:2025550103@provider-b.invalid
provider B -> 2025550101 -> sip:2025550101@vrs-a.example.invalid
```

Negative control:

```text
2025550105 -> URD-invalid -> ACE from-phones
                         -> no route AGI
                         -> no JAIN-SIP INVITE
```

The target assertion is:

```text
Dual ACE -> Asterisk -> JAIN-SIP lab: 8/8 PASS
```

That string is a **target verdict**, not a current result, until CI actually produces it.

## Promotion rule

Baudot should promote a runtime claim only when all of the following exist for the same commit:

1. the relevant workflow completed with `success`;
2. the assertion layer reached its terminal PASS verdict;
3. generated evidence artifacts were uploaded;
4. the observed route identity matches the CTE decision;
5. the transport destination remains independently observable; and
6. negative controls demonstrate the expected fail-closed boundary.

A queued workflow, a syntactically valid harness, a locally compiled component, or an expected output string is not sufficient evidence for promotion.

## Claim boundary

Even after the signaling workflow turns green, the result is still bounded. It can support a claim about a synthetic signaling path through a historical ACE application, controlled Asterisk, clean-room iTRS routing state, and an independent JAIN-SIP peer.

It does not establish:

- live TRS Numbering Directory interoperability;
- iconectiv or Neustar production API compatibility;
- VRS provider certification;
- production subscriber behavior;
- emergency-call behavior;
- interpreter queue behavior;
- media quality;
- RFC 4103 / T.140 media interoperability; or
- end-to-end production security properties.

The next evidence layer after the signaling path is green is the RTT/media plane: negotiate and observe T.140/RFC 4103 independently while retaining the same route, signaling, and claim-separation discipline.
