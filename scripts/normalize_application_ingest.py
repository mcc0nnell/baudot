#!/usr/bin/env python3
"""Normalize bounded application-source observations into Baudot session facts."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA = "baudot.session-observation@1"
NEVER_ESTABLISHES = [
    "accessibility.caption.ready",
    "rttReady",
    "t140Semantics",
    "rfc4103Media",
    "endToEndAccessibility",
]


class NormalizationError(ValueError):
    """Raised when a source fixture cannot be normalized without guessing."""


def _require_object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise NormalizationError(f"{label} must be an object")
    return value


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NormalizationError(f"{label} must be a non-empty string")
    return value


def _require_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise NormalizationError(f"{label} must be an integer")
    return value


def _event_id(source_family: str, source_session_id: str, *parts: object) -> str:
    material = "|".join([source_family, source_session_id, *(str(part) for part in parts)])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _base(
    *,
    source_family: str,
    source_session_id: str,
    source_participant_id: str | None,
    occurred_at_ms: int,
    event_type: str,
    event_parts: tuple[object, ...],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "eventId": _event_id(source_family, source_session_id, *event_parts),
        "source": {
            "family": source_family,
            "sourceSessionId": source_session_id,
        },
        "eventType": event_type,
        "occurredAtMs": occurred_at_ms,
        "authority": {
            "classification": "source-observation-only",
            "doesNotEstablish": NEVER_ESTABLISHES,
        },
    }
    if source_participant_id is not None:
        result["participant"] = {"sourceParticipantId": source_participant_id}
    return result


def normalize_zoom_rtms(document: dict[str, Any]) -> dict[str, Any]:
    source_session_id = _require_string(document.get("sourceSessionId"), "Zoom sourceSessionId")
    message = _require_object(document.get("message"), "Zoom message")
    msg_type = _require_int(message.get("msg_type"), "Zoom msg_type")
    content = _require_object(message.get("content"), "Zoom message.content")

    source_participant_id = str(_require_int(content.get("user_id"), "Zoom content.user_id"))
    occurred_at_ms = _require_int(content.get("timestamp"), "Zoom content.timestamp")

    if msg_type == 17:
        text = _require_string(content.get("data"), "Zoom transcript data")
        start_time_ms = _require_int(content.get("start_time"), "Zoom content.start_time")
        end_time_ms = _require_int(content.get("end_time"), "Zoom content.end_time")
        language_id = _require_int(content.get("language"), "Zoom content.language")
        result = _base(
            source_family="zoom-rtms",
            source_session_id=source_session_id,
            source_participant_id=source_participant_id,
            occurred_at_ms=occurred_at_ms,
            event_type="text.transcript.observed",
            event_parts=(msg_type, occurred_at_ms, source_participant_id),
        )
        result["observation"] = {
            "text": text,
            "startTimeMs": start_time_ms,
            "endTimeMs": end_time_ms,
            "languageId": language_id,
        }
        return result

    if msg_type == 14:
        bytes_observed = _require_int(document.get("bytesObserved"), "Zoom bytesObserved")
        if bytes_observed <= 0:
            raise NormalizationError("Zoom bytesObserved must be positive")
        result = _base(
            source_family="zoom-rtms",
            source_session_id=source_session_id,
            source_participant_id=source_participant_id,
            occurred_at_ms=occurred_at_ms,
            event_type="media.audio.observed",
            event_parts=(msg_type, occurred_at_ms, source_participant_id),
        )
        result["observation"] = {
            "bytesObserved": bytes_observed,
            "format": _require_string(document.get("format"), "Zoom format"),
            "sampleRateHz": _require_int(document.get("sampleRateHz"), "Zoom sampleRateHz"),
            "channels": _require_int(document.get("channels"), "Zoom channels"),
        }
        return result

    raise NormalizationError(f"unsupported Zoom RTMS msg_type {msg_type}")


def normalize_teams_graph_media(document: dict[str, Any]) -> dict[str, Any]:
    observation = _require_object(document.get("adapterObservation"), "Teams adapterObservation")
    kind = _require_string(observation.get("kind"), "Teams adapterObservation.kind")
    source_session_id = _require_string(observation.get("callId"), "Teams callId")
    occurred_at_ms = _require_int(observation.get("timestampMs"), "Teams timestampMs")

    if kind == "audio-buffer":
        source_participant_id = _require_string(
            observation.get("participantId"), "Teams participantId"
        )
        bytes_observed = _require_int(observation.get("bytesObserved"), "Teams bytesObserved")
        if bytes_observed <= 0:
            raise NormalizationError("Teams bytesObserved must be positive")
        result = _base(
            source_family="teams-graph-media",
            source_session_id=source_session_id,
            source_participant_id=source_participant_id,
            occurred_at_ms=occurred_at_ms,
            event_type="media.audio.observed",
            event_parts=(kind, occurred_at_ms, source_participant_id),
        )
        result["observation"] = {
            "bytesObserved": bytes_observed,
            "format": _require_string(observation.get("format"), "Teams format"),
            "sampleRateHz": _require_int(observation.get("sampleRateHz"), "Teams sampleRateHz"),
            "channels": _require_int(observation.get("channels"), "Teams channels"),
        }
        return result

    if kind == "call-established":
        result = _base(
            source_family="teams-graph-media",
            source_session_id=source_session_id,
            source_participant_id=None,
            occurred_at_ms=occurred_at_ms,
            event_type="signaling.connected",
            event_parts=(kind, occurred_at_ms),
        )
        result["observation"] = {"state": "established"}
        return result

    raise NormalizationError(f"unsupported Teams adapter observation kind {kind}")


def normalize(document: dict[str, Any]) -> dict[str, Any]:
    source_family = _require_string(document.get("sourceFamily"), "sourceFamily")
    if source_family == "zoom-rtms":
        return normalize_zoom_rtms(document)
    if source_family == "teams-graph-media":
        return normalize_teams_graph_media(document)
    raise NormalizationError(f"unsupported sourceFamily {source_family}")


def load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    return _require_object(value, str(path))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: normalize_application_ingest.py FIXTURE.json", file=sys.stderr)
        return 2
    result = normalize(load(Path(args[0])))
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
