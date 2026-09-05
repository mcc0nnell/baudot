from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class InvalidFederationScenario(ValueError):
    """Raised when a federated-session scenario cannot be reduced safely."""


@dataclass(frozen=True)
class FederatedSessionResult:
    arm_id: str
    session_connected: bool
    accessibility_ready: bool
    security_claim_valid: bool
    terminal_verdict: str
    missing_participants: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    unmet_readiness: tuple[str, ...]
    media_termination_points: tuple[str, ...]


def _string_set(value: Any, field: str) -> set[str]:
    if value is None:
        return set()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise InvalidFederationScenario(f"{field} must be a list of strings")
    return set(value)


def _arm_by_id(scenario: Mapping[str, Any], arm_id: str) -> Mapping[str, Any]:
    arms = scenario.get("arms")
    if not isinstance(arms, list):
        raise InvalidFederationScenario("arms must be a list")
    matches = [arm for arm in arms if isinstance(arm, Mapping) and arm.get("id") == arm_id]
    if len(matches) != 1:
        raise InvalidFederationScenario(f"arm {arm_id!r} must exist exactly once")
    return matches[0]


def reduce_federated_session(
    scenario: Mapping[str, Any],
    arm_id: str,
) -> FederatedSessionResult:
    """Reduce one deterministic federated-call arm into explicit readiness facts.

    The reducer intentionally ignores provider and platform brand labels. It evaluates
    only required participant roles/capabilities, readiness observations, and the
    media-security evidence supplied by the arm.
    """

    model = scenario.get("federationModel")
    if not isinstance(model, Mapping):
        raise InvalidFederationScenario("federationModel must be an object")

    participant_specs = model.get("participants")
    if not isinstance(participant_specs, list) or not participant_specs:
        raise InvalidFederationScenario("federationModel.participants must be a non-empty list")

    arm = _arm_by_id(scenario, arm_id)
    observations = arm.get("observations")
    if not isinstance(observations, Mapping):
        raise InvalidFederationScenario(f"arm {arm_id!r} observations must be an object")

    participant_observations = observations.get("participants")
    if not isinstance(participant_observations, Mapping):
        raise InvalidFederationScenario(
            f"arm {arm_id!r} observations.participants must be an object"
        )

    missing_participants: list[str] = []
    missing_capabilities: list[str] = []

    for spec in participant_specs:
        if not isinstance(spec, Mapping):
            raise InvalidFederationScenario("participant specifications must be objects")
        participant_id = spec.get("id")
        if not isinstance(participant_id, str) or not participant_id:
            raise InvalidFederationScenario("participant id must be a non-empty string")

        observed = participant_observations.get(participant_id)
        if not isinstance(observed, Mapping) or observed.get("joined") is not True:
            missing_participants.append(participant_id)
            continue

        required = _string_set(
            spec.get("requiredCapabilities", []),
            f"participant {participant_id} requiredCapabilities",
        )
        negotiated = _string_set(
            observed.get("negotiatedCapabilities", []),
            f"participant {participant_id} negotiatedCapabilities",
        )
        for capability in sorted(required - negotiated):
            missing_capabilities.append(f"{participant_id}:{capability}")

    required_readiness = _string_set(
        model.get("requiredReadiness", []),
        "federationModel.requiredReadiness",
    )
    readiness = observations.get("readiness", {})
    if not isinstance(readiness, Mapping):
        raise InvalidFederationScenario(f"arm {arm_id!r} readiness must be an object")
    unmet_readiness = sorted(
        name for name in required_readiness if readiness.get(name) is not True
    )

    session_connected = observations.get("sessionConnected") is True
    accessibility_ready = (
        session_connected
        and not missing_participants
        and not missing_capabilities
        and not unmet_readiness
    )

    media_paths = observations.get("mediaPaths", [])
    if not isinstance(media_paths, list):
        raise InvalidFederationScenario(f"arm {arm_id!r} mediaPaths must be a list")

    termination_points: set[str] = set()
    all_legs_encrypted = True
    for index, path in enumerate(media_paths):
        if not isinstance(path, Mapping):
            raise InvalidFederationScenario(f"mediaPaths[{index}] must be an object")
        if path.get("encrypted") is not True:
            all_legs_encrypted = False
        terminated_at = path.get("terminatedAt")
        if terminated_at is not None:
            if not isinstance(terminated_at, str) or not terminated_at:
                raise InvalidFederationScenario(
                    f"mediaPaths[{index}].terminatedAt must be a non-empty string"
                )
            termination_points.add(terminated_at)

    security = observations.get("security", {})
    if not isinstance(security, Mapping):
        raise InvalidFederationScenario(f"arm {arm_id!r} security must be an object")
    claimed_unqualified_e2ee = security.get("claimedUnqualifiedE2ee") is True

    # Multiple encrypted legs can still be secure transport, but a media-terminating
    # bridge means an unqualified end-to-end claim is not supported by this evidence.
    security_claim_valid = all_legs_encrypted and not (
        claimed_unqualified_e2ee and termination_points
    )

    terminal_verdict = (
        "ready" if accessibility_ready and security_claim_valid else "not-ready"
    )

    return FederatedSessionResult(
        arm_id=arm_id,
        session_connected=session_connected,
        accessibility_ready=accessibility_ready,
        security_claim_valid=security_claim_valid,
        terminal_verdict=terminal_verdict,
        missing_participants=tuple(sorted(missing_participants)),
        missing_capabilities=tuple(sorted(missing_capabilities)),
        unmet_readiness=tuple(unmet_readiness),
        media_termination_points=tuple(sorted(termination_points)),
    )
