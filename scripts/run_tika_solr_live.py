#!/usr/bin/env python3
"""Exercise the bounded live Tika -> provenance -> Solr document lane."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
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
EXPECTED = {
    "indexed": ("index", []),
    "quarantined-empty-extraction": ("reject", ["empty-extraction"]),
    "rejected-missing-source-hash": ("reject", ["missing-source-hash"]),
    "rejected-forbidden-data": ("reject", ["forbidden-sensitive-field"]),
}


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
            # Tika 4's bare /tika endpoint returns Markdown content but advertises
            # it as text/plain;charset=UTF-8. Asking for text/markdown yields 406.
            "Accept": "text/plain",
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
    if anonymous_status not in (401, 403):
        raise SystemExit(f"Solr anonymous access did not fail closed: HTTP {anonymous_status}")
    evidence["security"]["anonymousSearchStatus"] = anonymous_status

    status, security = request_json(
        f"{args.solr.rstrip('/')}/api/cluster/security/authentication",
        user=args.user,
        password=args.password,
    )
    if status != 200 or find_block_unknown(security) is not True:
        raise SystemExit("effective Solr authentication config does not prove blockUnknown=true")
    evidence["security"]["blockUnknown"] = True

    admitted = []
    rejected_ids = []

    for item in MANIFEST["documents"]:
        document_id = item["documentId"]
        path = FIXTURE_ROOT / item["file"]
        raw = path.read_bytes()
        source_hash = None if item.get("omitSourceHash", False) else sha256_bytes(raw)
        extracted, extracted_hash = extract_tika(args.tika, path)
        has_forbidden = any(pattern.search(extracted) for pattern in FORBIDDEN_PATTERNS)
        parse_nonempty = bool(extracted.strip())

        reasons = []
        if not parse_nonempty:
            reasons.append("empty-extraction")
        if source_hash is None:
            reasons.append("missing-source-hash")
        if has_forbidden:
            reasons.append("forbidden-sensitive-field")

        decision = "index" if not reasons else "reject"
        expected_decision, expected_reasons = EXPECTED[item["expect"]]
        if decision != expected_decision or sorted(reasons) != sorted(expected_reasons):
            raise SystemExit(
                f"fixture {document_id} produced {decision}/{reasons}, "
                f"expected {expected_decision}/{expected_reasons}"
            )

        record = {
            "documentId": document_id,
            "sourceClass": item["sourceClass"],
            "sourceRef": item["sourceRef"],
            "file": item["file"],
            "sourceSha256": source_hash,
            "extractionSha256": extracted_hash,
            "parseNonempty": parse_nonempty,
            "forbiddenSensitiveFieldDetected": has_forbidden,
            "decision": decision,
            "reasons": reasons,
        }
        evidence["documents"].append(record)

        if decision == "index":
            admitted.append(
                {
                    "id": document_id,
                    "documentClass": item["sourceClass"],
                    "sourceRef": item["sourceRef"],
                    "sourceSha256": source_hash,
                    "extractionSha256": extracted_hash,
                    "content": extracted,
                    "derivedEvidenceOnly": True,
                }
            )
        else:
            rejected_ids.append(document_id)

    if admitted:
        status, update = request_json(
            f"{args.solr.rstrip('/')}/solr/baudot_docs/update?commit=true&wt=json",
            method="POST",
            data=admitted,
            user=args.user,
            password=args.password,
        )
        if status != 200 or update.get("responseHeader", {}).get("status") != 0:
            raise SystemExit("Solr update did not succeed")

    all_docs = solr_query(args.solr, "*:*", args.user, args.password)
    returned = all_docs.get("response", {}).get("docs", [])
    returned_ids = {doc["id"] for doc in returned}
    admitted_ids = {doc["id"] for doc in admitted}
    if returned_ids != admitted_ids:
        raise SystemExit(f"Solr returned unexpected document ids: {returned_ids} != {admitted_ids}")
    if returned_ids.intersection(rejected_ids):
        raise SystemExit("rejected fixture became queryable")

    evidence["queries"]["allDocumentIds"] = sorted(returned_ids)
    evidence["queries"]["admittedCount"] = len(returned_ids)
    evidence["queries"]["rejectedIdsAbsent"] = sorted(rejected_ids)

    # Retrieval must preserve provenance hashes and the explicit derived-only marker.
    for doc in returned:
        if not doc.get("sourceSha256") or not doc.get("extractionSha256"):
            raise SystemExit(f"indexed document {doc['id']} lost provenance hashes")
        marker = doc.get("derivedEvidenceOnly")
        if isinstance(marker, list):
            marker = marker[0] if marker else None
        if marker not in (True, "true"):
            raise SystemExit(f"indexed document {doc['id']} lost derived-evidence marker")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"validated live Tika -> Solr lane: admitted={len(admitted_ids)} rejected={len(rejected_ids)}")


if __name__ == "__main__":
    main()
