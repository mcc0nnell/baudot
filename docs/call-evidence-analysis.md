# Observe-only failed-call evidence analysis

This slice gives Baudot a deterministic call-failure reasoning primitive without giving the analyzer any live call-control authority.

The first contract is:

```text
interop/pjsip/call-evidence-bundle-v1.json
```

and the first executable fixtures are:

```text
testkit/call-evidence/known-good-v1.json
testkit/call-evidence/downstream-503-v1.json
```

## Boundary

The analyzer is explicitly:

```text
OBSERVE
```

It may read normalized call evidence and derive a finding. It may not:

- retry a call;
- terminate a call;
- select or rewrite a route;
- update registration;
- update numbering; or
- otherwise mutate live call state.

This keeps failure reasoning separate from call execution.

## First deterministic rule

The first rule is intentionally narrow:

```text
downstream SIP final response observed
+ SIP status = 503
=
DOWNSTREAM_FINAL_503_OBSERVED
failure boundary = downstream-signaling-boundary
root cause = NOT_DERIVED
```

The finding records where the measured call first crossed into a failed signaling outcome. It does **not** claim that the downstream provider caused the underlying problem.

## Differential evidence

The analyzer can compare a failed bundle with a known-good bundle.

For the first pair, both calls share the same first four normalized observations:

```text
ingress INVITE observed
iTRS lookup succeeded
provider route selected
downstream INVITE sent
```

The first divergence is then:

```text
known good -> 180 Ringing
failed     -> 503 Service Unavailable
```

This is stronger than a free-form log summary because the common prefix and divergence are machine-checkable.

## Privacy

The first contract accepts only synthetic or tokenized identity and rejects common raw telephone-number, subscriber, and credential field names.

Production ingestion should normalize/redact raw artifacts before they become a `CallEvidenceBundle`.

## Run locally or from external CI

```bash
python scripts/validate_call_evidence_analysis.py

python scripts/analyze_call_evidence.py \
  testkit/call-evidence/downstream-503-v1.json \
  --baseline testkit/call-evidence/known-good-v1.json
```

No GitHub Actions workflow is added by this slice.

## What this establishes

A green run establishes that Baudot can:

1. validate an observe-only call-evidence bundle;
2. preserve a deterministic ordered signaling/routing timeline;
3. derive one explicit 503 signaling-boundary finding;
4. compare failed evidence with a known-good call; and
5. refuse to promote that finding into production root cause, provider fault, or live call-control authority.

## What it does not establish

This slice does not yet ingest production SIP traces, CDRs, provider logs, DNS/network telemetry, SDP/media evidence, registration state, timer expirations, or real iTRS data.

It also does not establish production root cause, provider fault, service-quality compliance, compensability, or regulatory compliance.

## Next threshold

Add normalized timer-expiry and SDP/media observations, then admit real redacted call artifacts through an evidence-only ingestion adapter. Keep the reducer deterministic and keep any probabilistic/model-based explanation downstream of the machine-derived finding.
