#!/usr/bin/env python3
"""Validate Baudot's causal proof / derivation guardrail."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "testkit" / "meta" / "causal-proof-contract-v1.json"

REQUIRED_VOCABULARY = {
    "fact",
    "rule",
    "claim",
    "authority",
    "evidenceReference",
    "derivation",
}
REQUIRED_METHOD = ["define", "derive", "execute", "observe", "prove"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def forward_chain(seed_facts: set[str], rules: list[dict]) -> set[str]:
    """Derive every claim reachable from seed facts under requiresAll rules."""
    known = set(seed_facts)
    changed = True
    while changed:
        changed = False
        for rule in rules:
            requirements = set(rule["requiresAll"])
            produced = rule["produces"]
            if requirements <= known and produced not in known:
                known.add(produced)
                changed = True
    return known


def assert_acyclic(fact_ids: set[str], rules: list[dict]) -> None:
    """Reject rule graphs whose produced claims depend recursively on themselves."""
    produced = {rule["produces"] for rule in rules}
    dependencies = {
        rule["produces"]: {dep for dep in rule["requiresAll"] if dep in produced}
        for rule in rules
    }

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visited:
            return
        require(node not in visiting, f"cyclic derivation detected at {node}")
        visiting.add(node)
        for dependency in dependencies.get(node, set()):
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for claim in produced:
        visit(claim)

    known = fact_ids | produced
    for rule in rules:
        unknown = set(rule["requiresAll"]) - known
        require(not unknown, f"{rule['id']}: unknown dependencies {sorted(unknown)}")


def main() -> int:
    document = json.loads(CONTRACT.read_text(encoding="utf-8"))

    require(document.get("schema") == "baudot.causal-proof-contract@1", "unexpected causal proof schema")
    require(document.get("status") == "experimental", "causal proof contract must remain experimental")
    require(document.get("method") == REQUIRED_METHOD, "proof method drift")
    require(set(document.get("vocabulary", {})) == REQUIRED_VOCABULARY, "causal proof vocabulary drift")

    authorities = document.get("authorities")
    require(isinstance(authorities, list) and authorities, "authorities must be a non-empty list")
    authority_ids = [entry.get("id") for entry in authorities]
    require(all(isinstance(value, str) and value for value in authority_ids), "authority id must be non-empty")
    require(len(authority_ids) == len(set(authority_ids)), "duplicate authority id")
    authority_set = set(authority_ids)

    facts = document.get("facts")
    require(isinstance(facts, list) and facts, "facts must be a non-empty list")
    fact_ids = [entry.get("id") for entry in facts]
    require(all(isinstance(value, str) and value for value in fact_ids), "fact id must be non-empty")
    require(len(fact_ids) == len(set(fact_ids)), "duplicate fact id")
    fact_set = set(fact_ids)
    for fact in facts:
        require(fact.get("authority") in authority_set, f"{fact['id']}: unknown fact authority")
        require(fact.get("evidenceRequired") is True, f"{fact['id']}: source fact must require evidence")

    rules = document.get("rules")
    require(isinstance(rules, list) and rules, "rules must be a non-empty list")
    rule_ids = [rule.get("id") for rule in rules]
    require(all(isinstance(value, str) and value for value in rule_ids), "rule id must be non-empty")
    require(len(rule_ids) == len(set(rule_ids)), "duplicate rule id")

    produced = [rule.get("produces") for rule in rules]
    require(all(isinstance(value, str) and value for value in produced), "produced claim must be non-empty")
    require(len(produced) == len(set(produced)), "each derived claim must have one canonical rule")
    require(not (fact_set & set(produced)), "a source fact cannot also be a derived claim")

    for rule in rules:
        dependencies = rule.get("requiresAll")
        require(isinstance(dependencies, list) and dependencies, f"{rule['id']}: requiresAll must be non-empty")
        require(len(dependencies) == len(set(dependencies)), f"{rule['id']}: duplicate dependency")
        require(rule["produces"] not in dependencies, f"{rule['id']}: self dependency")
        require(rule.get("authority") in authority_set, f"{rule['id']}: unknown claim authority")

    assert_acyclic(fact_set, rules)

    forbidden = document.get("forbiddenPromotions")
    require(isinstance(forbidden, list) and forbidden, "forbiddenPromotions must be non-empty")
    forbidden_pairs: set[tuple[tuple[str, ...], str]] = set()
    rule_by_claim = {rule["produces"]: rule for rule in rules}
    known_nodes = fact_set | set(produced)

    for item in forbidden:
        source = item.get("fromOnly")
        target = item.get("to")
        reason = item.get("reason")
        require(isinstance(source, list) and source, "forbidden promotion needs fromOnly facts/claims")
        require(len(source) == len(set(source)), "duplicate forbidden-promotion source")
        require(all(node in known_nodes for node in source), f"unknown forbidden-promotion source: {source}")
        require(isinstance(target, str) and target, "forbidden promotion needs target")
        require(isinstance(reason, str) and reason, f"{target}: forbidden promotion needs reason")
        key = (tuple(sorted(source)), target)
        require(key not in forbidden_pairs, f"duplicate forbidden promotion {key}")
        forbidden_pairs.add(key)

        # If Baudot does have a rule for this target, the forbidden source set
        # must be insufficient by itself. A stronger rule may require it plus
        # additional independent evidence.
        if target in rule_by_claim:
            requirements = set(rule_by_claim[target]["requiresAll"])
            require(
                not requirements <= set(source),
                f"{target}: canonical rule is satisfied by a forbidden weaker source set",
            )

    fixtures = document.get("derivationFixtures")
    require(isinstance(fixtures, dict), "derivationFixtures must be an object")
    valid = fixtures.get("valid")
    invalid = fixtures.get("invalid")
    require(isinstance(valid, list) and valid, "valid derivation fixtures required")
    require(isinstance(invalid, list) and invalid, "invalid derivation fixtures required")

    fixture_ids: list[str] = []
    for fixture in valid:
        fixture_ids.append(fixture.get("id"))
        seeds = set(fixture.get("facts", []))
        require(seeds <= fact_set, f"{fixture.get('id')}: valid fixture contains unknown source fact")
        derived = forward_chain(seeds, rules)
        expected = fixture.get("expectClaim")
        require(expected in derived, f"{fixture.get('id')}: expected claim {expected} was not derivable")

    for fixture in invalid:
        fixture_ids.append(fixture.get("id"))
        seeds = set(fixture.get("facts", []))
        require(seeds <= fact_set, f"{fixture.get('id')}: invalid fixture contains unknown source fact")
        derived = forward_chain(seeds, rules)
        attempted = fixture.get("attemptedClaim")
        require(attempted not in derived, f"{fixture.get('id')}: forbidden stronger claim became derivable")

    require(all(isinstance(value, str) and value for value in fixture_ids), "fixture id must be non-empty")
    require(len(fixture_ids) == len(set(fixture_ids)), "duplicate derivation fixture id")

    boundary = document.get("claimBoundary", {})
    require(boundary.get("repositoryArchitectureGuardrail") is True, "contract must remain an architecture guardrail")
    for excluded in (
        "generalTheoremProver",
        "protocolConformance",
        "productionAccessibilityReadiness",
        "productionRoutingAuthority",
        "productionFundAuthority",
    ):
        require(boundary.get(excluded) is False, f"forbidden positive claim boundary: {excluded}")

    print(f"validated {len(facts)} evidence-bearing facts")
    print(f"validated {len(rules)} acyclic derivation rules")
    print(f"validated {len(forbidden)} forbidden claim promotions")
    print(f"validated {len(valid)} positive and {len(invalid)} negative derivation fixtures")
    print("define -> derive -> execute -> observe -> prove")
    print("causal proof contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
