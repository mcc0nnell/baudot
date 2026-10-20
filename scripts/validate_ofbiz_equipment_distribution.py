#!/usr/bin/env python3
"""Validate the synthetic OFBiz-shaped TRS equipment-distribution contract."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "testkit" / "business" / "ofbiz-equipment-distribution-v1.json"


def require(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"PASS {name}: {actual}")


@dataclass
class State:
    available: dict[str, int]
    quarantine: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    orders: list[dict] = field(default_factory=list)
    shipments: list[dict] = field(default_factory=list)
    returns: list[dict] = field(default_factory=list)
    processed: dict[str, dict] = field(default_factory=dict)
    rejections: int = 0
    backorders: int = 0
    idempotent_replays: int = 0


def validate_contract(fixture: dict) -> None:
    require("contract schema", fixture["schema"], "baudot.ofbiz-equipment-distribution@1")
    ofbiz = fixture["ofbiz"]
    require("OFBiz release branch", ofbiz["releaseBranch"], "release24.09")
    require("OFBiz pinned commit", ofbiz["pinnedCommit"], "d65f164191f331fc77da198701ab97df9bff5564")
    require("OFBiz repository", ofbiz["repository"], "apache/ofbiz-framework")

    expected_entities = {
        "product": ["Product"],
        "facility": ["Facility"],
        "inventory": ["InventoryItem", "InventoryItemDetail"],
        "order": ["OrderHeader", "OrderItem"],
        "shipment": ["Shipment", "ShipmentItem"],
        "return": ["ReturnHeader", "ReturnItem"],
    }
    require("reference entity mapping", ofbiz["referenceEntities"], expected_entities)

    authority = fixture["authority"]
    require("external eligibility owner", authority["eligibilityOwner"], "external-program-policy")
    require("OFBiz cannot create eligibility", authority["ofbizMayCreateEligibility"], False)
    require("inventory does not prove eligibility", authority["inventoryAvailabilityProvesEligibility"], False)
    require("order does not prove eligibility", authority["orderCreationProvesEligibility"], False)
    require("shipment does not prove eligibility", authority["shipmentCompletionProvesEligibility"], False)

    skus = [row["sku"] for row in fixture["catalog"]]
    require("catalog SKUs unique", len(skus), len(set(skus)))
    require("synthetic facility", fixture["facility"]["facilityId"], "SYN-TRS-WAREHOUSE-A")

    scenario_ids = [row["id"] for row in fixture["scenarios"]]
    require("scenario IDs", scenario_ids, [f"EQUIP-{n:03d}" for n in range(1, 7)])

    for scenario in fixture["scenarios"]:
        eligibility = scenario["eligibility"]
        if not eligibility["decisionRef"].startswith("eligibility:synthetic:"):
            raise AssertionError(f"{scenario['id']}: eligibility reference must be synthetic")
        for sku, quantity in scenario["initialInventory"].items():
            if sku not in skus:
                raise AssertionError(f"{scenario['id']}: unknown initial-inventory SKU {sku}")
            if not isinstance(quantity, int) or quantity < 0:
                raise AssertionError(f"{scenario['id']}: invalid inventory quantity")


def add_order(state: State, command: dict, kind: str) -> dict:
    order = {
        "orderId": f"ORDER-{command['requestId']}",
        "requestId": command["requestId"],
        "subscriberId": command["subscriberId"],
        "sku": command["sku"],
        "quantity": command["quantity"],
        "kind": kind,
    }
    state.orders.append(order)
    return order


def ship_if_available(state: State, order: dict) -> bool:
    sku = order["sku"]
    quantity = order["quantity"]
    if state.available.get(sku, 0) < quantity:
        state.backorders += 1
        return False
    state.available[sku] -= quantity
    state.shipments.append(
        {
            "shipmentId": f"SHIP-{order['requestId']}",
            "orderId": order["orderId"],
            "sku": sku,
            "quantity": quantity,
        }
    )
    return True


def execute(scenario: dict) -> State:
    state = State(available=dict(scenario["initialInventory"]))
    eligibility = scenario["eligibility"]

    for command in scenario["commands"]:
        request_id = command["requestId"]
        if request_id in state.processed:
            state.idempotent_replays += 1
            continue

        command_type = command["type"]
        result: dict = {"type": command_type, "accepted": False}

        if command_type == "fulfill":
            if not eligibility["approved"]:
                state.rejections += 1
                result["reason"] = "external-eligibility-required"
            else:
                order = add_order(state, command, "initial")
                result["accepted"] = True
                result["shipped"] = ship_if_available(state, order)

        elif command_type == "return":
            original = state.processed.get(command["originalRequestId"])
            original_shipped = bool(original and original.get("shipped"))
            if not original_shipped:
                state.rejections += 1
                result["reason"] = "original-shipment-required"
            else:
                state.returns.append(
                    {
                        "returnId": f"RETURN-{request_id}",
                        "originalRequestId": command["originalRequestId"],
                        "sku": command["sku"],
                        "quantity": command["quantity"],
                        "condition": command["condition"],
                    }
                )
                result["accepted"] = True
                if command["condition"] == "defective":
                    state.quarantine[command["sku"]] += command["quantity"]
                else:
                    state.available[command["sku"]] = state.available.get(command["sku"], 0) + command["quantity"]

        elif command_type == "replacement":
            original = state.processed.get(command["originalRequestId"])
            has_return = any(
                row["originalRequestId"] == command["originalRequestId"]
                and row["condition"] == "defective"
                for row in state.returns
            )
            if not eligibility["approved"] or not original or not original.get("shipped") or not has_return:
                state.rejections += 1
                result["reason"] = "eligible-defective-return-required"
            else:
                order = add_order(state, command, "replacement")
                result["accepted"] = True
                result["shipped"] = ship_if_available(state, order)

        else:
            raise AssertionError(f"{scenario['id']}: unknown command type {command_type}")

        state.processed[request_id] = result

    return state


def validate_scenario(scenario: dict) -> None:
    state = execute(scenario)
    expected = scenario["expected"]
    sid = scenario["id"]

    require(f"{sid} orders", len(state.orders), expected["orders"])
    require(f"{sid} shipments", len(state.shipments), expected["shipments"])
    require(f"{sid} returns", len(state.returns), expected["returns"])
    require(f"{sid} rejections", state.rejections, expected["rejections"])
    require(f"{sid} backorders", state.backorders, expected["backorders"])
    require(f"{sid} available", state.available, expected["available"])
    actual_quarantine = {sku: state.quarantine.get(sku, 0) for sku in expected["quarantine"]}
    require(f"{sid} quarantine", actual_quarantine, expected["quarantine"])
    require(
        f"{sid} idempotent replays",
        state.idempotent_replays,
        expected.get("idempotentReplays", 0),
    )

    if not scenario["eligibility"]["approved"]:
        require(f"{sid} ineligible created no orders", len(state.orders), 0)
        require(f"{sid} ineligible created no shipments", len(state.shipments), 0)

    print(f"PASS {sid}: {scenario['description']}")


def main() -> None:
    fixture = json.loads(FIXTURE.read_text())
    validate_contract(fixture)
    for scenario in fixture["scenarios"]:
        validate_scenario(scenario)

    for key, value in fixture["claimBoundary"].items():
        require(key, value, False)

    print("Synthetic OFBiz equipment-distribution model: PASS")


if __name__ == "__main__":
    main()
