#!/usr/bin/env python3
"""Map a validated BaudotRoute into the narrow TILDEN-HANDOFF-002 RTT runtime profile."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SIP_UDP = re.compile(r"^sip:callee@([^:;]+):(\d+);transport=udp$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    route = json.loads(args.route.read_text(encoding="utf-8"))
    selection_id = route.get("selectionId")
    endpoint = route.get("selectedEndpoint")

    require(isinstance(selection_id, str) and selection_id, "route is missing selectionId")
    require(isinstance(endpoint, str) and endpoint, "route is missing selectedEndpoint")

    match = SIP_UDP.fullmatch(endpoint)
    require(match is not None, (
        "TILDEN-HANDOFF-002 currently accepts only canonical "
        "sip:callee@HOST:PORT;transport=udp endpoints"
    ))
    host, port_text = match.groups()
    port = int(port_text)
    require(1 <= port <= 65535, "selected SIP port is out of range")

    runtime = {
        "schema": "baudot.tilden-rtt-route/v1",
        "selectionId": selection_id,
        "target": route.get("target"),
        "resolutionDigest": route.get("resolutionDigest"),
        "requestDigest": route.get("requestDigest"),
        "selectedEndpoint": endpoint,
        "canonicalRequestUri": f"sip:callee@{host}:{port};transport=udp",
        "sip": {
            "host": host,
            "port": port,
            "transport": "udp",
            "user": "callee",
        },
        "claimBoundary": "selected-route-rtt-profile-input",
    }
    require(runtime["canonicalRequestUri"] == endpoint, "runtime route changed selectedEndpoint")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(runtime, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
