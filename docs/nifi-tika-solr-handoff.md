# NiFi -> Tika -> Solr provenance-preserving handoff

This qualification slice composes the live NiFi bulk-ingest and Tika/Solr document-search lanes without making either plane authoritative for the other.

## Composition pins

The CI lane deliberately composes the exact current sibling heads instead of merging their pull requests into the shared integration branch just to run a test:

```text
common base   65723f8c6f566f092ebdd4a3901cf8743ca5a0bc
NiFi #121     bf6ffa25423c9107ef3b1ca546bc14f7574116bf
Tika/Solr #129 9df3f208cc126d070060f495295c1babbedf6cb6
```

Those trees are merged only inside the Actions worktree. The repository branch topology remains unchanged.

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

The NiFi-emitted provenance JSON is treated as an immutable input artifact. Its bytes are hashed before Tika parsing and checked again after Solr indexing.

The original staged document bytes are likewise checked before and after downstream processing.

## Append-only downstream evidence

Tika and Solr may add only derived extraction/index evidence:

```text
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

The source-content hash and extracted-content hash therefore remain distinct evidence anchors.

Solr receives the six upstream NiFi fields unchanged alongside the derived fields. The qualification query reads the record back and verifies every upstream value survived the index round trip.

## Live path

```text
synthetic permitted document
  -> pinned NiFi 2.11.0
  -> original bytes staging
  -> immutable six-field NiFi provenance envelope
  -> pinned Tika 4.0.0 extraction
  -> append-only derived evidence
  -> pinned Solr 10.0.0 index
  -> authenticated read-back
  -> upstream field equality check
```

NiFi uses two connections on the same success relationship so the FlowFile is cloned: one copy retains the original document bytes, while the other is converted to the six-field provenance JSON. The downstream lane never reconstructs the upstream envelope from Tika or Solr state.

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

This lane proves a bounded technical handoff only. It does not establish production pipeline security, protected-record suitability, source authenticity, regulatory completeness, or legal interpretation.

## Evidence retained

The Actions artifact retains:

- the original NiFi-staged source object;
- the exact NiFi provenance sidecar;
- source-object and envelope SHA-256 values;
- NiFi/Tika/Solr image IDs;
- bounded service logs;
- extracted-content SHA-256;
- Solr index record ID;
- upstream round-trip equality results; and
- explicit non-authority flags.

Once #121 and #129 converge into the same repository tree, the CI-local merge step can be removed without changing the handoff contract or evidence assertions.
