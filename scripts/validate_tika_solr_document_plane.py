#!/usr/bin/env python3
"""Validate the bounded Tika -> Solr document/search profile."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / "testkit/business/tika-solr-document-plane-v1.json").read_text())


def require(name: str, actual, expected=True) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"PASS {name}: {actual!r}")


def main() -> None:
    require("schema", PROFILE["schema"], "baudot.tika-solr-document-plane@1")

    tika = PROFILE["tika"]
    require("Tika version", tika["version"], "4.0.0")
    require("Tika release commit", tika["releaseCommit"], "514e1b3d8d29726d02ac6a12479d95f5db263379")
    require("Tika markdown output", tika["defaultOutput"], "markdown")
    require("Tika parse isolation", tika["parsingIsolation"], "out-of-process")

    solr = PROFILE["solr"]
    require("Solr version", solr["version"], "10.0.0")
    require("Solr release commit", solr["releaseCommit"], "6c6c48a6f78486130682ea9c1f7a2723af5a87be")
    security = solr["security"]
    require("Solr no public admin", security["publicAdminSurfaceAllowed"], False)
    require("Solr anonymous search disabled", security["anonymousSearchAllowed"], False)
    require("Solr JWT blockUnknown true", security["jwtBlockUnknownMustBeTrue"], True)
    require("Solr external protection", security["externalProtectionRequired"], True)

    envelope = PROFILE["provenanceEnvelope"]
    fields = set(envelope["fields"])
    forbidden = set(envelope["forbiddenFields"])
    require("provenance fields exclude forbidden", fields.isdisjoint(forbidden), True)
    for required in {"documentId", "sourceRef", "sourceSha256", "extractorVersion", "extractedContentSha256"}:
        require(f"provenance has {required}", required in fields, True)

    solr_fields = set(PROFILE["solrFields"])
    require("Solr index excludes forbidden", solr_fields.isdisjoint(forbidden), True)
    for required in {"documentId", "sourceRef", "sourceSha256", "bodyMarkdown", "extractedContentSha256"}:
        require(f"Solr field has {required}", required in solr_fields, True)

    for key, value in PROFILE["authorityBoundary"].items():
        require(f"non-authority {key}", value, False)

    ids = [case["id"] for case in PROFILE["cases"]]
    require("case ids", ids, [f"DOC-{index:03d}" for index in range(1, 6)])

    for case in PROFILE["cases"]:
        should_index = bool(
            case["sourceClass"] in PROFILE["admittedDocumentClasses"]
            and case["sourceSha256Present"]
            and case["parseSucceeded"]
            and case["provenanceComplete"]
            and not case["containsForbiddenData"]
        )
        require(case["id"], should_index, case["expectIndexed"])

    for key, value in PROFILE["claimBoundary"].items():
        require(f"claim boundary {key}", value, False)

    print("Baudot Tika -> Solr document plane: PASS")


if __name__ == "__main__":
    main()
