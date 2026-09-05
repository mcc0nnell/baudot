# JAIN SIP + Wiretap harness

Baudot owns accessible real-time communications behavior and test vocabulary. JAIN SIP and Sandia Wiretap are test adapters: they let Baudot exercise transport behavior without redefining the T.140 semantic core.

## Boundary

```text
Baudot scenario / expectation
        |
        +-- JAIN SIP probe -------- signaling observation
        |
        +-- UDP media-path probe -- reachability observation
        |
        +-- Wiretap --------------- controlled routed topology
        |
        `-- evidence aggregator --- canonical result + hashes
```

The UDP heartbeat in this first slice is **not RTP** and is not an RTP conformance claim. It exists only to prove that successful SIP signaling and successful media-path reachability are independent observations. A later RTP/RFC 4103 adapter can replace the heartbeat without changing that evidence model.

## Distributed roles

`BaudotProbe` has two roles, selected with `BAUDOT_ROLE`:

- `callee`: binds a SIP endpoint and the media-path probe receiver, answers INVITE, and records what arrived.
- `caller`: sends an INVITE, completes the dialog on 200 OK, sends a correlated media probe, and records what it sent.

Both sides use the same `BAUDOT_CORRELATION` value. After a run, `EvidenceAggregator` joins the two role bundles and verifies that scenario ID, correlation ID, and expected media state agree before classifying the run.

## Aggregate state

The aggregate intentionally separates *scenario success* from *observed communications state*.

Example baseline:

```json
{"scenario":"001-signaling-and-media","correlation":"...","scenarioResult":"PASS","callState":"CALL_ESTABLISHED","mediaState":"MEDIA_RECEIVED","expectedMedia":"true"}
```

Example injected media failure:

```json
{"scenario":"002-signaling-only","correlation":"...","scenarioResult":"PASS","callState":"CALL_ESTABLISHED","mediaState":"MEDIA_FAILED","expectedMedia":"false"}
```

That second result is the important invariant: the experiment passed because Baudot successfully reproduced a state where signaling was healthy while the media path was not.

## Local deterministic smoke runs

The two checked-in scenarios run on loopback and exercise the evidence/classification machinery without Wiretap:

```bash
bash scripts/run-local-scenario.sh scenarios/001-signaling-and-media.env
bash scripts/run-local-scenario.sh scenarios/002-signaling-only.env
```

Scenario 002 uses a deliberately unbound local UDP target. This is a synthetic negative control, not a claim about NAT, SBC, browser, or production-network behavior.

## Wiretap topology

For a real routed experiment, place signaling and media on separately routable test CIDRs on the remote side, for example:

```text
10.77.10.0/24  SIP signaling
10.77.20.0/24  media test path
```

Then generate Wiretap client configuration:

```bash
export WIRETAP_ENDPOINT=<reachable-host:port>

# Healthy path: route both signaling and media through Wiretap.
bash scripts/wiretap/configure-client.sh 001

# Fault path: route signaling only; media remains unreachable through this test topology.
bash scripts/wiretap/configure-client.sh 002
```

The generated WireGuard configuration is installed using Wiretap's normal documented workflow. Baudot does not automatically elevate privileges, install interfaces, or deploy the remote Wiretap server.

On the remote test host, run the callee with distinct advertised signaling/media addresses. On the client, run the caller with the same correlation ID. Collect both evidence directories and aggregate them.

## Evidence bundle

Each role emits:

```text
<evidence-root>/<scenario>/<correlation>/<role>/
  events.jsonl
  result.properties
  manifest.sha256
```

Aggregation adds:

```text
<evidence-root>/<scenario>/<correlation>/aggregate/
  result.json
  manifest.sha256
```

The aggregate manifest hashes both role event/result files plus the aggregate result. This is evidence preservation, not attestation: signing and WindAnvil policy evaluation are separate layers.

## Dependency posture

The harness uses `javax.sip:jain-sip-ri:1.3.0-91`. The RI is old, so Baudot treats it as a bounded interoperability instrument rather than a general-purpose platform choice. Its legacy Log4j 1.x API is bridged to SLF4J instead of adding a Log4j 1.x runtime dependency.

Wiretap remains an external executable and topology provider. Baudot does not fork it, vendor it, or make its network model part of Baudot's semantic core.

PJSIP is planned as a separate endpoint/media oracle, not as a replacement for the JAIN SIP signaling probe. Its observations should be preserved independently and compared only at the Baudot evidence layer. See [`sip-stack-strategy.md`](sip-stack-strategy.md) for that boundary and the first proving slice.
