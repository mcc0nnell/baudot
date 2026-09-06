#!/usr/bin/env python3
"""Validate the bounded Apache Shiro user/session profile."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / "testkit/business/shiro-user-session-v1.json").read_text())


def require(name: str, actual, expected=True) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"PASS {name}: {actual!r}")


def evaluate(case: dict) -> dict:
    # A protected subject requires active strong authentication. A remembered
    # identity is useful UX context but is not treated as fresh authentication.
    authenticated = bool(case["credentialsValid"] and case["sessionActive"] and not case["remembered"])
    ranger_may_be_called = bool(authenticated and case["trustedService"])
    operation_may_execute = bool(
        ranger_may_be_called
        and case["rangerDecision"] == "ALLOW"
        and case["protocolValid"]
    )
    return {
        "authenticated": authenticated,
        "rangerMayBeCalled": ranger_may_be_called,
        "operationMayExecute": operation_may_execute,
    }


def main() -> None:
    require("schema", PROFILE["schema"], "baudot.shiro-user-session@1")
    shiro = PROFILE["shiro"]
    require("Shiro version", shiro["version"], "3.0.1")
    require("Shiro release tag", shiro["releaseTag"], "shiro-root-3.0.1")
    require("Shiro release commit", shiro["releaseCommit"], "3dcc3fc2a8ddae21ea76a8c55637aa165f368357")
    require("Shiro role", shiro["role"], "application-user-authentication-and-session-context")

    context = PROFILE["subjectContext"]
    fields = set(context["fields"])
    forbidden = set(context["forbiddenFields"])
    require("subject context separates allowed/forbidden", fields.isdisjoint(forbidden), True)
    for required in {"actorId", "actorType", "roles", "sessionId", "authenticationStrength"}:
        require(f"subject context contains {required}", required in fields, True)
    for sensitive in {"password", "telephoneNumber", "subscriberName", "eligibilityApproved", "identityVerified"}:
        require(f"subject context forbids {sensitive}", sensitive in forbidden, True)

    handoff = PROFILE["rangerHandoff"]
    require("Ranger handoff trusted-service only", handoff["trustedServiceOnly"], True)
    require("protected operations require authentication", handoff["requiresAuthenticatedSubjectForProtectedOperation"], True)
    require("remembered cannot authorize protected action", handoff["rememberedSubjectMayAuthorizeProtectedOperation"], False)
    require("Ranger forwarded fields are subject-context subset", set(handoff["forwardedFields"]).issubset(fields), True)
    require("Ranger handoff excludes forbidden fields", set(handoff["forwardedFields"]).isdisjoint(forbidden), True)

    authority = PROFILE["authorityBoundary"]
    for key, value in authority.items():
        require(f"non-authority {key}", value, False)

    cases = PROFILE["cases"]
    ids = [case["id"] for case in cases]
    require("case IDs unique", len(ids), len(set(ids)))
    require("expected case set", ids, [f"SHIRO-{index:03d}" for index in range(1, 9)])

    for case in cases:
        actual = evaluate(case)
        require(case["id"], actual, case["expect"])

    remembered = next(case for case in cases if case["id"] == "SHIRO-005")
    require("remembered fixture is remembered", remembered["remembered"], True)
    require("remembered fixture has active session", remembered["sessionActive"], True)
    require("remembered fixture still fails protected authentication", remembered["expect"]["authenticated"], False)

    denied = next(case for case in cases if case["id"] == "SHIRO-004")
    require("Ranger deny remains terminal", denied["expect"]["operationMayExecute"], False)

    invalid_protocol = next(case for case in cases if case["id"] == "SHIRO-008")
    require("protocol invalid remains terminal", invalid_protocol["expect"]["operationMayExecute"], False)

    for key, value in PROFILE["claimBoundary"].items():
        require(f"claim boundary {key}", value, False)

    print("Baudot Shiro user/session profile: PASS")


if __name__ == "__main__":
    main()
