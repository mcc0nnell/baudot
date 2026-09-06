#!/usr/bin/env python3
"""Validate the bounded ACE Kamailio/rtpengine donor abstraction.

This is not a Kamailio or rtpengine emulator. It exists to keep proxy/relay
control state separate from Baudot's terminal T.140 readiness authority.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VECTORS = ROOT / "media-relay-vectors.json"


def reduce_case(case: dict) -> dict:
    method = case["method"].upper()
    has_sdp = bool(case["hasSdp"])
    in_dialog = bool(case["inDialog"])
    relay_available = bool(case["relayAvailable"])

    if method == "BYE" and in_dialog:
        relay_action = "teardown"
    elif method in {"INVITE", "ACK"} and has_sdp:
        relay_action = "manage"
    else:
        relay_action = "none"

    if relay_action == "none":
        relay_outcome = "not_applicable"
    elif relay_available:
        relay_outcome = "requested"
    else:
        relay_outcome = "relay_unavailable"

    # Relay/control observations are never verdict authority. The mock publishes
    # readiness only from the explicit independent semantic observation.
    rtt_ready = (
        bool(case["signalingEstablished"])
        and bool(case["mediaObserved"])
        and case.get("independentT140Text") == "H"
    )

    return {
        "relayAction": relay_action,
        "relayOutcome": relay_outcome,
        "rttReady": rtt_ready,
    }


def main() -> int:
    document = json.loads(VECTORS.read_text(encoding="utf-8"))

    if any(document["claimBoundary"].values()):
        raise AssertionError("donor profile must not contain positive conformance claims")

    seen: set[str] = set()
    positive_readiness = 0
    for vector in document["vectors"]:
        vector_id = vector["id"]
        if vector_id in seen:
            raise AssertionError(f"duplicate vector id: {vector_id}")
        seen.add(vector_id)

        actual = reduce_case(vector["input"])
        expected = vector["expected"]
        if actual != expected:
            raise AssertionError(
                f"{vector_id}: expected {expected!r}, observed {actual!r}"
            )

        if actual["rttReady"]:
            positive_readiness += 1
            if vector["input"].get("independentT140Text") != "H":
                raise AssertionError(
                    f"{vector_id}: readiness escaped independent T.140 authority"
                )
        elif vector["input"].get("independentT140Text") == "H":
            raise AssertionError(
                f"{vector_id}: independent T.140 observation was not reflected"
            )

        print(
            f"PASS {vector_id}: action={actual['relayAction']} "
            f"relay={actual['relayOutcome']} rttReady={str(actual['rttReady']).lower()}"
        )

    if positive_readiness != 1:
        raise AssertionError(
            f"expected exactly one semantic-readiness arm, observed {positive_readiness}"
        )

    print(f"validated {len(seen)} ACE Kamailio/rtpengine donor vectors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
