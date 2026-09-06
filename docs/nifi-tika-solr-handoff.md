# NiFi -> Tika -> Solr provenance-preserving handoff

This qualification slice composes the live NiFi bulk-ingest and Tika/Solr document-search lanes without making either plane authoritative for the other.

## Converged composition evidence

The two prerequisite lanes were qualified at exact heads and then merged into the shared integration tree:

```text
common base                65723f8c6f566f092ebdd4a3901cf8743ca5a0bc
NiFi #121 qualified head   bf6ffa25423c9107ef3b1ca546bc14f7574116bf
NiFi #121 merge commit     783b038c8b750af617a12e6befba287ce65b13c2
Tika/Solr #129 head        9df3f208cc126d070060f495295c1babbedf6cb6
Tika/Solr #129 merge       134e7512dab2393cc9be5a307952a4e9f2857594
```

The handoff workflow now runs directly against that converged repository tree. The former CI-local sibling fetch/merge machinery and stale-pin workflow have been removed. The exact qualified heads and merge commits remain in the profile as historical evidence.

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

The NiFi-emitted provenance JSON is an immutable input artifact. Its bytes are hashed before Tika parsing and checked again after Solr indexing. The original staged document bytes are likewise checked before and after downstream processing.

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

The source-content hash and extracted-content hash remain distinct evidence anchors. Solr receives the six upstream NiFi fields unchanged alongside derived fields, and the qualification query proves every upstream value survives the index round trip.

## Replay and idempotency

The searchable source identity is deliberately narrower than the observation envelope:

```text
sourceEvidenceId = sha256(sourceSystem | sourceObjectId | contentSha256)
```

`receivedAt`, `flowId`, and `correlationId` remain upstream observation evidence. They do not create a new searchable source identity.

The live runner enforces three replay rules:

1. the Solr unique ID is derived only from the stable source identity tuple;
2. replaying the exact same six-field envelope writes the same Solr ID and must still return exactly one record; and
3. if the same source identity arrives with a different six-field observation envelope, the search lane rejects it before update instead of overwriting provenance or creating a second searchable source.

That third case is intentionally fail-closed. This slice does not claim an observation ledger. Multiple receive/correlation observations require a separate explicit evidence plane.

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

These cases provide counter-evidence that the happy path is not merely accepting arbitrary downstream normalization.

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

## Done boundary

This slice is done when the converged-tree profile and negative qualification are green and the live NiFi -> Tika -> Solr workflow proves provenance preservation, fail-closed mutation handling, exact-replay idempotency, divergent-observation rejection, fail-closed Solr authentication, retained evidence, and explicit non-authority boundaries on the real repository tree.

Ranger authorization, Shiro user/session authentication, iTRS authority, TRS business authority, compensability, and claim/payment decisions are separate composition boundaries. They do not reopen this handoff slice.
