#!/usr/bin/env python3
"""Validate portable Baudot causal-proof manifests against the meta-contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "testkit" / "meta" / "causal-proof-contract-v1.json"
MANIFEST_SCHEMA = "baudot.causal-proof-manifest@1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def forward_chain(seed_facts: set[str], rules: list[dict[str, Any]]) -> tuple[set[str], list[dict[str, Any]]]:
    known = set(seed_facts)
    trace: list[dict[str, Any]] = []
    changed = True
    while changed:
        changed = False
        for rule in rules:
            requirements = set(rule["requiresAll"])
            produced = rule["produces"]
            if requirements <= known and produced not in known:
                known.add(produced)
                trace.append(
                    {
                        "rule": rule["id"],
                        "requiresAll": list(rule["requiresAll"]),
                        "produces": produced,
                        "authority": rule["authority"],
                    }
                )
                changed = True
    return known, trace


def resolve_under(root: Path, relative: str, label: str) -> Path:
    require(isinstance(relative, str) and relative, f"{label}: path must be non-empty")
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    require(candidate.is_relative_to(root_resolved), f"{label}: evidence path escapes evidence root")
    return candidate


def load_contract(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    require(document.get("schema") == "baudot.causal-proof-contract@1", "unexpected causal proof contract schema")
    return document


def validate_manifest(manifest_path: Path, contract_path: Path | None = None) -> list[dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("schema") == MANIFEST_SCHEMA, "unexpected causal proof manifest schema")
    require(isinstance(manifest.get("scenarioId"), str) and manifest["scenarioId"], "scenarioId required")
    require(isinstance(manifest.get("correlationId"), str) and manifest["correlationId"], "correlationId required")

    declared_contract = manifest.get("contract", "testkit/meta/causal-proof-contract-v1.json")
    if contract_path is None:
        contract_candidate = resolve_under(ROOT, declared_contract, "contract")
    else:
        contract_candidate = contract_path.resolve()
    contract = load_contract(contract_candidate)

    evidence_root_rel = manifest.get("evidenceRoot", ".")
    require(isinstance(evidence_root_rel, str) and evidence_root_rel, "evidenceRoot must be non-empty")
    evidence_root = (manifest_path.parent / evidence_root_rel).resolve()

    facts = {entry["id"]: entry for entry in contract["facts"]}
    rules = contract["rules"]
    known_nodes = set(facts) | {rule["produces"] for rule in rules}

    proofs = manifest.get("proofs")
    require(isinstance(proofs, list) and proofs, "proofs must be a non-empty list")
    proof_ids: list[str] = []
    summaries: list[dict[str, Any]] = []

    for proof in proofs:
        proof_id = proof.get("id")
        require(isinstance(proof_id, str) and proof_id, "proof id required")
        proof_ids.append(proof_id)

        source_facts = proof.get("sourceFacts")
        require(isinstance(source_facts, list) and source_facts, f"{proof_id}: sourceFacts required")
        source_ids: list[str] = []

        for source in source_facts:
            fact_id = source.get("id")
            authority = source.get("authority")
            require(fact_id in facts, f"{proof_id}: unknown source fact {fact_id!r}")
            require(authority == facts[fact_id]["authority"], f"{proof_id}: authority mismatch for {fact_id}")
            source_ids.append(fact_id)

            evidence = source.get("evidence")
            require(isinstance(evidence, list) and evidence, f"{proof_id}: {fact_id} requires evidence")
            for index, ref in enumerate(evidence):
                label = f"{proof_id}:{fact_id}:evidence[{index}]"
                relative = ref.get("path")
                expected_digest = ref.get("sha256")
                reducer = ref.get("reducer")
                require(isinstance(expected_digest, str) and len(expected_digest) == 64, f"{label}: sha256 required")
                require(isinstance(reducer, str) and reducer, f"{label}: reducer required")
                artifact = resolve_under(evidence_root, relative, label)
                require(artifact.is_file(), f"{label}: missing evidence file {artifact}")
                actual_digest = sha256(artifact)
                require(actual_digest == expected_digest, f"{label}: sha256 mismatch")

        require(len(source_ids) == len(set(source_ids)), f"{proof_id}: duplicate source fact")
        derived, trace = forward_chain(set(source_ids), rules)

        expect_claims = proof.get("expectClaims", [])
        forbid_claims = proof.get("forbidClaims", [])
        require(isinstance(expect_claims, list), f"{proof_id}: expectClaims must be a list")
        require(isinstance(forbid_claims, list), f"{proof_id}: forbidClaims must be a list")
        require(expect_claims or forbid_claims, f"{proof_id}: expected or forbidden claims required")
        require(all(isinstance(claim, str) and claim for claim in expect_claims + forbid_claims),
                f"{proof_id}: claim ids must be non-empty")
        require(not (set(expect_claims) & set(forbid_claims)), f"{proof_id}: claim cannot be expected and forbidden")

        for claim in expect_claims:
            require(claim in known_nodes, f"{proof_id}: unknown expected claim {claim}")
            require(claim in derived, f"{proof_id}: expected claim {claim} is not derivable")
        for claim in forbid_claims:
            require(claim not in derived, f"{proof_id}: forbidden claim {claim} became derivable")

        summaries.append(
            {
                "id": proof_id,
                "sourceFacts": source_ids,
                "expectClaims": expect_claims,
                "forbidClaims": forbid_claims,
                "derivation": trace,
            }
        )

    require(len(proof_ids) == len(set(proof_ids)), "duplicate proof id")
    return summaries


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="baudot-causal-proof-") as tmp:
        tmp_path = Path(tmp)
        evidence = tmp_path / "evidence"
        evidence.mkdir()
        signaling = evidence / "signaling.txt"
        semantic = evidence / "semantic.bin"
        signaling.write_text("replacement.dialog.established=true\nreplacement.rtt.negotiated=true\n", encoding="utf-8")
        semantic.write_bytes(b"H")

        manifest = {
            "schema": MANIFEST_SCHEMA,
            "scenarioId": "SELF-TEST",
            "correlationId": "portable-proof-v1",
            "contract": "testkit/meta/causal-proof-contract-v1.json",
            "evidenceRoot": "evidence",
            "proofs": [
                {
                    "id": "positive",
                    "sourceFacts": [
                        {
                            "id": "replacement.dialog.established",
                            "authority": "baudot-signaling-evidence",
                            "evidence": [{"path": "signaling.txt", "sha256": sha256(signaling), "reducer": "self-test"}],
                        },
                        {
                            "id": "replacement.rtt.negotiated",
                            "authority": "baudot-signaling-evidence",
                            "evidence": [{"path": "signaling.txt", "sha256": sha256(signaling), "reducer": "self-test"}],
                        },
                        {
                            "id": "replacement.t140.semantic.observed",
                            "authority": "baudot-semantic-reducer",
                            "evidence": [{"path": "semantic.bin", "sha256": sha256(semantic), "reducer": "self-test"}],
                        },
                    ],
                    "expectClaims": ["replacement.rtt.ready", "old-leg.safe-to-release"],
                },
                {
                    "id": "negative",
                    "sourceFacts": [
                        {
                            "id": "replacement.dialog.established",
                            "authority": "baudot-signaling-evidence",
                            "evidence": [{"path": "signaling.txt", "sha256": sha256(signaling), "reducer": "self-test"}],
                        },
                        {
                            "id": "replacement.rtt.negotiated",
                            "authority": "baudot-signaling-evidence",
                            "evidence": [{"path": "signaling.txt", "sha256": sha256(signaling), "reducer": "self-test"}],
                        },
                    ],
                    "forbidClaims": ["replacement.rtt.ready", "old-leg.safe-to-release"],
                },
            ],
        }
        manifest_path = tmp_path / "proof.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        summaries = validate_manifest(manifest_path)
        require(len(summaries) == 2, "self-test proof count mismatch")
        print("causal proof manifest self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    require(args.manifest is not None, "manifest path required unless --self-test is used")
    summaries = validate_manifest(args.manifest, args.contract)
    for summary in summaries:
        print(f"proof {summary['id']}:")
        print(f"  source facts: {', '.join(summary['sourceFacts'])}")
        for step in summary["derivation"]:
            print(
                f"  {step['rule']}: "
                f"{' + '.join(step['requiresAll'])} -> {step['produces']} "
                f"[{step['authority']}]"
            )
        if summary["expectClaims"]:
            print(f"  expected: {', '.join(summary['expectClaims'])}")
        if summary["forbidClaims"]:
            print(f"  forbidden: {', '.join(summary['forbidClaims'])}")
    print("causal proof manifest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
