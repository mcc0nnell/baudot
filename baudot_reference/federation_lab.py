from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .rfc8865 import T140DataChannelMessage, T140DataChannelProfile


class InvalidFederationBoundary(ValueError):
    """Raised when BAUDOT-FED-002 evidence cannot be reduced safely."""


@dataclass(frozen=True, slots=True)
class SipWebRtcBoundaryResult:
    arm_id: str
    sip_dialog_established: bool
    interpreter_joined: bool
    interpreter_ready: bool
    browser_boundary_negotiated: bool
    browser_boundary_profile_valid: bool
    browser_boundary_t140_observed: bool
    browser_boundary_t140_valid: bool
    decoded_text: str | None
    terminal_verdict: str
    failed_facts: tuple[str, ...]


def _arm_by_id(scenario: Mapping[str, Any], arm_id: str) -> Mapping[str, Any]:
    arms = scenario.get("arms")
    if not isinstance(arms, list):
        raise InvalidFederationBoundary("arms must be a list")
    matches = [arm for arm in arms if isinstance(arm, Mapping) and arm.get("id") == arm_id]
    if len(matches) != 1:
        raise InvalidFederationBoundary(f"arm {arm_id!r} must exist exactly once")
    return matches[0]


def _parse_hex(value: object) -> bytes:
    if not isinstance(value, str) or not value.strip():
        raise InvalidFederationBoundary("browserBoundaryT140Hex must be a non-empty hex string")
    compact = "".join(value.split())
    if len(compact) % 2:
        raise InvalidFederationBoundary("browserBoundaryT140Hex must contain complete octets")
    try:
        return bytes.fromhex(compact)
    except ValueError as exc:
        raise InvalidFederationBoundary("browserBoundaryT140Hex contains invalid hex") from exc


def _profile_valid(observations: Mapping[str, Any]) -> bool:
    profile = observations.get("browserBoundaryProfile")
    if not isinstance(profile, Mapping):
        return False
    try:
        T140DataChannelProfile(
            subprotocol=profile.get("subprotocol"),
            reliable=profile.get("reliable"),
            ordered=profile.get("ordered"),
        )
    except (TypeError, ValueError):
        return False
    return True


def reduce_sip_webrtc_boundary(
    scenario: Mapping[str, Any],
    arm_id: str,
) -> SipWebRtcBoundaryResult:
    """Reduce BAUDOT-FED-002 without promoting the reference boundary to a browser claim.

    SIP establishment, interpreter participation/readiness, RFC 8865 profile shape,
    and received T.140 validity remain independent facts. The function intentionally
    does not derive ICE, DTLS, SCTP, or RTCPeerConnection state from these inputs.
    """

    arm = _arm_by_id(scenario, arm_id)
    observations = arm.get("observations")
    if not isinstance(observations, Mapping):
        raise InvalidFederationBoundary(f"arm {arm_id!r} observations must be an object")

    sip_dialog_established = observations.get("sipDialogEstablished") is True
    interpreter_joined = observations.get("interpreterJoined") is True
    interpreter_ready = observations.get("interpreterReady") is True
    browser_boundary_negotiated = observations.get("browserBoundaryNegotiated") is True
    browser_boundary_t140_observed = observations.get("browserBoundaryT140Observed") is True

    profile_valid = browser_boundary_negotiated and _profile_valid(observations)

    t140_valid = False
    decoded_text: str | None = None
    if browser_boundary_t140_observed:
        try:
            payload = _parse_hex(observations.get("browserBoundaryT140Hex"))
            message = T140DataChannelMessage.from_bytes(payload)
            decoded_text = message.text
            t140_valid = True
        except (InvalidFederationBoundary, ValueError):
            t140_valid = False

    facts = {
        "sipDialogEstablished": sip_dialog_established,
        "interpreterJoined": interpreter_joined,
        "interpreterReady": interpreter_ready,
        "browserBoundaryNegotiated": browser_boundary_negotiated,
        "browserBoundaryProfileValid": profile_valid,
        "browserBoundaryT140Observed": browser_boundary_t140_observed,
        "browserBoundaryT140Valid": t140_valid,
    }
    failed_facts = tuple(sorted(name for name, value in facts.items() if not value))
    terminal_verdict = "ready" if not failed_facts else "not-ready"

    return SipWebRtcBoundaryResult(
        arm_id=arm_id,
        sip_dialog_established=sip_dialog_established,
        interpreter_joined=interpreter_joined,
        interpreter_ready=interpreter_ready,
        browser_boundary_negotiated=browser_boundary_negotiated,
        browser_boundary_profile_valid=profile_valid,
        browser_boundary_t140_observed=browser_boundary_t140_observed,
        browser_boundary_t140_valid=t140_valid,
        decoded_text=decoded_text,
        terminal_verdict=terminal_verdict,
        failed_facts=failed_facts,
    )
