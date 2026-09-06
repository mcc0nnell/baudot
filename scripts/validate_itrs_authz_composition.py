#!/usr/bin/env python3
"""Validate the composed APISIX -> Shiro -> Ranger -> iTRS authority boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "testkit" / "business" / "itrs-authz-composition-v1.json"
BUSINESS_PATH = ROOT / "testkit" / "business" / "trs-business-authority-v1.json"
EVIDENCE_PATH = ROOT / "target" / "itrs-authz-composition" / "evidence.json"

DECISION_ORDER = [
    "gatewayAuthentication",
    "applicationAuthentication",
    "rangerAuthorization",
    "protocolValidity",
    "trsBusinessAuthority",
]

PASS_VALUES = {
    "gatewayAuthentication": "ADMIT",
    "applicationAuthentication": "AUTHENTICATED",
    "rangerAuthorization": "ALLOW",
    "protocolValidity": "VALID",
    "trsBusinessAuthority": "ALLOW",
}

FAIL_VALUES = {
    "gatewayAuthentication": "DENY",
    "applicationAuthentication": "DENY",
    "rangerAuthorization": "DENY",
    "protocolValidity": "INVALID",
    "trsBusinessAuthority": "DENY",
}


def require(name: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"PASS {name}: {actual}")


def validate_declared_inputs(contract: dict[str, Any], business: dict[str, Any]) -> None:
    require("composition schema", contract["schema"], "baudot.itrs-authz-composition@1")
    require("composition profile", contract["profile"], "synthetic-clean-room")

    inputs = contract["declaredInputs"]
    require("APISIX input schema", inputs["gatewayAuthentication"], "baudot.apisix-api-edge@1")
    require("Shiro input schema", inputs["applicationAuthentication"], "baudot.shiro-user-session@1")
    require(
        "Ranger input schema",
        inputs["rangerAuthorization"],
        "baudot.ranger-itrs-pdp-contract@1",
    )
    require(
        "TRS business input schema",
        inputs["trsBusinessAuthority"],
        "baudot.trs-business-authority-contract@1",
    )
    require("base TRS business contract schema", business["schema"], inputs["trsBusinessAuthority"])

    policy = business["itrsPolicy"]
    require("base iTRS identity source", policy["identitySource"], "shiro")
    require("base iTRS policy decision point", policy["policyDecisionPoint"], "ranger")
    require("base iTRS protocol gate", policy["protocolGate"], "baudot-itrs-service")

    promotions = {(row["from"], row["to"]) for row in business["forbiddenPromotions"]}
    if ("shiro.authenticated", "itrs.authorized") not in promotions:
        raise AssertionError("base contract no longer forbids Shiro authentication promotion")
    if ("ranger.allow", "itrs.protocol-valid") not in promotions:
        raise AssertionError("base contract no longer forbids Ranger ALLOW promotion")
    print("PASS base forbidden promotions remain present")


def validate_handoff(contract: dict[str, Any]) -> None:
    require("decision order", contract["decisionOrder"], DECISION_ORDER)

    handoff = contract["subjectHandoff"]
    require("gateway credential not forwarded", handoff["gatewayCredentialForwarded"], False)
    require(
        "gateway principal not directly asserted to Ranger",
        handoff["gatewayPrincipalDirectlyAssertedAsRangerSubject"],
        False,
    )
    require("Ranger subject source", handoff["rangerSubjectSource"], "shiro.actorId")
    require("trusted application service only", handoff["trustedApplicationServiceOnly"], True)
    require("correlation ID may cross boundaries", handoff["correlationIdMayCrossBoundaries"], True)

    authority = contract["authorityBoundary"]
    for key in (
        "gatewayAuthenticationIsApplicationAuthentication",
        "gatewayAuthenticationIsRangerAuthorization",
        "applicationAuthenticationIsRangerAuthorization",
        "rangerAuthorizationIsProtocolValidity",
        "rangerAuthorizationIsTrsBusinessAuthority",
        "protocolValidityIsTrsBusinessAuthority",
    ):
        require(key, authority[key], False)
    require(
        "downstream decisions stay unevaluated after deny",
        authority["downstreamDecisionAfterUpstreamDeny"],
        "NOT_EVALUATED",
    )


def derive_case(case: dict[str, Any]) -> tuple[bool, bool]:
    stopped = False
    ranger_called = False

    for stage in DECISION_ORDER:
        value = case[stage]

        if stopped:
            require(f"{case['id']} {stage} after stop", value, "NOT_EVALUATED")
            continue

        if value == "NOT_EVALUATED":
            raise AssertionError(f"{case['id']}: {stage} cannot be NOT_EVALUATED before a stop")

        if stage == "rangerAuthorization":
            ranger_called = True

        if value == PASS_VALUES[stage]:
            continue
        if value == FAIL_VALUES[stage]:
            stopped = True
            continue
        raise AssertionError(f"{case['id']}: invalid {stage} value {value!r}")

    execute = all(case[stage] == PASS_VALUES[stage] for stage in DECISION_ORDER)
    return ranger_called, execute


def validate_cases(contract: dict[str, Any]) -> list[dict[str, Any]]:
    expected_ids = {f"ITRS-COMP-{n:03d}" for n in range(1, 7)}
    actual_ids = {case["id"] for case in contract["cases"]}
    require("composition case coverage", actual_ids, expected_ids)

    evidence_rows: list[dict[str, Any]] = []
    correlations: set[str] = set()

    for case in contract["cases"]:
        correlation_id = case["correlationId"]
        if correlation_id in correlations:
            raise AssertionError(f"duplicate correlation ID: {correlation_id}")
        correlations.add(correlation_id)

        ranger_called, execute = derive_case(case)
        require(f"{case['id']} execute gate", execute, case["expectedExecute"])

        evidence_rows.append(
            {
                "caseId": case["id"],
                "correlationId": correlation_id,
                "gatewayAuthentication": case["gatewayAuthentication"],
                "applicationAuthentication": case["applicationAuthentication"],
                "rangerAuthorization": case["rangerAuthorization"],
                "protocolValidity": case["protocolValidity"],
                "trsBusinessAuthority": case["trsBusinessAuthority"],
                "rangerCalled": ranger_called,
                "execute": execute,
            }
        )

    require(
        "only all-pass case executes",
        [row["caseId"] for row in evidence_rows if row["execute"]],
        ["ITRS-COMP-006"],
    )
    return evidence_rows


def validate_evidence_contract(contract: dict[str, Any], evidence_rows: list[dict[str, Any]]) -> None:
    evidence = contract["evidence"]
    require("evidence schema", evidence["schema"], "baudot.itrs-authz-composition-evidence@1")

    expected_fields = {
        "caseId",
        "correlationId",
        "gatewayAuthentication",
        "applicationAuthentication",
        "rangerAuthorization",
        "protocolValidity",
        "trsBusinessAuthority",
        "rangerCalled",
        "execute",
    }
    require("evidence field set", set(evidence["fields"]), expected_fields)
    for row in evidence_rows:
        require(f"{row['caseId']} evidence field set", set(row), expected_fields)

    forbidden = set(evidence["forbiddenFields"])
    required_forbidden = {
        "authorizationHeader",
        "accessToken",
        "refreshToken",
        "password",
        "telephoneNumber",
        "subscriberId",
    }
    require("forbidden evidence fields", forbidden, required_forbidden)
    if expected_fields & forbidden:
        raise AssertionError("evidence field set intersects forbidden field set")
    print("PASS evidence projection contains no forbidden credential/subscriber fields")


def validate_claim_boundary(contract: dict[str, Any]) -> None:
    boundary = contract["claimBoundary"]
    require("synthetic fixtures only", boundary["syntheticFixturesOnly"], True)
    for key, value in boundary.items():
        if key == "syntheticFixturesOnly":
            continue
        require(key, value, False)


def write_evidence(contract: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema": contract["evidence"]["schema"],
        "contractSchema": contract["schema"],
        "profile": contract["profile"],
        "rangerSubjectSource": contract["subjectHandoff"]["rangerSubjectSource"],
        "gatewayCredentialForwarded": contract["subjectHandoff"]["gatewayCredentialForwarded"],
        "cases": rows,
    }
    EVIDENCE_PATH.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    print(f"PASS evidence written: {EVIDENCE_PATH.relative_to(ROOT)}")


def main() -> None:
    contract = json.loads(CONTRACT_PATH.read_text())
    business = json.loads(BUSINESS_PATH.read_text())

    validate_declared_inputs(contract, business)
    validate_handoff(contract)
    rows = validate_cases(contract)
    validate_evidence_contract(contract, rows)
    validate_claim_boundary(contract)
    write_evidence(contract, rows)

    print("iTRS authz composition contract: PASS")


if __name__ == "__main__":
    main()
