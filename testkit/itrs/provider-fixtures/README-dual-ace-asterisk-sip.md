# Dual ACE Connect Lite -> Asterisk -> JAIN-SIP lab

This slice replaces the deterministic AMI stubs from the dual-ACE runtime lab with **two real, isolated Asterisk processes** and carries the successful ACE decisions into Baudot's JAIN-SIP evidence path.

ACE remains pinned and unmodified:

```text
mitrefccace/aceconnectlite
da74e6450193be1456ce2cdf65dd5ffdf0e92f1e
```

The PBX configuration is intentionally **not** taken from the historical ACE Asterisk submodule. That old pin is not used as a source boundary here. Instead, CI installs the Ubuntu 24.04 `asterisk` package and generates a minimal Baudot-owned configuration for each provider fixture.

## Verification status

Status snapshot: **2026-09-05 21:12 America/New_York**.

This lab is implemented, but its hosted runtime proof is **not green yet**. The GitHub Actions workflow is currently queued and has not acquired a runner. No workflow step has executed and no evidence artifact has been produced for the current head.

Accordingly:

- `Dual ACE -> Asterisk -> JAIN-SIP lab: 8/8 PASS` is the **target terminal verdict**, not a current result;
- the correct current claim is **implemented and runnable, awaiting hosted runtime verification**; and
- the signaling-level claim may be promoted only after the workflow completes successfully and uploads the expected evidence.

See [`docs/itrs-vrs-interoperability-lab.md`](../../../docs/itrs-vrs-interoperability-lab.md) for the full evidence ladder and promotion rule.

## Architecture

```text
ACE A real server.js                         ACE B real server.js
        |                                            |
        | historical /vrsverify/                     | historical /vrsverify/
        v                                            v
Baudot adapter A                              Baudot adapter B
        \                                            /
         \                                          /
                    synthetic iTRS CTE

ACE A --real AMI--> Asterisk A       ACE B --real AMI--> Asterisk B
                         |                       |
                         | outbound-CA           | outbound-CA
                         v                       v
                    CTE route AGI           CTE route AGI
                         |                       |
                  exact logical URI        exact logical URI
                         |                       |
             PJSIP + outbound proxy   PJSIP + outbound proxy
                         |                       |
                         v                       v
                JAIN-SIP peer B          JAIN-SIP peer A
```

The important separation survives the PBX boundary:

1. `/vrsverify/` only classifies the number for historical ACE behavior.
2. The controlled Asterisk `outbound-CA` context independently performs an authenticated AllCallQuery against the synthetic CTE.
3. The CTE result becomes the explicit PJSIP Request-URI.
4. A separate `outbound_proxy` directs the packet to a loopback JAIN-SIP peer without replacing the logical URI.

## Signaling proof

Each positive leg must complete:

```text
ACE outbound-call
  -> real AMI Originate
  -> Asterisk Local agent leg
  -> outbound-CA dialplan
  -> authenticated AllCallQuery
  -> PJSIP INVITE with exact CTE logical Request-URI
  -> JAIN-SIP 200 OK
  -> Asterisk ACK
  -> JAIN-SIP BYE
  -> Asterisk 200 OK
```

Expected positive routes:

```text
provider A -> 2025550103 -> sip:2025550103@provider-b.invalid
provider B -> 2025550101 -> sip:2025550101@vrs-a.example.invalid
```

The negative `2025550105` case must remain on ACE's historical `from-phones` context and must not reach the route AGI or JAIN-SIP peer.

The final assertion matrix is expected to report:

```text
Dual ACE -> Asterisk -> JAIN-SIP lab: 8/8 PASS
```

Do not treat the expected string above as observed evidence until the workflow completes and the assertion output is preserved.

## Evidence

A completed run writes:

- the installed Asterisk version;
- one JSONL AllCallQuery/AGI trace per provider;
- one JSON JAIN-SIP transaction record per positive provider leg;
- generated Asterisk configuration; and
- ACE/Asterisk/adapter/JAIN-SIP logs.

The workflow is configured to upload the lab evidence even on failure, so a red run should identify the failing boundary rather than collapse into a generic CI error.

The JAIN-SIP evidence record captures the logical Request-URI and Route header so the test can prove that routing identity and immediate transport destination remain distinct facts.

## Claim limit

When a green run exists, it can support a **signaling-level synthetic interoperability proof**, not a production VRS certification. The remote gateways are JAIN-SIP test peers; no production provider, live TRS Numbering Directory, subscriber record, emergency call path, media quality, interpreter queue, or RTT conformance is exercised here.
