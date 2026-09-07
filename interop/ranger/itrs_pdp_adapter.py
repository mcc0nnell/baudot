#!/usr/bin/env python3
"""Minimal fail-closed adapter for Baudot's synthetic iTRS -> Ranger PDP boundary.

This module intentionally owns only translation to the documented Ranger PDP wire shape
and enforcement of the returned ALLOW/DENY decision. It does not validate iTRS protocol
semantics, select routes, establish compensability, or produce accessibility verdicts.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class PdpUnavailable(RuntimeError):
    """No usable Ranger PDP decision was obtained."""


@dataclass(frozen=True)
class AuthorizationOutcome:
    pdp_called: bool
    decision: str
    execute: bool
    reason: str
    request: dict[str, Any] | None = None


def build_pdp_request(
    *,
    subject: str,
    resource_type: str,
    resource_id: str,
    operation_class: str,
    correlation_id: str,
    service_type: str,
    service_name: str,
    operation_mappings: dict[str, dict[str, str]],
) -> dict[str, Any]:
    mapping = operation_mappings.get(operation_class)
    if mapping is None:
        raise ValueError(f"unknown operation class: {operation_class}")
    if mapping["resourceType"] != resource_type:
        raise ValueError(
            f"operation {operation_class} requires resource type "
            f"{mapping['resourceType']}, got {resource_type}"
        )

    return {
        "user": {"name": subject},
        "access": {
            "resource": {"name": f"{resource_type}:{resource_id}"},
            "action": mapping["action"],
            "permissions": [mapping["permission"]],
        },
        "context": {
            "serviceType": service_type,
            "serviceName": service_name,
            "correlationId": correlation_id,
            "operationClass": operation_class,
        },
    }


def post_pdp_authorize(
    base_url: str,
    payload: dict[str, Any],
    *,
    endpoint: str = "/v1/authorize",
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + endpoint
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PdpUnavailable(str(exc)) from exc

    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PdpUnavailable("Ranger PDP returned non-JSON content") from exc

    if not isinstance(body, dict):
        raise PdpUnavailable("Ranger PDP response must be a JSON object")
    return body


def authorize_operation(
    fixture: dict[str, Any],
    contract: dict[str, Any],
    base_url: str,
) -> AuthorizationOutcome:
    """Authorize one protected synthetic iTRS operation and fail closed on every gap."""

    if not fixture.get("authenticated", False):
        return AuthorizationOutcome(False, "PRECHECK_DENY", False, "subject-not-authenticated")

    # This deployment profile deliberately routes PDP calls only through the trusted
    # Baudot iTRS service. End-user clients do not call Ranger PDP directly and cannot
    # assert another subject's identity/groups/attributes.
    if not fixture.get("trustedApplicationCaller", False):
        return AuthorizationOutcome(False, "PRECHECK_DENY", False, "caller-not-trusted")

    resource = fixture["resource"]
    payload = build_pdp_request(
        subject=fixture["subject"],
        resource_type=resource["type"],
        resource_id=resource["id"],
        operation_class=fixture["operationClass"],
        correlation_id=fixture["id"],
        service_type=contract["serviceType"],
        service_name=contract["serviceName"],
        operation_mappings=contract["operationMappings"],
    )

    try:
        result = post_pdp_authorize(
            base_url,
            payload,
            endpoint=contract["endpoint"],
            timeout_seconds=0.5,
        )
    except PdpUnavailable:
        return AuthorizationOutcome(True, "UNAVAILABLE", False, "no-pdp-decision", payload)

    decision = result.get("decision")
    if decision not in {"ALLOW", "DENY"}:
        return AuthorizationOutcome(True, "INVALID", False, "invalid-pdp-decision", payload)
    if decision != "ALLOW":
        return AuthorizationOutcome(True, decision, False, "policy-denied", payload)
    if not fixture.get("protocolValid", False):
        return AuthorizationOutcome(True, decision, False, "protocol-gate-rejected", payload)

    return AuthorizationOutcome(True, decision, True, "authorized-and-protocol-valid", payload)
