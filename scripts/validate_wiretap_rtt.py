#!/usr/bin/env python3
"""Validate RTT evidence without trusting the Java sender's protocol classification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from baudot_reference.rfc2198 import Rfc2198T140Packet
from baudot_reference.rfc4103 import PrimaryT140RtpPacket
from baudot_reference.rfc4103_recovery import (
    infer_redundant_sequence_numbers,
    recover_forward_gap,
)
from baudot_reference.t140 import apply_t140_baseline

T140_PT = 98
RED_PT = 99
CLOCK_RATE = 1000


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_properties(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        require(bool(separator) and bool(key), f"{path}: malformed property line: {raw!r}")
        values[key] = value
    return values


def validate_sdp(text: str, *, direction: str, label: str) -> dict[str, object]:
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    media = next((line for line in lines if line.startswith("m=text ")), None)
    require(media is not None, f"{label}: missing m=text media line")
    parts = media.split()
    require(len(parts) >= 5, f"{label}: malformed m=text media line")
    require(parts[2] == "RTP/AVP", f"{label}: expected RTP/AVP")
    require(parts[3:] == [str(RED_PT), str(T140_PT)], f"{label}: payload order must be RED then T.140")
    required = {
        f"a=rtpmap:{RED_PT} red/{CLOCK_RATE}",
        f"a=fmtp:{RED_PT} {T140_PT}/{T140_PT}/{T140_PT}",
        f"a=rtpmap:{T140_PT} t140/{CLOCK_RATE}",
        f"a={direction}",
    }
    missing = required - set(lines)
    require(not missing, f"{label}: missing SDP attributes: {sorted(missing)}")
    return {
        "media": "text",
        "protocol": "RTP/AVP",
        "redPayloadType": RED_PT,
        "t140PayloadType": T140_PT,
        "clockRate": CLOCK_RATE,
        "redundancy": [T140_PT, T140_PT, T140_PT],
        "direction": direction,
    }


def validate_normal(primary: PrimaryT140RtpPacket, red: Rfc2198T140Packet) -> dict[str, object]:
    require(primary.marker is True, "initial direct T.140 packet must carry the marker bit")
    require(primary.sequence_number == 1, "unexpected initial RTP sequence number")
    require(primary.timestamp == 1000, "unexpected initial RTP timestamp")
    require(primary.block.text == "H", "unexpected initial T140block")
    require(red.marker is False, "follow-up RED packet must not carry the initial marker bit")
    require(red.sequence_number == 2, "unexpected RED RTP sequence number")
    require(red.timestamp == 1300, "unexpected RED RTP timestamp")
    require(len(red.redundant) == 1, "expected one redundant generation")
    require(red.redundant[0].timestamp_offset == 300, "unexpected RED timestamp offset")
    require(red.redundant[0].block.text == "H", "redundant T140block does not match prior primary")
    require(red.primary.text == "i", "unexpected RED primary T140block")
    require(infer_redundant_sequence_numbers(red) == (1,), "RED history does not map back to RTP sequence 1")
    recovered = recover_forward_gap(primary.sequence_number, red)
    normalized_text = primary.block.text + "".join(item.block.text for item in recovered)
    presentation = apply_t140_baseline(ord(character) for character in normalized_text)
    require(presentation.display_text == "Hi", "normalized RTT presentation is not 'Hi'")
    require(presentation.missing_text_markers == 0, "normal RTT path introduced a missing-text marker")
    return {
        "presentation": presentation.as_dict(),
        "recovery": {"gapDetected": False, "recoveredSequenceNumbers": [], "sources": [item.source for item in recovered]},
    }


def validate_recovery(caller: Path, primary: PrimaryT140RtpPacket, red: Rfc2198T140Packet) -> dict[str, object]:
    plan_path = caller / "rtt-loss-plan.json"
    require(plan_path.is_file(), "recovery profile is missing rtt-loss-plan.json")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    require(plan.get("injection") == "controlled-source-omission", "unexpected recovery injection type")
    require(plan.get("emittedSequenceNumbers") == [0, 2], "recovery plan must emit RTP sequences 0 and 2")
    require(plan.get("omittedSequenceNumbers") == [1], "recovery plan must omit RTP sequence 1")
    require(plan.get("omittedTimestamp") == 1000, "recovery plan omitted timestamp must be 1000")
    require(plan.get("omittedT140Text") == "B", "recovery plan omitted T140block must be 'B'")
    require(plan.get("recoveryCarrierSequence") == 2, "RED recovery carrier must be RTP sequence 2")
    require(plan.get("redundantTimestampOffset") == 300, "RED recovery offset must be 300 ms")
    return validate_gap_recovery(primary, red, injection=plan)


def validate_gap_recovery(
    primary: PrimaryT140RtpPacket,
    red: Rfc2198T140Packet,
    *,
    injection: dict[str, object],
) -> dict[str, object]:
    require(primary.marker is True, "recovery prior packet must carry the marker bit")
    require(primary.sequence_number == 0, "recovery prior RTP sequence must be 0")
    require(primary.timestamp == 700, "recovery prior RTP timestamp must be 700")
    require(primary.block.text == "A", "recovery prior T140block must be 'A'")
    require(red.marker is False, "recovery RED packet marker must be clear")
    require(red.sequence_number == 2, "recovery RED RTP sequence must be 2")
    require(red.timestamp == 1300, "recovery RED RTP timestamp must be 1300")
    require(len(red.redundant) == 1, "recovery RED packet must contain one redundant generation")
    require(red.redundant[0].timestamp_offset == 300, "recovery RED timestamp offset must be 300")
    require(red.redundant[0].block.text == "B", "redundant T140block must recover missing 'B'")
    require(red.primary.text == "C", "recovery RED primary T140block must be 'C'")
    require(infer_redundant_sequence_numbers(red) == (1,), "RED history must map to missing RTP sequence 1")
    recovered = recover_forward_gap(primary.sequence_number, red)
    require([item.sequence_number for item in recovered] == [1, 2], "recovery output must contain sequences 1 and 2")
    require([item.source for item in recovered] == ["redundant", "primary"], "missing sequence must be recovered from redundancy")
    require(recovered[0].block.text == "B", "recovered sequence 1 must contain 'B'")
    require(all(item.source != "missing-marker" for item in recovered), "recovery path introduced a missing-text marker source")
    normalized_text = primary.block.text + "".join(item.block.text for item in recovered)
    presentation = apply_t140_baseline(ord(character) for character in normalized_text)
    require(presentation.display_text == "ABC", "recovered RTT presentation is not 'ABC'")
    require(presentation.missing_text_markers == 0, "successful RED recovery introduced a missing-text marker")
    return {
        "presentation": presentation.as_dict(),
        "lossInjection": injection,
        "recovery": {
            "gapDetected": True,
            "previousSequenceNumber": 0,
            "observedNextSequenceNumber": 2,
            "missingSequenceNumbers": [1],
            "recoveredSequenceNumbers": [1],
            "sources": [item.source for item in recovered],
            "missingTextMarkers": 0,
        },
    }


def nft_rules(document: dict[str, object]) -> list[dict[str, object]]:
    rules: list[dict[str, object]] = []
    for item in document.get("nftables", []):
        if isinstance(item, dict) and isinstance(item.get("rule"), dict):
            rules.append(item["rule"])
    return rules


def validate_nft_fault(run_dir: Path) -> dict[str, object]:
    before = json.loads((run_dir / "network-fault-before.json").read_text(encoding="utf-8"))
    after = json.loads((run_dir / "network-fault-after.json").read_text(encoding="utf-8"))
    before_rules = nft_rules(before)
    after_rules = nft_rules(after)
    require(len(before_rules) == 1 and len(after_rules) == 1, "fault evidence must contain exactly one nftables rule")

    def inspect(rule: dict[str, object]) -> tuple[bool, bool, bool, bool, int]:
        has_destination = False
        has_dport = False
        has_sequence = False
        has_drop = False
        packets = -1
        for expression in rule.get("expr", []):
            if not isinstance(expression, dict):
                continue
            match = expression.get("match")
            if isinstance(match, dict):
                left = match.get("left")
                right = match.get("right")
                if isinstance(left, dict) and isinstance(left.get("payload"), dict):
                    payload = left["payload"]
                    if payload.get("protocol") == "ip" and payload.get("field") == "daddr" and right == "10.77.20.2":
                        has_destination = True
                    if payload.get("protocol") == "udp" and payload.get("field") == "dport" and right == 40000:
                        has_dport = True
                    if payload.get("offset") == 80 and payload.get("len") == 16 and right == 1:
                        has_sequence = True
            counter = expression.get("counter")
            if isinstance(counter, dict) and isinstance(counter.get("packets"), int):
                packets = counter["packets"]
            if "drop" in expression:
                has_drop = True
        return has_destination, has_dport, has_sequence, has_drop, packets

    before_state = inspect(before_rules[0])
    after_state = inspect(after_rules[0])
    require(all(before_state[:4]) and all(after_state[:4]), "nftables fault rule does not preserve the expected destination/port/RTP-sequence/drop selector")
    require(before_state[4] == 0, f"fault counter must begin at 0, got {before_state[4]}")
    require(after_state[4] == 1, f"fault counter must end at exactly 1 packet, got {after_state[4]}")
    return {
        "mechanism": "nftables-caller-egress",
        "destination": "10.77.20.2:40000",
        "rtpSequence": 1,
        "counterBefore": before_state[4],
        "counterAfter": after_state[4],
        "matchedDrops": after_state[4] - before_state[4],
    }


def validate_network_loss(
    run_dir: Path,
    caller: Path,
    sent: list[bytes],
    received: list[bytes],
) -> tuple[PrimaryT140RtpPacket, Rfc2198T140Packet, dict[str, object]]:
    expectation_path = caller / "rtt-network-fault-expectation.json"
    require(expectation_path.is_file(), "network-loss profile is missing rtt-network-fault-expectation.json")
    expectation = json.loads(expectation_path.read_text(encoding="utf-8"))
    require(expectation.get("injection") == "caller-network-egress-drop", "unexpected network-loss injection type")
    require(expectation.get("sentSequenceNumbers") == [0, 1, 2], "network-loss sender must emit sequences 0, 1, and 2")
    require(expectation.get("expectedReceivedSequenceNumbers") == [0, 2], "network-loss receiver expectation must be sequences 0 and 2")
    require(expectation.get("dropSequenceNumbers") == [1], "network-loss selector must target sequence 1")
    require(len(sent) == 3 and len(received) == 2, "network-loss profile must preserve 3 sent and 2 received datagrams")
    require(sent[0] == received[0] and sent[2] == received[1], "delivered network-loss datagrams changed on the route")
    require(sent[1] not in received, "targeted sequence-1 datagram unexpectedly appears in receiver evidence")

    prior = PrimaryT140RtpPacket.from_bytes(sent[0], expected_payload_type=T140_PT)
    dropped = PrimaryT140RtpPacket.from_bytes(sent[1], expected_payload_type=T140_PT)
    red = Rfc2198T140Packet.from_bytes(sent[2], expected_red_payload_type=RED_PT, expected_t140_payload_type=T140_PT)
    require(prior.sequence_number == 0 and prior.timestamp == 700 and prior.block.text == "A", "unexpected network-loss prior packet")
    require(dropped.sequence_number == 1 and dropped.timestamp == 1000 and dropped.block.text == "B", "sender evidence does not contain the targeted sequence-1/B packet")
    require(dropped.marker is False, "targeted sequence-1 packet must not carry the initial marker")
    received_prior = PrimaryT140RtpPacket.from_bytes(received[0], expected_payload_type=T140_PT)
    received_red = Rfc2198T140Packet.from_bytes(received[1], expected_red_payload_type=RED_PT, expected_t140_payload_type=T140_PT)
    require(received_prior == prior, "received prior packet differs from sender evidence")
    require(received_red == red, "received RED packet differs from sender evidence")

    fault = validate_nft_fault(run_dir)
    semantic = validate_gap_recovery(received_prior, received_red, injection={"expectation": expectation, "networkFault": fault})
    semantic["networkLoss"] = {
        "sentSequenceNumbers": [0, 1, 2],
        "receivedSequenceNumbers": [0, 2],
        "droppedSequenceNumbers": [1],
        "droppedT140Text": "B",
        "deliveredWireBytesPreserved": True,
        **fault,
    }
    return received_prior, received_red, semantic


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run_dir = args.run_dir
    scenario = run_dir.parent.name
    caller = run_dir / "caller"
    callee = run_dir / "callee"
    caller_result = read_properties(caller / "result.properties")
    callee_result = read_properties(callee / "result.properties")
    profile = caller_result.get("rtt.profile", "normal")
    require(callee_result.get("rtt.profile", "normal") == profile, "caller/callee RTT profile mismatch")
    require(profile in {"normal", "recovery", "network-loss"}, f"unsupported RTT profile: {profile}")

    sent_count = 3 if profile == "network-loss" else 2
    sent = [(caller / f"rtt-datagram-{index}-sent.bin").read_bytes() for index in range(1, sent_count + 1)]
    received = [(callee / f"rtt-datagram-{index}-received.bin").read_bytes() for index in range(1, 3)]

    offer = validate_sdp((callee / "offer.sdp").read_text(encoding="utf-8"), direction="sendonly", label="offer")
    answer = validate_sdp((caller / "answer.sdp").read_text(encoding="utf-8"), direction="recvonly", label="answer")

    if profile == "network-loss":
        primary, red, semantic = validate_network_loss(run_dir, caller, sent, received)
        wire_preserved = True
        sent_sequence_numbers = [0, 1, 2]
        received_sequence_numbers = [0, 2]
    else:
        require(sent == received, "RTT datagrams changed between sender and receiver evidence")
        observed_pts = [(packet[1] & 0x7F) for packet in received if len(packet) >= 2]
        require(observed_pts == [T140_PT, RED_PT], f"unexpected payload-type sequence: {observed_pts}")
        primary = PrimaryT140RtpPacket.from_bytes(received[0], expected_payload_type=T140_PT)
        red = Rfc2198T140Packet.from_bytes(received[1], expected_red_payload_type=RED_PT, expected_t140_payload_type=T140_PT)
        semantic = validate_normal(primary, red) if profile == "normal" else validate_recovery(caller, primary, red)
        wire_preserved = True
        sent_sequence_numbers = [primary.sequence_number, red.sequence_number]
        received_sequence_numbers = sent_sequence_numbers

    evidence: dict[str, object] = {
        "schema": "baudot.rtt-transport-evidence/v3",
        "scenario": scenario,
        "profile": profile,
        "validationAuthority": "baudot-python-reference",
        "wireBytesPreserved": wire_preserved,
        "sentSequenceNumbers": sent_sequence_numbers,
        "receivedSequenceNumbers": received_sequence_numbers,
        "sdp": {"offer": offer, "answer": answer},
        "rtp": {
            "directPayloadType": primary.payload_type,
            "redPayloadType": red.red_payload_type,
            "sequence": [primary.sequence_number, red.sequence_number],
            "timestamps": [primary.timestamp, red.timestamp],
            "redundantSequenceNumbers": list(infer_redundant_sequence_numbers(red)),
            "redundantText": red.redundant[0].block.text,
            "primaryText": [primary.block.text, red.primary.text],
        },
        **semantic,
        "claimBoundary": {
            "doesNotEstablish": [
                "full RFC 3261 conformance",
                "full RFC 4103 conformance",
                "full T.140 conformance",
                "RTCP behavior",
                "out-of-order recovery",
                "browser or WebRTC interoperability",
                "production network readiness",
                "Wiretap-native packet-loss injection" if profile == "network-loss" else "packet-loss behavior beyond the exercised profile",
            ]
        },
        "verdict": "pass",
    }

    output = run_dir / "rtt-validation.json"
    output.write_text(json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if profile == "network-loss":
        print("✓ caller sent RTP sequences 0,1,2; host-network fault dropped sequence 1 exactly once")
        print("✓ receiver observed 0,2; RFC 2198 recovered sequence 1: presentation 'ABC', missing markers 0")
    elif profile == "recovery":
        print("✓ controlled source omission created RTP sequence gap 0 → 2")
        print("✓ RFC 2198 recovered sequence 1 from redundancy: presentation 'ABC', missing markers 0")
    else:
        print("✓ RTT bytes preserved and independently validated as RFC 4103/RFC 2198 T.140")
        print("✓ presentation: 'Hi' (missing-text markers: 0)")


if __name__ == "__main__":
    main()
