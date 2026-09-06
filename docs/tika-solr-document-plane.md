# Apache Tika + Solr document/search plane

This profile gives Baudot a bounded document-ingestion and retrieval layer:

```text
permitted document
  -> NiFi staging
  -> Tika extraction / normalization
  -> provenance envelope
  -> Solr index
  -> read-only search
```

The pipeline exists to make public regulatory, technical, and synthetic evidence easier to find. It does not make extracted text or search ranking authoritative.

## Pins

```text
Apache Tika 4.0.0
release commit 514e1b3d8d29726d02ac6a12479d95f5db263379

Apache Solr 10.0.0
release commit 6c6c48a6f78486130682ea9c1f7a2723af5a87be
```

Tika 4.0.0 is the first stable 4.x release. Its default output is Markdown and parsing is moved out of process where possible, which is a good fit for untrusted or malformed document inputs.

Solr 10.0.0 is the current stable release for this profile.

## Security boundary

Solr 10.0.0 has a published JWT-authentication advisory involving the `blockUnknown` default. Baudot therefore requires:

```text
blockUnknown = true
anonymous search disabled
admin surface not public
external protection required
```

A successful Solr query is never evidence that the requester was entitled to see a different protected data source.

## Admitted document classes

The initial general-search index is limited to:

- public rules;
- public orders;
- public guidance;
- public reports;
- public provider documents;
- synthetic contracts; and
- synthetic test evidence.

Production subscriber records, credentials, protected call records, or payment/claim authority data do not belong in this index.

## Provenance

Every admitted extraction preserves a source-level envelope including:

```text
documentId
sourceClass
sourceRef
sourceSha256
receivedAt
mediaType
extractor + extractorVersion
extractedContentSha256
indexVersion
```

The original source hash remains the anchor. Extracted Markdown is a derived representation.

```text
Tika text
!= original source
```

## Solr fields

The initial searchable representation includes:

```text
documentId
sourceClass
sourceRef
sourceSha256
mediaType
title
bodyMarkdown
extractedMetadata
extractorVersion
extractedContentSha256
indexedAt
```

The index explicitly excludes credentials, tokens, subscriber identity/telephone numbers, raw CDRs, and Fund authority fields.

## Authority boundary

```text
Tika parse success
!= source authenticity

Tika extracted text
!= canonical source

Solr index success
!= source authority

Solr search result
!= regulatory interpretation
!= policy decision
!= legal precedence
!= subscriber eligibility
!= compensability
!= claim approval
```

Search should always retain a path back to the original source reference and source hash.

## Synthetic matrix

The test profile covers:

- admitted public rule with complete provenance;
- corrupt/failed parse quarantined rather than indexed as empty truth;
- missing source hash rejected;
- forbidden subscriber/credential data rejected from general search; and
- successful retrieval remaining derived evidence only.

## Relationship to NiFi

NiFi owns bulk movement/staging only. A permitted document drop may arrive through NiFi, but:

```text
NiFi delivery success
!= document admissibility
!= source authenticity
```

Tika extraction and Solr indexing happen only after the source/provenance checks in this profile.

## Next threshold

Boot pinned Tika 4.0.0 and Solr 10.0.0 in an isolated live lane, feed a small synthetic/public fixture corpus, preserve source and extraction hashes, index only admitted records, run exact/hash/full-text queries, and verify failed/forbidden inputs never become searchable documents.

The live lane should also inspect the effective Solr security configuration and fail unless anonymous requests are blocked.

## Sources

- Apache Tika 4.0.0: <https://tika.apache.org/4.0.0/>
- Apache Tika downloads: <https://tika.apache.org/download>
- Apache Solr 10.0.0 downloads: <https://solr.apache.org/downloads>
- Apache Solr security/news: <https://solr.apache.org/news.html>

## Claim boundary

This profile does not establish regulatory completeness, legal interpretation, source authenticity merely from extraction, production search security, protected-record handling approval, or production Tika/Solr suitability.
