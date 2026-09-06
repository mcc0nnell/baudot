#!/usr/bin/env python3
"""Validate and execute the synthetic Baudot iTRS -> Ranger PDP profile."""

from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_DEF = ROOT / "interop" / "ranger" / "itrs-service-def-v1.json"
CONTRACT = ROOT / "interop" / "ranger" / "itrs-pdp-contract-v1.json"
ADAPTER = ROOT / "interop" / "ranger" / "itrs_pdp_adapter.py"


def load_adapter():
    spec = importlib.util.spec_from_file_location("itrs_pdp_adapter", ADAPTER)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Ranger adapter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(name: str, actual, expected) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"PASS {name}: {actual}")


def validate_service_def(service_def: dict, contract: dict) -> None:
    require("Ranger service name", service_def["name"], "baudot-itrs")
    require("PDP service type binds service definition", contract["serviceType"], service_def["name"])
    require("Ranger PDP endpoint", contract["endpoint"], "/v1/authorize")

    resources = {row["name"]: row for row in service_def["resources"]}
    access_types = {row["name"]: row for row in service_def["accessTypes"]}

    require(
        "resource vocabulary",
        set(resources),
        {"provider", "subscriber", "telephone-number", "registration", "routing-record"},
    )
    require(
        "access vocabulary",
        set(access_types),
        {"query", "create", "update", "assign", "route", "audit"},
    )

    resource_ids = [row["itemId"] for row in service_def["resources"]]
    access_ids = [row["itemId"] for row in service_def["accessTypes"]]
    require("resource item IDs unique", len(resource_ids), len(set(resource_ids)))
    require("access item IDs unique", len(access_ids), len(set(access_ids)))

    for name, row in resources.items():
        require(
            f"{name} matcher",
            row["matcher"],
            "org.apache.ranger.plugin.resourcematcher.RangerDefaultResourceMatcher",
        )
        for permission in row["accessTypeRestrictions"]:
            if permission not in access_types:
                raise AssertionError(f"{name}: unknown accessTypeRestriction {permission}")
        print(f"PASS {name} access restrictions: {row['accessTypeRestrictions']}")

    for operation_class, mapping in contract["operationMappings"].items():
        resource = resources.get(mapping["resourceType"])
        if resource is None:
            raise AssertionError(f"{operation_class}: unknown resource type")
        permission = mapping["permission"]
        if permission not in access_types:
            raise AssertionError(f"{operation_class}: unknown permission {permission}")
        if permission not in resource["accessTypeRestrictions"]:
            raise AssertionError(
                f"{operation_class}: permission {permission} not valid for {mapping['resourceType']}"
            )
        if mapping["action"] not in {"QUERY", "CREATE", "UPDATE"}:
            raise AssertionError(f"{operation_class}: unsupported PDP action {mapping['action']}")
        print(
            f"PASS {operation_class}: {mapping['resourceType']} / "
            f"{mapping['action']} / {permission}"
        )

    trusted = contract["trustedCallerBoundary"]
    require("no direct end-user PDP calls", trusted["endUserDirectPdpCallsAllowed"], False)
    require("only authenticated subject may be asserted", trusted["applicationMayAssertAuthenticatedSubjectOnly"], True)
    require("groups/attributes require trusted caller", trusted["groupsOrAttributesRequireTrustedCaller"], True)
    require("PDP failure is not implicit allow", trusted["pdpFailureImplicitAllow"], False)


class FixturePdpHandler(BaseHTTPRequestHandler):
    fixtures: dict[str, dict] = {}
    observed: dict[str, dict] = {}

    def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
        if self.path != "/v1/authorize":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        correlation_id = body["context"]["correlationId"]
        fixture = self.fixtures[correlation_id]
        self.observed[correlation_id] = body

        if fixture["pdpMode"] == "unavailable":
            self.send_error(503)
            return

        if fixture["pdpMode"] == "malformed":
            payload = {}
        else:
            payload = {"decision": fixture["pdpDecision"]}

        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


def validate_fixtures(contract: dict, adapter) -> None:
    fixtures = contract["fixtures"]
    require(
        "fixture IDs",
        [row["id"] for row in fixtures],
        [f"ITRS-RANGER-{index:03d}" for index in range(1, 8)],
    )

    FixturePdpHandler.fixtures = {row["id"]: row for row in fixtures}
    FixturePdpHandler.observed = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixturePdpHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        for fixture in fixtures:
            outcome = adapter.authorize_operation(fixture, contract, base_url)
            expected = fixture["expected"]
            require(f"{fixture['id']} PDP called", outcome.pdp_called, expected["pdpCalled"])
            require(f"{fixture['id']} execute", outcome.execute, expected["execute"])

            observed = FixturePdpHandler.observed.get(fixture["id"])
            if expected["pdpCalled"]:
                if observed is None:
                    raise AssertionError(f"{fixture['id']}: expected HTTP PDP request")
                mapping = contract["operationMappings"][fixture["operationClass"]]
                resource = fixture["resource"]
                require(f"{fixture['id']} user", observed["user"]["name"], fixture["subject"])
                require(
                    f"{fixture['id']} resource",
                    observed["access"]["resource"]["name"],
                    f"{resource['type']}:{resource['id']}",
                )
                require(f"{fixture['id']} action", observed["access"]["action"], mapping["action"])
                require(
                    f"{fixture['id']} permission",
                    observed["access"]["permissions"],
                    [mapping["permission"]],
                )
                require(
                    f"{fixture['id']} serviceType",
                    observed["context"]["serviceType"],
                    contract["serviceType"],
                )
                require(
                    f"{fixture['id']} serviceName",
                    observed["context"]["serviceName"],
                    contract["serviceName"],
                )
            elif observed is not None:
                raise AssertionError(f"{fixture['id']}: precheck rejection still called PDP")

            print(f"PASS {fixture['id']} reason: {outcome.reason}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def main() -> None:
    service_def = json.loads(SERVICE_DEF.read_text())
    contract = json.loads(CONTRACT.read_text())
    adapter = load_adapter()

    validate_service_def(service_def, contract)
    validate_fixtures(contract, adapter)

    boundary = contract["claimBoundary"]
    for key, value in boundary.items():
        require(key, value, False)

    print("Baudot iTRS Ranger PDP profile: PASS")


if __name__ == "__main__":
    main()
