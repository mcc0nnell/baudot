#!/usr/bin/env python3
"""Validate the Apache-native TRS business authority contract."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "testkit" / "business" / "trs-business-authority-v1.json"


def require(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"PASS {name}: {actual}")


def require_contains(name: str, values: list[str], expected: str) -> None:
    if expected not in values:
        raise AssertionError(f"{name}: missing {expected!r}")
    print(f"PASS {name}: {expected}")


def validate_role_ownership(contract: dict) -> None:
    roles = contract["roles"]

    expected = {
        "shiro": "authenticated-subject",
        "ranger": "resource-action-context-policy-decision",
        "ofbiz": "equipment-catalog",
        "kafka": "cdr-event-transport",
        "fineract": "trs-fund-ledger",
        "tika": "document-extraction",
        "solr": "document-retrieval-index",
        "camel": "cross-domain-routing",
        "tilden": "route-selection-authority",
        "baudot": "communications-observation",
    }

    for component, capability in expected.items():
        require_contains(f"{component} owns canonical bounded role", roles[component]["owns"], capability)
        if capability in roles[component]["mustNotOwn"]:
            raise AssertionError(f"{component}: capability appears in both owns and mustNotOwn: {capability}")

    require_contains("Shiro does not own TRS policy", roles["shiro"]["mustNotOwn"], "trs-policy")
    require_contains("Ranger does not own iTRS protocol validity", roles["ranger"]["mustNotOwn"], "itrs-protocol-validity")
    require_contains("OFBiz does not own subscriber eligibility", roles["ofbiz"]["mustNotOwn"], "subscriber-eligibility")
    require_contains("Kafka does not own call compensability", roles["kafka"]["mustNotOwn"], "call-compensability")
    require_contains("Fineract does not own claim approval", roles["fineract"]["mustNotOwn"], "claim-approval")
    require_contains("Camel does not own accessibility readiness", roles["camel"]["mustNotOwn"], "accessibility-readiness")


def validate_forbidden_promotions(contract: dict) -> None:
    promotions = {(row["from"], row["to"]) for row in contract["forbiddenPromotions"]}
    expected = {
        ("shiro.authenticated", "itrs.authorized"),
        ("ranger.allow", "itrs.protocol-valid"),
        ("ranger.allow", "route.correct"),
        ("ofbiz.shipment-complete", "subscriber.eligible"),
        ("kafka.cdr-persisted", "call.compensable"),
        ("kafka.cdr-persisted", "claim.approved"),
        ("fineract.journal-balanced", "claim.approved"),
        ("fineract.journal-balanced", "payment.authorized"),
        ("solr.document-retrieved", "source.authoritative"),
        ("camel.workflow-complete", "accessibility.ready"),
    }
    require("forbidden promotion set", promotions, expected)


def validate_itrs_policy(contract: dict) -> None:
    policy = contract["itrsPolicy"]
    require("iTRS policy decision point", policy["policyDecisionPoint"], "ranger")
    require("iTRS identity source", policy["identitySource"], "shiro")
    require("iTRS protocol gate", policy["protocolGate"], "baudot-itrs-service")
    require("Ranger decision values", policy["decisionValues"], ["ALLOW", "DENY"])

    required_context = set(policy["requiredRequestContext"])
    fixture_ids: set[str] = set()

    for fixture in policy["fixtures"]:
        fixture_id = fixture["id"]
        if fixture_id in fixture_ids:
            raise AssertionError(f"duplicate fixture id: {fixture_id}")
        fixture_ids.add(fixture_id)

        subject = fixture["subject"]
        request = fixture["request"]
        available_context = {
            "subjectId": subject["subjectId"],
            "providerId": request["providerId"],
            "resourceType": request["resourceType"],
            "resourceId": request["resourceId"],
            "action": request["action"],
            "correlationId": request["correlationId"],
        }
        missing = required_context - set(available_context)
        require(f"{fixture_id} required policy context present", missing, set())

        if request["resourceType"] not in policy["resources"]:
            raise AssertionError(f"{fixture_id}: unknown resource type {request['resourceType']}")
        if request["action"] not in policy["actions"]:
            raise AssertionError(f"{fixture_id}: unknown action {request['action']}")
        if fixture["rangerDecision"] not in policy["decisionValues"]:
            raise AssertionError(f"{fixture_id}: invalid Ranger decision")

        execute = (
            fixture["authenticated"]
            and fixture["rangerDecision"] == "ALLOW"
            and fixture["protocolValid"]
        )
        require(f"{fixture_id} execution gate", execute, fixture["expectedExecute"])

    require(
        "iTRS policy fixture coverage",
        fixture_ids,
        {"ITRS-POLICY-001", "ITRS-POLICY-002", "ITRS-POLICY-003", "ITRS-POLICY-004"},
    )


def validate_cross_domain_flows(contract: dict) -> None:
    flows = {flow["id"]: flow["steps"] for flow in contract["crossDomainFlows"]}

    identity_flow = flows["FLOW-IDENTITY-POLICY-ITRS"]
    require("identity flow starts with Shiro", identity_flow[0], "shiro.authenticated-subject")
    require("identity flow uses Ranger before protocol gate", identity_flow[1], "ranger.resource-action-context-policy-decision")
    require("identity flow keeps protocol gate separate", identity_flow[2], "baudot-itrs-service.protocol-gate")

    equipment_flow = flows["FLOW-EQUIPMENT"]
    require("equipment flow requires external eligibility first", equipment_flow[0], "external-eligibility-decision")
    require_contains("equipment flow uses OFBiz fulfillment", equipment_flow, "ofbiz.fulfillment-order")

    fund_flow = flows["FLOW-CALL-TO-FUND"]
    require("call-to-fund starts with Baudot observation", fund_flow[0], "baudot.communications-observation")
    require_contains("call-to-fund has explicit compensability decision", fund_flow, "external-compensability-decision")
    require_contains("call-to-fund has explicit claim approval", fund_flow, "external-claim-approval")
    require_contains("call-to-fund posts only after approval", fund_flow, "fineract.journal-posting")
    if fund_flow.index("fineract.journal-posting") < fund_flow.index("external-claim-approval"):
        raise AssertionError("Fineract posting occurs before explicit claim approval")
    print("PASS call-to-fund ordering: approval precedes ledger posting")


def validate_claim_boundary(contract: dict) -> None:
    boundary = contract["claimBoundary"]
    require("synthetic fixtures only", boundary["syntheticFixturesOnly"], True)
    for name in (
        "productionIdentityDataUsed",
        "productionSubscriberDataUsed",
        "productionCdrDataUsed",
        "productionFundDataUsed",
        "productionItrsCompatibilityClaimed",
        "rangerWireCompatibilityClaimed",
        "ofbizProductionSuitabilityClaimed",
        "productionTrsReadinessClaimed",
    ):
        require(name, boundary[name], False)


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    require("contract schema", contract["schema"], "baudot.trs-business-authority-contract@1")
    require("contract profile", contract["profile"], "synthetic-clean-room")

    validate_role_ownership(contract)
    validate_forbidden_promotions(contract)
    validate_itrs_policy(contract)
    validate_cross_domain_flows(contract)
    validate_claim_boundary(contract)

    print("TRS business authority contract: PASS")


if __name__ == "__main__":
    main()
