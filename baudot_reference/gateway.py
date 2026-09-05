"""Deterministic RFC 4103 ↔ RFC 8865 T.140 gateway trial harness.

This module composes Baudot's existing reference boundaries. It is intentionally
not a socket, browser, SIP, or production gateway. Its purpose is to execute the
portable BAUDOT-INTEROP-002 semantic trials while preserving source transport,
normalized T.140, target transport, presentation, and loss-marker evidence as
separate observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .rfc2198 import RedundantT140Generation, Rfc2198T140Packet
from .rfc4103 import PrimaryT140RtpPacket
from .rfc4103_recovery import RecoveredT140Block, recover_forward_gap
from .rfc8865 import T140DataChannelMessage, replacement_marker_for_possible_loss
from .t140 import apply_t140_baseline
from .t140block import T140Block

T140_PAYLOAD_TYPE = 98
RED_PAYLOAD_TYPE = 99
SSRC = 0x0BAD_D00D
BASE_TIMESTAMP = 10_000


@dataclass(frozen=True, slots=True)
class GatewayTrialResult:
    trial_id: str
    source_transport: str
    target_transport: str
    source_trace: tuple[dict[str, Any], ...]
    normalized_trace: tuple[dict[str, Any], ...]
    target_trace: tuple[dict[str, Any], ...]
    presentation: str
    missing_text_markers: int
    expected_presentation: str
    expected_missing_text_markers: int
    verdict: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "trialId": self.trial_id,
            "sourceTransport": self.source_transport,
            "targetTransport": self.target_transport,
            "sourceTrace": list(self.source_trace),
            "normalizedTrace": list(self.normalized_trace),
            "targetTrace": list(self.target_trace),
            "presentation": self.presentation,
            "missingTextMarkers": self.missing_text_markers,
            "expectedPresentation": self.expected_presentation,
            "expectedMissingTextMarkers": self.expected_missing_text_markers,
            "verdict": self.verdict,
        }


def _code_point(value: str) -> int:
    if not isinstance(value, str) or not value.startswith("U+"):
        raise ValueError(f"invalid T.140 code-point token {value!r}")
    return int(value[2:], 16)


def _blocks_from_tokens(tokens: list[str]) -> tuple[T140Block, ...]:
    return tuple(T140Block.from_text(chr(_code_point(token))) for token in tokens)


def _normalized(block: T140Block, *, source: str, sequence_number: int | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {
        "source": source,
        "t140Hex": block.utf8_hex,
        "text": block.text,
    }
    if sequence_number is not None:
        item["sequenceNumber"] = sequence_number
    return item


def _render(blocks: tuple[T140Block, ...]) -> tuple[str, int]:
    code_points = [ord(character) for block in blocks for character in block.text]
    result = apply_t140_baseline(code_points)
    return result.display_text, result.missing_text_markers


def _direct_packet(block: T140Block, sequence_number: int, *, marker: bool = False) -> tuple[PrimaryT140RtpPacket, dict[str, Any]]:
    packet = PrimaryT140RtpPacket(
        payload_type=T140_PAYLOAD_TYPE,
        sequence_number=sequence_number,
        timestamp=BASE_TIMESTAMP + sequence_number * 300,
        ssrc=SSRC,
        marker=marker,
        block=block,
    )
    wire = packet.to_bytes()
    parsed = PrimaryT140RtpPacket.from_bytes(wire, expected_payload_type=T140_PAYLOAD_TYPE)
    return parsed, {
        "event": "RFC4103_PRIMARY",
        "sequenceNumber": parsed.sequence_number,
        "marker": parsed.marker,
        "t140Hex": parsed.block.utf8_hex,
        "wireHex": wire.hex(" "),
    }


def _red_packet(
    *,
    sequence_number: int,
    redundant: tuple[RedundantT140Generation, ...],
    primary: T140Block,
) -> tuple[Rfc2198T140Packet, dict[str, Any]]:
    packet = Rfc2198T140Packet(
        red_payload_type=RED_PAYLOAD_TYPE,
        t140_payload_type=T140_PAYLOAD_TYPE,
        sequence_number=sequence_number,
        timestamp=BASE_TIMESTAMP + sequence_number * 300,
        ssrc=SSRC,
        marker=False,
        redundant=redundant,
        primary=primary,
    )
    wire = packet.to_bytes()
    parsed = Rfc2198T140Packet.from_bytes(
        wire,
        expected_red_payload_type=RED_PAYLOAD_TYPE,
        expected_t140_payload_type=T140_PAYLOAD_TYPE,
    )
    return parsed, {
        "event": "RFC4103_RED",
        "sequenceNumber": parsed.sequence_number,
        "redundant": [
            {"timestampOffset": item.timestamp_offset, "t140Hex": item.block.utf8_hex}
            for item in parsed.redundant
        ],
        "primaryHex": parsed.primary.utf8_hex,
        "wireHex": wire.hex(" "),
    }


def _to_datachannel(blocks: tuple[T140Block, ...]) -> tuple[tuple[dict[str, Any], ...], T140Block]:
    message = T140DataChannelMessage.from_blocks(blocks)
    received = T140DataChannelMessage.from_bytes(message.payload)
    trace = ({
        "event": "RFC8865_MESSAGE",
        "subprotocol": "t140",
        "reliable": True,
        "ordered": True,
        "payloadHex": received.utf8_hex,
    },)
    return trace, received.aggregate_block


def _to_rtp(blocks: tuple[T140Block, ...]) -> tuple[dict[str, Any], ...]:
    trace: list[dict[str, Any]] = []
    for index, block in enumerate(blocks, start=200):
        _, event = _direct_packet(block, index, marker=index == 200)
        trace.append(event)
    return tuple(trace)


def _result(
    trial: dict[str, Any],
    *,
    source_trace: tuple[dict[str, Any], ...],
    normalized_blocks: tuple[T140Block, ...],
    normalized_trace: tuple[dict[str, Any], ...],
    target_trace: tuple[dict[str, Any], ...],
) -> GatewayTrialResult:
    presentation, missing = _render(normalized_blocks)
    expected_presentation = trial["expectedPresentation"]
    expected_missing = trial["expectedMissingMarkers"]
    verdict = "pass" if presentation == expected_presentation and missing == expected_missing else "fail"
    return GatewayTrialResult(
        trial_id=trial["id"],
        source_transport=trial["sourceTransport"],
        target_transport=trial["targetTransport"],
        source_trace=source_trace,
        normalized_trace=normalized_trace,
        target_trace=target_trace,
        presentation=presentation,
        missing_text_markers=missing,
        expected_presentation=expected_presentation,
        expected_missing_text_markers=expected_missing,
        verdict=verdict,
    )


def run_gateway_trial(trial: dict[str, Any]) -> GatewayTrialResult:
    """Execute one BAUDOT-INTEROP-002 trial using deterministic reference adapters."""

    trial_id = trial["id"]
    input_blocks = _blocks_from_tokens(trial["inputT140"])

    if trial_id == "normal-rtp-to-datachannel":
        source: list[dict[str, Any]] = []
        normalized_blocks: list[T140Block] = []
        normalized: list[dict[str, Any]] = []
        for index, block in enumerate(input_blocks, start=100):
            packet, event = _direct_packet(block, index, marker=index == 100)
            source.append(event)
            normalized_blocks.append(packet.block)
            normalized.append(_normalized(packet.block, source="primary", sequence_number=packet.sequence_number))
        target, _ = _to_datachannel(tuple(normalized_blocks))
        return _result(
            trial,
            source_trace=tuple(source),
            normalized_blocks=tuple(normalized_blocks),
            normalized_trace=tuple(normalized),
            target_trace=target,
        )

    if trial_id == "normal-datachannel-to-rtp":
        message = T140DataChannelMessage.from_blocks(input_blocks)
        received = T140DataChannelMessage.from_bytes(message.payload)
        aggregate = received.aggregate_block
        source = ({
            "event": "RFC8865_MESSAGE",
            "subprotocol": "t140",
            "reliable": True,
            "ordered": True,
            "payloadHex": received.utf8_hex,
        },)
        normalized_blocks = (aggregate,)
        normalized = (_normalized(aggregate, source="datachannel"),)
        return _result(
            trial,
            source_trace=source,
            normalized_blocks=normalized_blocks,
            normalized_trace=normalized,
            target_trace=_to_rtp(normalized_blocks),
        )

    if trial_id == "recovered-rtp-loss-does-not-leak-marker":
        first, first_event = _direct_packet(input_blocks[0], 100, marker=True)
        red, red_event = _red_packet(
            sequence_number=102,
            redundant=(RedundantT140Generation(300, input_blocks[1]),),
            primary=input_blocks[2],
        )
        recovered = recover_forward_gap(first.sequence_number, red)
        normalized_blocks = (first.block,) + tuple(item.block for item in recovered)
        normalized = (
            _normalized(first.block, source="primary", sequence_number=first.sequence_number),
        ) + tuple(_normalized(item.block, source=item.source, sequence_number=item.sequence_number) for item in recovered)
        target, _ = _to_datachannel(normalized_blocks)
        return _result(
            trial,
            source_trace=(first_event, red_event),
            normalized_blocks=normalized_blocks,
            normalized_trace=normalized,
            target_trace=target,
        )

    if trial_id == "unrecovered-rtp-loss-becomes-marker":
        first, first_event = _direct_packet(T140Block.from_text("A"), 100, marker=True)
        red, red_event = _red_packet(
            sequence_number=103,
            redundant=(RedundantT140Generation(300, T140Block(b"")),),
            primary=T140Block.from_text("C"),
        )
        recovered = recover_forward_gap(first.sequence_number, red)
        normalized_blocks = (first.block,) + tuple(item.block for item in recovered)
        normalized = (
            _normalized(first.block, source="primary", sequence_number=first.sequence_number),
        ) + tuple(_normalized(item.block, source=item.source, sequence_number=item.sequence_number) for item in recovered)
        target, _ = _to_datachannel(normalized_blocks)
        return _result(
            trial,
            source_trace=(first_event, red_event),
            normalized_blocks=normalized_blocks,
            normalized_trace=normalized,
            target_trace=target,
        )

    if trial_id == "datachannel-reestablishment-suspected-loss":
        blocks = (
            T140Block.from_text("A"),
            replacement_marker_for_possible_loss(),
            T140Block.from_text("C"),
        )
        message = T140DataChannelMessage.from_blocks(blocks)
        source = ({
            "event": "RFC8865_REESTABLISHED_MESSAGE",
            "subprotocol": "t140",
            "possibleLoss": True,
            "payloadHex": message.utf8_hex,
        },)
        aggregate = T140DataChannelMessage.from_bytes(message.payload).aggregate_block
        normalized_blocks = (aggregate,)
        normalized = (_normalized(aggregate, source="datachannel-after-reestablishment"),)
        return _result(
            trial,
            source_trace=source,
            normalized_blocks=normalized_blocks,
            normalized_trace=normalized,
            target_trace=_to_rtp(normalized_blocks),
        )

    if trial_id == "empty-block-is-not-loss":
        blocks = (T140Block.from_text("A"), T140Block(b""), T140Block.from_text("B"))
        source: list[dict[str, Any]] = []
        normalized: list[dict[str, Any]] = []
        normalized_blocks: list[T140Block] = []
        for index, block in enumerate(blocks, start=100):
            packet, event = _direct_packet(block, index, marker=index == 100)
            source.append(event)
            normalized_blocks.append(packet.block)
            normalized.append(_normalized(packet.block, source="primary", sequence_number=packet.sequence_number))
        target, _ = _to_datachannel(tuple(normalized_blocks))
        return _result(
            trial,
            source_trace=tuple(source),
            normalized_blocks=tuple(normalized_blocks),
            normalized_trace=tuple(normalized),
            target_trace=target,
        )

    raise ValueError(f"unsupported BAUDOT-INTEROP-002 trial: {trial_id}")


def run_gateway_contract(contract: dict[str, Any]) -> tuple[GatewayTrialResult, ...]:
    if contract.get("id") != "BAUDOT-INTEROP-002":
        raise ValueError("gateway harness only executes BAUDOT-INTEROP-002")
    trials = contract.get("trials")
    if not isinstance(trials, list) or not trials:
        raise ValueError("BAUDOT-INTEROP-002 must declare trials")
    results = tuple(run_gateway_trial(trial) for trial in trials)
    if any(result.verdict != "pass" for result in results):
        failed = [result.trial_id for result in results if result.verdict != "pass"]
        raise AssertionError(f"gateway semantic equivalence failed: {failed}")
    return results
