#!/usr/bin/env python3
"""Reduce synthetic RUE RTT negotiation arms into bounded readiness evidence.

The reducer intentionally keeps five observations separate:
- local RTT policy for this controlled arm;
- remote SDP T.140 capability;
- whether the answer accepts T.140;
- whether T.140 was negotiated; and
- whether independently observed non-empty T.140 exists.

Negotiation is never terminal RTT readiness by itself.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "testkit" / "vrs" / "fixtures" / "rue-rtt-negotiation-arms-v1.json"
EVIDENCE = ROOT / "target" / "evidence" / "RUE-RTT-NEGOTIATION"

RTPMAP_T140 = re.compile(r"^a=rtpmap:(\d+)\s+t140/1000(?:\s|$)", re.IGNORECASE)
MEDIA_LINE = re.compile(r"^m=([^\s]+)\s+\d+\s+[^\s]+\s+(.+)$", re.IGNORECASE)


def remote_offers_t140(sdp: str) -> bool:
    """Return true only when a text media section maps one offered PT to t140/1000."""
    current_media: str | None = None
    text_payloads: set[str] = set()

    for raw in sdp.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        media = MEDIA_LINE.match(line)
        if media:
            current_media = media.group(1).lower()
            text_payloads = set(media.group(2).split()) if current_media == "text" else set()
            continue
        if current_media != "text":
            continue
        mapping = RTPMAP_T140.match(line)
        if mapping and mapping.group(1) in text_payloads:
            return True
    return False


def reduce_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id = str(case["id"])
    local_enabled = bool(case["localRttEnabled"])
    remote_offer = str(case["remoteOffer"])
    answer_accepts = bool(case["answerAcceptsT140"])
    first_observed = bool(case["firstT140CharacterObserved"])
    remote_t140 = remote_offers_t140(remote_offer)

    negotiated = local_enabled and remote_t140 and answer_accepts
    ready = negotiated and first_observed

    if not remote_t140:
        reason = "remote-no-t140"
    elif not local_enabled:
        reason = "local-rtt-disabled"
    elif not answer_accepts:
        reason = "answer-does-not-accept-t140"
    elif not first_observed:
        reason = "negotiated-awaiting-t140"
    else:
        reason = "ready"

    return {
        "schema": "baudot.rue-rtt-negotiation-result@1",
        "case": case_id,
        "localRttEnabled": local_enabled,
        "remoteOffersT140": remote_t140,
        "answerAcceptsT140": answer_accepts,
        "rttNegotiated": negotiated,
        "firstT140CharacterObserved": first_observed,
        "rttReady": ready,
        "reason": reason,
        "verdictAuthority": "baudot-independent-reducer",
        "claimBoundary": "synthetic session/readiness classification only",
    }


def expected_projection(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "remoteOffersT140": result["remoteOffersT140"],
        "rttNegotiated": result["rttNegotiated"],
        "firstT140CharacterObserved": result["firstT140CharacterObserved"],
        "rttReady": result["rttReady"],
        "reason": result["reason"],
    }


def validate_fixture(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    if fixture.get("schema") != "baudot.rue-rtt-negotiation-arms@1":
        raise ValueError("unexpected RTT negotiation fixture schema")
    if fixture.get("synthetic") is not True:
        raise ValueError("RTT negotiation fixture must remain synthetic")
    cases = fixture.get("cases")
    if not isinstance(cases, list) or len(cases) < 3:
        raise ValueError("RTT negotiation fixture requires two negative arms and a positive negotiation control")

    required_ids = {
        "local-enabled-remote-absent",
        "remote-offered-local-disabled",
        "both-enabled-negotiated-no-media-yet",
    }
    actual_ids = {str(case.get("id")) for case in cases}
    if actual_ids != required_ids:
        raise ValueError(f"RTT negotiation case set drifted: {sorted(actual_ids)}")

    results: list[dict[str, Any]] = []
    for case in cases:
        result = reduce_case(case)
        expected = case.get("expected")
        if expected_projection(result) != expected:
            raise ValueError(
                f"{case['id']}: expected {expected}, reduced {expected_projection(result)}"
            )
        if result["rttReady"] and not result["firstT140CharacterObserved"]:
            raise ValueError(f"{case['id']}: readiness cannot precede first T.140 observation")
        results.append(result)
    return results


def main() -> int:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    results = validate_fixture(fixture)
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    for result in results:
        path = EVIDENCE / f"{result['case']}.json"
        path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(
            f"{result['case']}: remoteT140={str(result['remoteOffersT140']).lower()} "
            f"negotiated={str(result['rttNegotiated']).lower()} "
            f"firstT140={str(result['firstT140CharacterObserved']).lower()} "
            f"ready={str(result['rttReady']).lower()} PASS"
        )

    summary = {
        "schema": "baudot.rue-rtt-negotiation-summary@1",
        "cases": len(results),
        "readyCases": sum(1 for result in results if result["rttReady"]),
        "negotiatedButNotReadyCases": sum(
            1 for result in results if result["rttNegotiated"] and not result["rttReady"]
        ),
        "claimBoundary": "negotiation does not establish RTT readiness",
    }
    (EVIDENCE / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("RUE RTT negotiation/readiness boundary: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
