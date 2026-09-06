#!/usr/bin/env python3
"""Compose one live NiFi document handoff into the pinned Tika/Solr lane."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from run_nifi_live import (
    NiFiClient,
    connect,
    create_group,
    create_processor,
    processor_bundles,
    set_group_state,
)
from run_tika_solr_live import extract_tika, find_block_unknown, request_json, solr_query

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "testkit" / "documents" / "live" / "public-rule.txt"
REQUIRED_UPSTREAM = [
    "sourceSystem",
    "sourceObjectId",
    "receivedAt",
    "contentSha256",
    "flowId",
    "correlationId",
]
SOURCE_IDENTITY = ["sourceSystem", "sourceObjectId", "contentSha256"]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_evidence_id(upstream: dict[str, object]) -> str:
    material = "|".join(str(upstream[field]) for field in SOURCE_IDENTITY).encode()
    return "source-" + sha256_bytes(material)[:32]


def ensure_replay_compatible(existing: dict[str, object], candidate: dict[str, object]) -> None:
    for field in SOURCE_IDENTITY:
        if str(scalar(existing.get(field))) != str(candidate[field]):
            raise RuntimeError(f"source identity collision on {field}")
    changed = [
        field
        for field in REQUIRED_UPSTREAM
        if str(scalar(existing.get(field))) != str(candidate[field])
    ]
    if changed:
        raise RuntimeError(
            "same source evidence arrived with a different observation envelope: "
            + ",".join(changed)
        )


def prepare_root(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for child in root.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    for relative in ("input/document", "staged/document", "staged/envelope", "quarantine/document"):
        path = root / relative
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o777)
    shutil.copy2(SOURCE, root / "input" / "document" / SOURCE.name)


def build_document_handoff(client: NiFiClient, group_id: str, bundles: dict) -> dict[str, str]:
    standard = "org.apache.nifi.processors.standard."
    get_file = create_processor(
        client,
        group_id,
        bundles,
        standard + "GetFile",
        "document-GetFile",
        0,
        200,
        properties={
            "Input Directory": "/data/input/document",
            "Recurse Subdirectories": "false",
            "Keep Source File": "false",
            "Polling Interval": "250 ms",
            "Batch Size": "1",
        },
        auto_terminate=[],
    )
    hasher = create_processor(
        client,
        group_id,
        bundles,
        standard + "CryptographicHashContent",
        "document-SHA256",
        250,
        200,
        properties={"Hash Algorithm": "SHA-256", "Fail When Content Empty": "false"},
        auto_terminate=[],
    )
    evidence = create_processor(
        client,
        group_id,
        bundles,
        "org.apache.nifi.processors.attributes.UpdateAttribute",
        "document-UpstreamEvidence",
        500,
        200,
        properties={
            "sourceSystem": "synthetic-permitted-document-drop",
            "sourceObjectId": "${filename}",
            "receivedAt": "epoch-ms:${now():toNumber()}",
            "contentSha256": "${'content_SHA-256'}",
            "flowId": "document-drop-ingest",
            "correlationId": "${uuid}",
        },
        auto_terminate=[],
    )
    raw_stage = create_processor(
        client,
        group_id,
        bundles,
        standard + "PutFile",
        "document-RawStaging",
        850,
        100,
        properties={
            "Directory": "/data/staged/document",
            "Conflict Resolution Strategy": "replace",
            "Create Missing Directories": "true",
        },
        auto_terminate=["success", "failure"],
    )
    attributes_json = create_processor(
        client,
        group_id,
        bundles,
        standard + "AttributesToJSON",
        "document-ProvenanceEnvelope",
        800,
        300,
        properties={
            "Attributes List": ",".join(REQUIRED_UPSTREAM),
            "Destination": "flowfile-content",
            "Include Core Attributes": "false",
        },
        auto_terminate=[],
    )
    rename = create_processor(
        client,
        group_id,
        bundles,
        "org.apache.nifi.processors.attributes.UpdateAttribute",
        "document-ProvenanceFilename",
        1050,
        300,
        properties={"filename": "${filename}.provenance.json"},
        auto_terminate=[],
    )
    envelope_stage = create_processor(
        client,
        group_id,
        bundles,
        standard + "PutFile",
        "document-ProvenanceStaging",
        1300,
        300,
        properties={
            "Directory": "/data/staged/envelope",
            "Conflict Resolution Strategy": "replace",
            "Create Missing Directories": "true",
        },
        auto_terminate=["success", "failure"],
    )
    quarantine = create_processor(
        client,
        group_id,
        bundles,
        standard + "PutFile",
        "document-Quarantine",
        1050,
        500,
        properties={
            "Directory": "/data/quarantine/document",
            "Conflict Resolution Strategy": "replace",
            "Create Missing Directories": "true",
        },
        auto_terminate=["success", "failure"],
    )

    connect(client, group_id, get_file, hasher, "success", "document-read-to-hash")
    connect(client, group_id, hasher, evidence, "success", "document-hash-to-evidence")
    connect(client, group_id, hasher, quarantine, "failure", "document-hash-failure-quarantine")
    connect(client, group_id, evidence, raw_stage, "success", "document-evidence-to-raw-staging")
    connect(client, group_id, evidence, attributes_json, "success", "document-evidence-to-envelope")
    connect(client, group_id, attributes_json, rename, "success", "document-envelope-to-rename")
    connect(client, group_id, attributes_json, quarantine, "failure", "document-envelope-failure-quarantine")
    connect(client, group_id, rename, envelope_stage, "success", "document-envelope-to-staging")
    return {
        "getFile": get_file["id"],
        "hash": hasher["id"],
        "evidence": evidence["id"],
        "rawStage": raw_stage["id"],
        "attributesToJson": attributes_json["id"],
        "envelopeStage": envelope_stage["id"],
        "quarantine": quarantine["id"],
    }


def wait_for(path: Path, timeout: int = 90) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(1)
    raise RuntimeError(f"timed out waiting for {path}")


def scalar(value):
    if isinstance(value, list):
        if len(value) != 1:
            raise RuntimeError(f"expected one Solr value, got {value!r}")
        return value[0]
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nifi", default="https://127.0.0.1:8443")
    parser.add_argument("--nifi-user", required=True)
    parser.add_argument("--nifi-password", required=True)
    parser.add_argument("--tika", default="http://127.0.0.1:9998")
    parser.add_argument("--solr", default="http://127.0.0.1:8983")
    parser.add_argument("--solr-user", required=True)
    parser.add_argument("--solr-password", required=True)
    parser.add_argument("--data-root", default="target/nifi-tika-solr-handoff/nifi")
    parser.add_argument("--out", default="target/nifi-tika-solr-handoff/evidence.json")
    args = parser.parse_args()

    root = Path(args.data_root).resolve()
    prepare_root(root)
    source_bytes = SOURCE.read_bytes()
    source_sha = sha256_bytes(source_bytes)

    client = NiFiClient(args.nifi, args.nifi_user, args.nifi_password)
    bundles = processor_bundles(client)
    group_id = create_group(client)["id"]
    processors = build_document_handoff(client, group_id, bundles)

    raw_path = root / "staged" / "document" / SOURCE.name
    envelope_path = root / "staged" / "envelope" / f"{SOURCE.name}.provenance.json"
    set_group_state(client, group_id, "RUNNING")
    try:
        wait_for(raw_path)
        wait_for(envelope_path)
    finally:
        set_group_state(client, group_id, "STOPPED")

    raw_before = raw_path.read_bytes()
    envelope_before = envelope_path.read_bytes()
    upstream = json.loads(envelope_before)
    if set(upstream) != set(REQUIRED_UPSTREAM):
        raise RuntimeError(f"NiFi envelope fields changed: {sorted(upstream)}")
    if any(not upstream[field] for field in REQUIRED_UPSTREAM):
        raise RuntimeError("NiFi envelope contains an empty required provenance field")
    if raw_before != source_bytes or sha256_bytes(raw_before) != source_sha:
        raise RuntimeError("NiFi changed the original document bytes")
    if upstream["sourceObjectId"] != SOURCE.name:
        raise RuntimeError("NiFi sourceObjectId no longer identifies the original object")
    if upstream["contentSha256"] != source_sha:
        raise RuntimeError("NiFi contentSha256 does not match the staged source bytes")
    if upstream["flowId"] != "document-drop-ingest":
        raise RuntimeError("NiFi flowId changed at the document handoff")

    anonymous_status = None
    try:
        request_json(f"{args.solr.rstrip('/')}/solr/baudot_docs/select?q=*:*&wt=json")
        anonymous_status = 200
    except urllib.error.HTTPError as exc:
        anonymous_status = exc.code
    if anonymous_status not in (401, 403):
        raise RuntimeError(f"Solr anonymous access did not fail closed: HTTP {anonymous_status}")
    status, security = request_json(
        f"{args.solr.rstrip('/')}/api/cluster/security/authentication",
        user=args.solr_user,
        password=args.solr_password,
    )
    if status != 200 or find_block_unknown(security) is not True:
        raise RuntimeError("effective Solr authentication config does not prove blockUnknown=true")

    extracted, extracted_sha, parser_status = extract_tika(args.tika, raw_path)
    if extracted is None or not extracted.strip() or extracted_sha is None:
        raise RuntimeError("Tika did not produce a non-empty extraction for the admitted handoff")

    source_id = source_evidence_id(upstream)
    index_record_id = source_id
    indexed_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    indexed = {
        "id": index_record_id,
        "sourceEvidenceId": source_id,
        "indexRecordId": index_record_id,
        **upstream,
        "extractor": "apache-tika",
        "extractorVersion": "4.0.0",
        "parserHttpStatus": str(parser_status),
        "extractedContentSha256": extracted_sha,
        "indexVersion": "solr-10.0.0/baudot_docs",
        "indexedAt": indexed_at,
        "content": extracted,
        "derivedEvidenceOnly": True,
    }

    existing_result = solr_query(args.solr, f'id:"{index_record_id}"', args.solr_user, args.solr_password)
    existing_docs = existing_result.get("response", {}).get("docs", [])
    if len(existing_docs) > 1:
        raise RuntimeError("source evidence identity already resolves to multiple Solr records")
    if existing_docs:
        ensure_replay_compatible(existing_docs[0], upstream)

    status, update = request_json(
        f"{args.solr.rstrip('/')}/solr/baudot_docs/update?commit=true&wt=json",
        method="POST",
        data=[indexed],
        user=args.solr_user,
        password=args.solr_password,
    )
    if status != 200 or update.get("responseHeader", {}).get("status") != 0:
        raise RuntimeError("Solr update did not succeed")

    result = solr_query(args.solr, f'id:"{index_record_id}"', args.solr_user, args.solr_password)
    docs = result.get("response", {}).get("docs", [])
    if len(docs) != 1:
        raise RuntimeError(f"expected one Solr handoff record, got {len(docs)}")
    returned = docs[0]
    for field in REQUIRED_UPSTREAM:
        if str(scalar(returned.get(field))) != str(upstream[field]):
            raise RuntimeError(f"Solr round trip changed upstream field {field}")
    if str(scalar(returned.get("sourceEvidenceId"))) != source_id:
        raise RuntimeError("Solr round trip lost stable source evidence id")
    if str(scalar(returned.get("extractedContentSha256"))) != extracted_sha:
        raise RuntimeError("Solr round trip lost extracted-content hash")
    marker = scalar(returned.get("derivedEvidenceOnly"))
    if marker not in (True, "true"):
        raise RuntimeError("Solr round trip lost derived-evidence marker")

    replay_status, replay_update = request_json(
        f"{args.solr.rstrip('/')}/solr/baudot_docs/update?commit=true&wt=json",
        method="POST",
        data=[indexed],
        user=args.solr_user,
        password=args.solr_password,
    )
    if replay_status != 200 or replay_update.get("responseHeader", {}).get("status") != 0:
        raise RuntimeError("exact replay update did not succeed")
    replay_result = solr_query(args.solr, f'id:"{index_record_id}"', args.solr_user, args.solr_password)
    replay_docs = replay_result.get("response", {}).get("docs", [])
    if len(replay_docs) != 1:
        raise RuntimeError(f"exact replay forked source evidence into {len(replay_docs)} records")

    divergent = dict(upstream)
    divergent["receivedAt"] = str(upstream["receivedAt"]) + "-reobserved"
    divergent["correlationId"] = str(upstream["correlationId"]) + "-reobserved"
    if source_evidence_id(divergent) != source_id:
        raise RuntimeError("observation-only changes altered stable source identity")
    divergent_rejected = False
    try:
        ensure_replay_compatible(returned, divergent)
    except RuntimeError:
        divergent_rejected = True
    if not divergent_rejected:
        raise RuntimeError("same source with divergent observation envelope was not rejected")

    raw_after = raw_path.read_bytes()
    envelope_after = envelope_path.read_bytes()
    if raw_after != raw_before:
        raise RuntimeError("downstream processing rewrote the NiFi-staged source object")
    if envelope_after != envelope_before:
        raise RuntimeError("downstream processing rewrote the NiFi provenance envelope")

    evidence = {
        "schema": "baudot.nifi-tika-solr-live-handoff-evidence@1",
        "processGroupId": group_id,
        "processors": processors,
        "upstream": upstream,
        "upstreamEnvelopeSha256": sha256_bytes(envelope_before),
        "upstreamEnvelopeUnchanged": True,
        "rawSourceSha256": source_sha,
        "rawBytesPreserved": True,
        "contentHashMatched": True,
        "derived": {
            "extractor": "apache-tika",
            "extractorVersion": "4.0.0",
            "parserHttpStatus": parser_status,
            "extractedContentSha256": extracted_sha,
            "sourceEvidenceId": source_id,
            "indexRecordId": index_record_id,
            "indexVersion": "solr-10.0.0/baudot_docs",
            "indexedAt": indexed_at,
            "derivedEvidenceOnly": True,
        },
        "replay": {
            "sourceIdentityFields": SOURCE_IDENTITY,
            "exactReplayRecordCount": len(replay_docs),
            "exactReplayIdempotent": True,
            "sameSourceDifferentEnvelopeRejected": divergent_rejected,
            "observationLedgerClaimed": False,
        },
        "indexRoundTripPreservedUpstream": True,
        "security": {
            "anonymousSearchStatus": anonymous_status,
            "blockUnknown": True,
        },
        "authority": {
            "nifiAcceptanceIsSourceAuthority": False,
            "tikaParseSuccessIsSourceAuthenticity": False,
            "solrIndexSuccessIsSourceAuthority": False,
            "solrSearchHitIsRegulatoryInterpretation": False,
            "solrSearchHitIsPolicyDecision": False,
            "handoffSuccessIsCompensability": False,
            "handoffSuccessIsClaimApproval": False,
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("validated live NiFi -> Tika -> Solr provenance-preserving replay-safe handoff")


if __name__ == "__main__":
    main()
