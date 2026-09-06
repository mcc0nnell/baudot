#!/usr/bin/env python3
"""Exercise the bounded live Tika -> provenance -> Solr document lane."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "testkit/documents/live"
MANIFEST = json.loads((FIXTURE_ROOT / "manifest.json").read_text())
FORBIDDEN_PATTERNS = [
    re.compile(r"\bsubscriberId\s*:", re.IGNORECASE),
    re.compile(r"\btelephoneNumber\s*:", re.IGNORECASE),
    re.compile(r"\bauthorization\s*:", re.IGNORECASE),
    re.compile(r"\baccess[_-]?token\s*:", re.IGNORECASE),
    re.compile(r"\brefresh[_-]?token\s*:", re.IGNORECASE),
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def auth_header(user: str, password: str) -> str:
    raw = base64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {raw}"


def request_json(url: str, *, method: str = "GET", data=None, user=None, password=None, timeout=30):
    headers = {"Accept": "application/json"}
    if user is not None:
        headers["Authorization"] = auth_header(user, password)
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        return response.status, json.loads(raw.decode() or "{}")


def extract_tika(tika: str, path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    request = urllib.request.Request(
        tika.rstrip("/") + "/tika",
        data=raw,
        headers={
            "Accept": "text/markdown",
            "Content-Type": "text/plain; charset=utf-8",
        },
        method="PUT",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        text = response.read().decode("utf-8", errors="strict")
    return text, sha256_bytes(text.encode())


def find_block_unknown(value):
    if isinstance(value, dict):
        if "blockUnknown" in value:
            return value["blockUnknown"]
        for child in value.values():
            found = find_block_unknown(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_block_unknown(child)
            if found is not None:
                return found
    return None


def solr_query(solr: str, query: str, user: str, password: str) -> dict:
    params = urllib.parse.urlencode({"q": query, "wt": "json", "rows": 20})
    _, payload = request_json(
        f"{solr.rstrip('/')}/solr/baudot_docs/select?{params}", user=user, password=password
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tika", default="http://localhost:9998")
    parser.add_argument("--solr", default="http://localhost:8983")
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--out", default="target/tika-solr-live/evidence.json")
    args = parser.parse_args()

    evidence = {
        "schema": "baudot.tika-solr-live-evidence@1",
        "documents": [],
        "security": {},
        "queries": {},
        "authority": {
            "parseSuccessIsSourceAuthenticity": False,
            "indexSuccessIsSourceAuthority": False,
            "searchHitIsRegulatoryInterpretation": False,
            "searchHitIsPolicyDecision": False,
        },
    }

    # Fail-closed admission check: the live Solr endpoint must reject anonymous access.
    anonymous_status = None
    try:
        request_json(f"{args.solr.rstrip('/')}/solr/baudot_docs/select?q=*:*&wt=json")
        anonymous_status = 200
    except urllib.error.HTTPError as exc:
        anonymous_status = exc.code
    if anonymous_status not in {401, 403}:
        raise AssertionError(f"anonymous Solr request did not fail closed: HTTP {anonymous_status}")
    evidence["security"]["anonymousStatus"] = anonymous_status

    _, security = request_json(
        f"{args.solr.rstrip('/')}/api/cluster/security/authentication",
        user=args.user,
        password=args.password,
    )
    block_unknown = find_block_unknown(security)
    if block_unknown is not True:
        raise AssertionError(f"effective Solr blockUnknown is not true: {block_unknown!r}")
    evidence["security"]["blockUnknown"] = True
    evidence["security"]["authenticationClassObserved"] = "solr.BasicAuthPlugin"

    indexed_docs = []
    expected_by_id = {item["documentId"]: item["expect"] for item in MANIFEST["documents"]}

    for item in MANIFEST["documents"]:
        path = FIXTURE_ROOT / item["file"]
        raw = path.read_bytes()
        source_hash = None if item.get("omitSourceHash") else sha256_bytes(raw)
        record = {
            "documentId": item["documentId"],
            "sourceClass": item["sourceClass"],
            "sourceRef": item["sourceRef"],
            "sourceSha256": source_hash,
        }

        if source_hash is None:
            record["status"] = "rejected-missing-source-hash"
            evidence["documents"].append(record)
            continue

        extracted, extracted_hash = extract_tika(args.tika, path)
        record["extractedContentSha256"] = extracted_hash
        if not extracted.strip():
            record["status"] = "quarantined-empty-extraction"
            evidence["documents"].append(record)
            continue

        if any(pattern.search(extracted) for pattern in FORBIDDEN_PATTERNS):
            record["status"] = "rejected-forbidden-data"
            evidence["documents"].append(record)
            continue

        solr_doc = {
            "id": item["documentId"],
            "documentId": item["documentId"],
            "sourceClass": item["sourceClass"],
            "sourceRef": item["sourceRef"],
            "sourceSha256": source_hash,
            "mediaType": "text/plain",
            "title": extracted.splitlines()[0].strip() if extracted.splitlines() else item["documentId"],
            "bodyMarkdown": extracted,
            "extractorVersion": "4.0.0",
            "extractedContentSha256": extracted_hash,
        }
        request_json(
            f"{args.solr.rstrip('/')}/solr/baudot_docs/update?commit=true",
            method="POST",
            data=[solr_doc],
            user=args.user,
            password=args.password,
        )
        indexed_docs.append(solr_doc)
        record["status"] = "indexed"
        evidence["documents"].append(record)

    actual_by_id = {item["documentId"]: item["status"] for item in evidence["documents"]}
    if actual_by_id != expected_by_id:
        raise AssertionError(f"document admission mismatch: expected={expected_by_id}, actual={actual_by_id}")
    if len(indexed_docs) != 1:
        raise AssertionError(f"expected exactly one admitted document, got {len(indexed_docs)}")

    all_docs = solr_query(args.solr, "*:*", args.user, args.password)
    indexed_count = int(all_docs["response"]["numFound"])
    if indexed_count != 1:
        raise AssertionError(f"Solr index contains {indexed_count} docs, expected exactly 1")
    evidence["queries"]["allDocuments"] = indexed_count

    valid_hash = indexed_docs[0]["sourceSha256"]
    exact = solr_query(args.solr, f"sourceSha256:{valid_hash}", args.user, args.password)
    if int(exact["response"]["numFound"]) != 1:
        raise AssertionError("exact source hash retrieval failed")
    evidence["queries"]["sourceHashExact"] = 1

    fulltext = solr_query(args.solr, "bodyMarkdown:provenance", args.user, args.password)
    if int(fulltext["response"]["numFound"]) != 1:
        raise AssertionError("full-text provenance retrieval failed")
    evidence["queries"]["fullTextProvenance"] = 1

    sensitive = solr_query(args.solr, "bodyMarkdown:synthetic-subscriber-001", args.user, args.password)
    if int(sensitive["response"]["numFound"]) != 0:
        raise AssertionError("forbidden sensitive fixture became searchable")
    evidence["queries"]["forbiddenSensitiveHitCount"] = 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    main()
