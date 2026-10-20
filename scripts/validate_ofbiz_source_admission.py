#!/usr/bin/env python3
"""Validate that Baudot's OFBiz reference mapping exists in an exact upstream checkout."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "testkit" / "business" / "ofbiz-equipment-distribution-v1.json"

ENTITY_FILES = {
    "Product": "applications/datamodel/entitydef/product-entitymodel.xml",
    "Facility": "applications/datamodel/entitydef/product-entitymodel.xml",
    "InventoryItem": "applications/datamodel/entitydef/product-entitymodel.xml",
    "InventoryItemDetail": "applications/datamodel/entitydef/product-entitymodel.xml",
    "OrderHeader": "applications/datamodel/entitydef/order-entitymodel.xml",
    "OrderItem": "applications/datamodel/entitydef/order-entitymodel.xml",
    "ReturnHeader": "applications/datamodel/entitydef/order-entitymodel.xml",
    "ReturnItem": "applications/datamodel/entitydef/order-entitymodel.xml",
    "Shipment": "applications/datamodel/entitydef/shipment-entitymodel.xml",
    "ShipmentItem": "applications/datamodel/entitydef/shipment-entitymodel.xml",
}


def require(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"PASS {name}: {actual}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args()

    fixture = json.loads(FIXTURE.read_text())
    checkout = args.checkout.resolve()
    expected_commit = fixture["ofbiz"]["pinnedCommit"]
    actual_commit = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    require("OFBiz exact checkout", actual_commit, expected_commit)

    declared = {
        entity
        for group in fixture["ofbiz"]["referenceEntities"].values()
        for entity in group
    }
    require("reference entities mapped to known source files", declared, set(ENTITY_FILES))

    for entity, relative in ENTITY_FILES.items():
        path = checkout / relative
        if not path.is_file():
            raise AssertionError(f"{entity}: missing source file {relative}")
        text = path.read_text(encoding="utf-8")
        pattern = rf'<entity\s+entity-name="{re.escape(entity)}"(?:\s|>)'
        if re.search(pattern, text) is None:
            raise AssertionError(f"{entity}: entity definition not found in {relative}")
        print(f"PASS {entity}: {relative}")

    shipment_services = checkout / "applications/product/src/main/groovy/org/apache/ofbiz/product/shipment/ShipmentServices.groovy"
    if not shipment_services.is_file():
        raise AssertionError("ShipmentServices.groovy missing from pinned OFBiz checkout")
    print("PASS shipment service surface: ShipmentServices.groovy")

    return_services = checkout / "applications/order/src/main/groovy/org/apache/ofbiz/order/order/OrderReturnServicesScript.groovy"
    if not return_services.is_file():
        raise AssertionError("OrderReturnServicesScript.groovy missing from pinned OFBiz checkout")
    print("PASS return service surface: OrderReturnServicesScript.groovy")

    print("Pinned OFBiz equipment-domain source admission: PASS")


if __name__ == "__main__":
    main()
