# SIP stack strategy: reference signaling + endpoint oracle

Baudot does not choose a SIP implementation as the source of truth for accessible real-time communications behavior. The semantic core remains the canonical T.140/RFC 4103 behavior and evidence model. SIP stacks are instruments used to exercise that model.

The current strategy intentionally uses two independent SIP implementations with different jobs:

```text
canonical Baudot scenario / vectors
             |
             +--> JAIN SIP -------- glass-box signaling observation
             |
Wiretap -----+--------------------- controlled network topology
             |
             +--> PJSIP ----------- endpoint/media observation
             |
             `--> evidence -------- comparison + preserved artifacts
```

## JAIN SIP: signaling reference instrument

JAIN SIP remains Baudot's bounded signaling instrument.

It is useful because the harness can observe and control SIP transactions, dialogs, message construction, response handling, and SDP exchange without treating a full softphone or media engine as a black box.

Baudot uses JAIN SIP to answer questions such as:

- Did the INVITE transaction complete?
- Was the dialog established only after the expected INVITE -> 200 -> ACK sequence?
- What SIP or SDP material was sent and received?
- Which signaling behavior changes under a controlled network fault?
- Can a historical or malformed interoperability case be reproduced deterministically?

JAIN SIP is **not** the production endpoint recommendation and is not the authority for T.140 or RFC 4103 semantics. Its age is a reason to keep the dependency bounded, observable, and replaceable.

## PJSIP: endpoint and media oracle

PJSIP is the independent endpoint/media implementation used to test whether Baudot's scenarios survive contact with a substantially different SIP and media stack.

PJSIP 2.16 and later includes RFC 4103 real-time text support in PJMEDIA, including SDP text-stream negotiation and RFC 2198 redundancy handling. That makes it directly useful for Baudot once the canonical RFC 4103 fixtures are routed through a real endpoint/media implementation.

Baudot should introduce PJSIP as an **oracle, not an authority**. Agreement between JAIN SIP and PJSIP is useful evidence. Disagreement is more useful still: it creates a concrete interoperability case to preserve and reduce.

PJSIP should answer questions such as:

- Does a real endpoint accept the same offer/answer sequence that the JAIN SIP probe observed?
- Does the negotiated `m=text` stream become usable?
- Are T.140/RFC 4103 packets emitted and received as expected?
- Does RFC 2198 redundancy recover text under controlled loss?
- Do signaling and text-media outcomes diverge under NAT-, SBC-, routing-, or loss-like faults introduced by the lab?

## Wiretap: topology, not semantics

Sandia Wiretap remains the controlled network substrate.

Wiretap may route, isolate, impair, or deny selected paths, but it does not define Baudot call state, media state, RTT state, or conformance. Those classifications belong to Baudot's evidence model.

The same scenario should be runnable against both SIP implementations under the same declared topology whenever practical.

## Differential interoperability model

A future cross-stack run should keep each implementation's observations separate before comparison.

Example evidence shape:

```text
scenario
  canonical-inputs/
  topology/
  jain-sip/
    signaling-events.jsonl
    result.properties
    manifest.sha256
  pjsip/
    endpoint-events.jsonl
    media-events.jsonl
    result.properties
    manifest.sha256
  aggregate/
    comparison.json
    manifest.sha256
```

The aggregate may classify outcomes such as:

```text
SIGNALING_AGREES
SIGNALING_DIVERGES
RTT_AGREES
RTT_DIVERGES
MEDIA_ONLY_FAILURE
STACK_SPECIFIC_FAILURE
```

These are interoperability observations, not automatic specification judgments. A stack disagreement must be reduced against the canonical Baudot vector and applicable protocol requirements before assigning fault.

## First PJSIP proving slice

The first PJSIP implementation should remain deliberately narrow:

1. Pin and checksum an explicit PJSIP release in the lab.
2. Stand up one deterministic caller/callee endpoint pair.
3. Negotiate one `m=text` RFC 4103 stream.
4. Replay an existing canonical non-redundant T140block vector rather than inventing a second serializer.
5. Preserve independent send/receive observations and hashes.
6. Run the same scenario through Wiretap with a healthy route and one injected text-media failure.
7. Compare the PJSIP result with the existing JAIN SIP signaling evidence without collapsing them into one pass/fail bit.

RFC 2198 redundancy, NAT/SBC matrices, codec interaction, browser/WebRTC gateways, and production VRS endpoints belong in later slices.

## E2EE boundary

End-to-end media protection is not a responsibility of either SIP stack.

SIP and SDP establish and describe sessions. Baudot's VRS E2EE work separately defines which participants are authorized to decrypt a media epoch and which infrastructure must remain outside the plaintext boundary. A future media-protection mechanism can therefore be tested across either signaling stack without making JAIN SIP or PJSIP the trust model.

## Non-claims

This strategy does not claim:

- that JAIN SIP or PJSIP is protocol-conformant merely because it is used as a test instrument;
- that agreement between two implementations proves standards conformance;
- that PJSIP is the Baudot production runtime;
- that the current harness proves RFC 4103, RFC 2198, NAT/SBC, browser, VRS, or accessibility conformance;
- that SIP-layer security is equivalent to end-to-end media confidentiality.

The goal is narrower: use independent stacks and a controlled network to turn interoperability differences into reproducible, evidence-bearing tests.