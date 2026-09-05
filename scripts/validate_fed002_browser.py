#!/usr/bin/env python3
"""Independently reduce the real-browser side of BAUDOT-FED-002."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from baudot_reference.rfc8865 import T140DataChannelMessage, T140DataChannelProfile


@dataclass(frozen=True, slots=True)
class BrowserEvidenceResult:
    browser_identified: bool
    ice_ready: bool
    dtls_ready: bool
    sctp_ready: bool
    candidate_pair_observed: bool
    local_channel_valid: bool
    remote_channel_valid: bool
    t140_valid: bool
    decoded_text: str | None
    terminal_verdict: str
    failed_facts: tuple[str, ...]


def _peer_ready(peer: Mapping[str, Any], field: str, accepted: set[str]) -> bool:
    return peer.get(field) in accepted


def _channel_valid(channel: Mapping[str, Any]) -> bool:
    try:
        T140DataChannelProfile(
            subprotocol=channel.get("protocol"),
            reliable=channel.get("maxPacketLifeTime") is None and channel.get("maxRetransmits") is None,
            ordered=channel.get("ordered"),
        )
    except (TypeError, ValueError):
        return False
    return channel.get("readyState") == "open"


def _decode_hex(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    compact = "".join(value.split())
    if len(compact) % 2:
        return None
    try:
        payload = bytes.fromhex(compact)
        return T140DataChannelMessage.from_bytes(payload).text
    except (ValueError, TypeError):
        return None


def validate_browser_evidence(evidence: Mapping[str, Any]) -> BrowserEvidenceResult:
    implementation = evidence.get("implementation")
    offerer = evidence.get("offerer")
    answerer = evidence.get("answerer")
    local_channel = evidence.get("localDataChannel")
    remote_channel = evidence.get("remoteDataChannel")

    if not all(isinstance(value, Mapping) for value in (implementation, offerer, answerer, local_channel, remote_channel)):
        raise ValueError("browser evidence is missing required object sections")

    user_agent = implementation.get("userAgent")
    browser_identified = isinstance(user_agent, str) and bool(user_agent.strip())
    ice_ready = all(
        _peer_ready(peer, "iceConnectionState", {"connected", "completed"})
        for peer in (offerer, answerer)
    )
    dtls_ready = all(_peer_ready(peer, "dtlsState", {"connected"}) for peer in (offerer, answerer))
    sctp_ready = all(_peer_ready(peer, "sctpState", {"connected"}) for peer in (offerer, answerer))
    candidate_pair_observed = all(
        isinstance(peer.get("succeededCandidatePairs"), list) and len(peer["succeededCandidatePairs"]) >= 1
        for peer in (offerer, answerer)
    )
    local_channel_valid = _channel_valid(local_channel)
    remote_channel_valid = _channel_valid(remote_channel)

    decoded_text = _decode_hex(evidence.get("receivedUtf8Hex"))
    t140_valid = decoded_text is not None and decoded_text == evidence.get("receivedText")

    facts = {
        "browserIdentified": browser_identified,
        "iceReady": ice_ready,
        "dtlsReady": dtls_ready,
        "sctpReady": sctp_ready,
        "candidatePairObserved": candidate_pair_observed,
        "localChannelValid": local_channel_valid,
        "remoteChannelValid": remote_channel_valid,
        "t140Valid": t140_valid,
    }
    failed_facts = tuple(sorted(name for name, value in facts.items() if not value))
    return BrowserEvidenceResult(
        browser_identified=browser_identified,
        ice_ready=ice_ready,
        dtls_ready=dtls_ready,
        sctp_ready=sctp_ready,
        candidate_pair_observed=candidate_pair_observed,
        local_channel_valid=local_channel_valid,
        remote_channel_valid=remote_channel_valid,
        t140_valid=t140_valid,
        decoded_text=decoded_text,
        terminal_verdict="ready" if not failed_facts else "not-ready",
        failed_facts=failed_facts,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    result = validate_browser_evidence(evidence)
    payload = asdict(result)
    payload["failed_facts"] = list(result.failed_facts)
    payload["source"] = str(args.evidence)
    payload["claimBoundary"] = "real Chromium WebRTC execution; not WebRTC or RFC 8865 conformance"
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result.terminal_verdict == "ready" else 4


if __name__ == "__main__":
    raise SystemExit(main())
