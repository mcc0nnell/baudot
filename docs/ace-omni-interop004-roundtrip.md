# BAUDOT-INTEROP-004 → ACE Omni observation round trip

This note records the first cross-repository evidence round trip between Baudot and ACE Omni.

It does not change the authority boundary in ADR-0002:

- **Baudot owns** accessible communications semantics, source facts, readiness vocabulary, assertions, claim scope, and terminal reduction.
- **ACE Omni owns** the identity, envelope digest, replay behavior, sequence, and export of an Omni-controlled evidence run.
- **Attached runtimes and probes own** the external effects and measurements they actually observe.

## Source run

The source is the green CI run for Baudot PR #45:

- repository: `mcc0nnell/baudot`
- source head: `f4dfe0c21e530d02d4fb5b4547fbf0098716a16b`
- GitHub Actions run: `33996472033`
- evidence artifact: `baudot-evidence`
- artifact id: `9978215143`
- artifact digest: `sha256:61cf2136f84c00892f94ce7fa5563dd1fe29dc24e7c652d4f9ea5f92ddb66a46`
- exported JSONL: `BAUDOT-INTEROP-004/omni-bridge-v1/observation-inputs.jsonl`
- JSONL SHA-256: `f15a1a84044bb210f879f3ebeb472bed83444f7211c957d429eb96e1f914220f`
- observation count: `17`
- source run binding: `baudot-ci-33996472033-1`
- source adapter binding: `baudot-interop004`

The Baudot export remains explicitly `authority: candidate-input`.

## Source evidence split

The 17 observations preserve source authority rather than flattening every fact into one implementation.

JAIN SIP probe evidence includes signaling and continuity facts such as:

- `referAccepted`;
- `notifyProgressObserved`;
- `replacementDialogEstablished`;
- `replacementTargetCorrelated`;
- `rttNegotiated`; and
- old-leg preservation or release.

The independent Python RFC 4103/T.140 reference owns:

- `firstT140CharacterObserved`; and
- `rttReady`.

That split is required because successful REFER, NOTIFY, replacement-dialog establishment, or SDP negotiation cannot manufacture observed T.140 readiness.

## Omni ingestion proof

ACE Omni PR #43, `Ingest Baudot INTEROP-004 observations into Omni ledger`, pins the exact JSONL from the Baudot Actions artifact as its test fixture.

The Omni-side proof:

1. validates all 17 records against the declared Baudot source run and adapter binding;
2. creates authoritative `ObservationEnvelope` records under a separate Omni-owned target run;
3. preserves each observation id, source id, timestamp, and payload;
4. computes canonical payload SHA-256 values inside Omni;
5. assigns stable one-based ledger sequence;
6. accepts an exact replay idempotently without creating a second observation;
7. rejects a changed timestamp under the same replay identity as a conflict;
8. exports the ordered ledger with a stable SHA-256 digest; and
9. projects the Baudot facts back out unchanged.

The round-trip assertions include:

```text
live-transfer:referAccepted = true
live-transfer:replacementDialogEstablished = true
live-transfer:replacementTargetCorrelated = true
control:rttNegotiated = true
control:firstT140CharacterObserved = true
control:rttReady = true
signaling-only:rttNegotiated = true
signaling-only:firstT140CharacterObserved = false
signaling-only:rttReady = false
signaling-only:oldLegPreserved = true
```

The important result is not that Omni agrees with Baudot. It is that Omni can preserve Baudot's source-identified facts, replay identity, and control/signaling-only distinction without redefining the accessibility claim.

## Two run identities, intentionally

The Baudot CI bundle was created before an Omni-owned run existed. Its `runId` is therefore source provenance, not an Omni call identifier.

The Omni import keeps the source binding explicit and creates a separate target run identity for its authoritative envelopes. This avoids laundering a foreign CI identifier into an Omni-owned execution identity.

The live ACE Omni TRS room path is different: its Durable Object binds `runId` to the server-created call UUID, owns authoritative room event sequence, synchronizes to D1, and retains the observation in a finalized evidence manifest.

The PR #43 import proof is protocol-level ledger authority. It does **not** claim that Baudot Actions run `33996472033` executed as a live Cloudflare Durable Object room or that the imported generic-run entries were persisted to D1.

## What this closes

Before this round trip, the cross-project boundary was specified but only one-way:

```text
Baudot evidence → ObservationInput candidates
```

The downstream integration demonstrates the other side:

```text
Baudot live probes
      ↓
Baudot terminal RUNNABLE_PASS
      ↓
source-bound ObservationInput candidates
      ↓
Omni source-binding validation
      ↓
Omni ObservationEnvelope + digest + sequence
      ↓
exact replay / conflict detection
      ↓
immutable Omni ledger export
      ↓
Baudot facts projected unchanged
```

This closes the protocol round trip while preserving separate authorities.

## What it still does not prove

The round trip does not establish:

- SIP or REFER conformance;
- RFC 4103 or T.140 conformance;
- production VRS interoperability;
- any behavior of a named contemporary provider;
- live generic-run persistence in ACE Omni D1/R2;
- that an Omni run may promote `BAUDOT-INTEROP-004` beyond `runnable`; or
- that evidence transport may replace Baudot's declared `requiredBeforeProven` review.

Scenario promotion remains a Baudot project decision based on the scenario's own evidence requirements.
