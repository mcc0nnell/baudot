# NiFi -> Tika -> Solr provenance-preserving handoff

This qualification slice composes the live NiFi bulk-ingest and Tika/Solr document-search lanes without making either plane authoritative for the other.

## Composition pins

The CI lane deliberately composes the exact current sibling heads instead of merging their pull requests into the shared integration branch just to run a test:

```text
common base     65723f8c6f566f092ebdd4a3901cf8743ca5a0bc
NiFi #121       bf6ffa25423c9107ef3b1ca546bc14f7574116bf
Tika/Solr #129  9df3f208cc126d070060f495295c1babbedf6cb6
```

Those trees are merged only inside the Actions worktree. The repository branch topology remains unchanged. A separate closure workflow compares these declared pins with the current PR heads and fails if either sibling moves, so prior qualification cannot silently follow new code.

## Handoff invariant

NiFi owns intake evidence for the original object:

```text
sourceSystem
sourceObjectId
receivedAt
contentSha256
flowId
correlationId
```

The document lane must not rename those fields into a new source identity vocabulary. In particular:

```text
sourceObjectId  != documentId rewrite
contentSha256   != sourceSha256 rewrite
```

The NiFi-emitted provenance JSON is treated as an immutable input artifact. Its bytes are hashed before Tika parsing and checked again after Solr indexing. The original staged document bytes are likewise checked before and after downstream processing.

## Append-only downstream evidence

Tika and Solr may add only derived extraction/index evidence:

```text
sourceEvidenceId
extractor
extractorVersion
parserHttpStatus
extractedContentSha256
indexRecordId
indexVersion
indexedAt
content
derivedEvidenceOnly
```

The source-content hash and extracted-content hash therefore remain distinct evidence anchors. Solr receives the six upstream NiFi fields unchanged alongside the derived fields. The qualification query reads the record back and verifies every upstream value survived the index round trip.

## Replay and idempotency

The searchable source identity is deliberately narrower than the observation envelope:

```text
sourceEvidenceId = sha256(sourceSystem | sourceObjectId | contentSha256)
```

`receivedAt`, `flowId`, and `correlationId` remain upstream observation evidence. They do not create a new searchable source identity.

The live runner enforces three replay rules:

1. the Solr unique ID is derived only from the stable source identity tuple;
2. replaying the exact same six-field envelope writes the same Solr ID and must still return exactly one record; and
3. if that same source identity arrives with a different six-field observation envelope, the search lane rejects it before update rather than overwriting the original provenance or creating a second searchable source.

That third case is intentionally fail-closed. This slice does not claim an observation ledger. A future observation-history plane may preserve multiple receives/correlations, but it must be introduced explicitly rather than smuggled into general search semantics.

## Live path

```text
synthetic permitted document
  -> pinned NiFi 2.11.0
  -> original bytes staging
  -> immutable six-field NiFi provenance envelope
  -> pinned Tika 4.0.0 extraction
  -> append-only derived evidence
  -> stable sourceEvidenceId
  -> pinned Solr 10.0.0 index
  -> authenticated read-back
  -> exact replay
  -> one-record assertion
  -> divergent-observation rejection
```

NiFi uses two connections on the same success relationship so the FlowFile is cloned: one copy retains the original document bytes, while the other is converted to the six-field provenance JSON. The downstream lane never reconstructs the upstream envelope from Tika or Solr state.

## Negative qualification

The cheap validation lane proves the handoff rejects:

- a changed source object ID;
- a changed flow ID;
- a changed source hash;
- staged bytes that no longer match the source hash;
- a missing required upstream field; and
- provenance aliases such as `documentId` added beside `sourceObjectId`.

These cases are counter-evidence that the happy path is not merely accepting arbitrary downstream normalization.

## Authority boundary

```text
NiFi acceptance
!= source authority

Tika parse success
!= source authenticity

Solr index success
!= source authority

Solr search hit
!= regulatory interpretation
!= policy decision
!= compensability
!= claim approval
```

This lane proves a bounded technical handoff only. It does not establish production pipeline security, protected-record suitability, source authenticity, regulatory completeness, legal interpretation, compensability, claim approval, or an observation-history system.

## Evidence retained

The Actions artifact retains:

- the original NiFi-staged source object;
- the exact NiFi provenance sidecar;
- source-object and envelope SHA-256 values;
- NiFi/Tika/Solr image IDs;
- bounded service logs;
- extracted-content SHA-256;
- stable source-evidence and Solr record IDs;
- upstream round-trip equality results;
- exact replay one-record evidence;
- divergent-observation rejection evidence; and
- explicit non-authority flags.

## Closure condition

This slice is complete when the profile/negative qualification, stale-pin check, and live composed handoff are green for the exact #121/#129 heads above. Once #121 and #129 converge into the same repository tree, remove only the CI-local sibling merge machinery. Keep the six-field upstream envelope, stable source-evidence identity, replay gate, negative qualification, and authority boundaries unchanged.
