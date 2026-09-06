#!/usr/bin/env python3
"""Validate the neutral read-only MCP evidence-tool contract."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "testkit/mcp/read-only-evidence-tools-v1.json").read_text())
FIXTURE_ROOT = ROOT / "testkit/mcp/fixtures/run-001"
EXPECTED = ["inspect_dialog", "observe_sip_trace", "compare_sdp", "export_evidence"]


def require(name: str, actual, expected=True) -> None:
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")
    print(f"PASS {name}: {actual!r}")


def main() -> None:
    require("schema", CONTRACT["schema"], "baudot.mcp-readonly-evidence-tools@1")
    lane = CONTRACT["implementationLane"]
    require("Camel version", lane["version"], "4.22.0")
    require("Camel release commit", lane["releaseCommit"], "1a54683f4becad3b32df42507e709526d8563f35")
    require("MCP transport", lane["transport"], "streamable-http")
    require("preview support recorded", lane["supportLevel"], "preview")

    require("Juneau snapshot not normative", CONTRACT["futureReferenceAdapter"]["snapshotIsNormativeDependency"], False)
    require("one explicit tool tag", CONTRACT["tagAllowlist"], ["baudot-evidence-readonly"])

    names = [tool["name"] for tool in CONTRACT["tools"]]
    require("exact read-only tool set", names, EXPECTED)
    require("tool names unique", len(names), len(set(names)))
    require("no forbidden mutation tool", set(names).isdisjoint(CONTRACT["forbiddenMutationTools"]), True)

    for tool in CONTRACT["tools"]:
        require(f"{tool['name']} input", tool["input"], ["runId"])
        annotations = tool["annotations"]
        require(f"{tool['name']} readOnly", annotations["readOnlyHint"], True)
        require(f"{tool['name']} destructive", annotations["destructiveHint"], False)
        require(f"{tool['name']} idempotent", annotations["idempotentHint"], True)
        require(f"{tool['name']} openWorld", annotations["openWorldHint"], False)

        path = FIXTURE_ROOT / tool["fixture"]
        if not path.is_file():
            raise AssertionError(f"missing fixture for {tool['name']}: {path}")
        result = json.loads(path.read_text())
        require(f"{tool['name']} fixture run", result["runId"], "run-001")
        require(f"{tool['name']} correlation", result["correlationId"], "corr-run-001")

    for key, value in CONTRACT["equivalenceBoundary"].items():
        if key.endswith("MustMatchExactly") or key.endswith("MustBePreserved"):
            require(f"equivalence {key}", value, True)
    require("MCP not canonical", CONTRACT["equivalenceBoundary"]["mcpObjectIsCanonicalBaudotSemantics"], False)
    require("tool completion not verdict", CONTRACT["equivalenceBoundary"]["toolCompletionIsAccessibilityVerdict"], False)
    require("hints not authorization", CONTRACT["deploymentBoundary"]["toolHintsAreAuthorization"], False)

    for key, value in CONTRACT["authorityBoundary"].items():
        require(f"non-authority {key}", value, False)

    print("Baudot read-only MCP evidence tools: PASS")


if __name__ == "__main__":
    main()
