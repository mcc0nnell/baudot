#!/usr/bin/env python3
"""Independently reduce the live JAIN SIP RUE RTT negotiation probe.

Java is signaling evidence only. This reducer reads the SDP bytes observed on
opposite sides of each dialog, classifies T.140 capability/acceptance, joins the
controlled local policy input, and keeps readiness false because this probe
intentionally sends no RTT media.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_rue_rtt_negotiation import active_t140, remote_offers_t140

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "testkit" / "vrs" / "fixtures" / "rue-rtt-negotiation-arms-v1.json"
EVIDENCE = ROOT / "target" / "evidence" / "RUE-RTT-NEGOTIATION-LIVE"


def read_properties(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def as_bool(value: str | None, label: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"{label}: expected literal true/false, got {value!r}")


def expected_reason(remote_t140: bool, local_enabled: bool, answer_accepts: bool) -> str:
    if not remote_t140:
        return "remote-no-t140"
    if not local_enabled:
        return "local-rtt-disabled"
    if not answer_accepts:
        return "answer-does-not-accept-t140"
    return "negotiated-awaiting-t140"


def main() -> int:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    expected_by_id = {case["id"]: case["expected"] for case in fixture["cases"]}
    expected_local = {case["id"]: bool(case["localRttEnabled"]) for case in fixture["cases"]}

    results: list[dict[str, object]] = []
    for arm in sorted(expected_by_id):
        directory = EVIDENCE / arm
        observation_path = directory / "observation.properties"
        offer_path = directory / "offer-observed.sdp"
        answer_path = directory / "answer-observed.sdp"
        for required in (observation_path, offer_path, answer_path):
            if not required.is_file():
                raise ValueError(f"{arm}: missing live evidence {required.relative_to(ROOT)}")

        observation = read_properties(observation_path)
        if observation.get("schema") != "baudot.rue-rtt-live-observation@1":
            raise ValueError(f"{arm}: unexpected Java observation schema")
        if observation.get("arm") != arm:
            raise ValueError(f"{arm}: Java observation arm mismatch")
        if observation.get("claim") != "controlled-live-sdp-negotiation-only":
            raise ValueError(f"{arm}: live claim boundary drift")
        if observation.get("javaVerdictAuthority") != "false":
            raise ValueError(f"{arm}: Java must never hold RTT verdict authority")
        if observation.get("error"):
            raise ValueError(f"{arm}: Java signaling error: {observation['error']}")
        if not as_bool(observation.get("dialogEstablished"), f"{arm} dialogEstablished"):
            raise ValueError(f"{arm}: SIP dialog did not establish")
        if not as_bool(observation.get("ackObserved"), f"{arm} ackObserved"):
            raise ValueError(f"{arm}: ACK was not observed")
        if as_bool(observation.get("rttMediaAttempted"), f"{arm} rttMediaAttempted"):
            raise ValueError(f"{arm}: negotiation-only probe must not originate RTT media")

        local_enabled = as_bool(observation.get("localRttEnabled"), f"{arm} localRttEnabled")
        if local_enabled != expected_local[arm]:
            raise ValueError(f"{arm}: live local policy drifted from fixture")

        offer = offer_path.read_text(encoding="utf-8")
        answer = answer_path.read_text(encoding="utf-8")
        remote_t140 = remote_offers_t140(offer)
        answer_accepts = active_t140(answer)
        negotiated = local_enabled and remote_t140 and answer_accepts
        first_observed = False
        ready = False
        reason = expected_reason(remote_t140, local_enabled, answer_accepts)

        projection = {
            "remoteOffersT140": remote_t140,
            "rttNegotiated": negotiated,
            "firstT140CharacterObserved": first_observed,
            "rttReady": ready,
            "reason": reason,
        }
        if projection != expected_by_id[arm]:
            raise ValueError(
                f"{arm}: live reduction {projection} != fixture expectation {expected_by_id[arm]}"
            )

        configured_remote = as_bool(
            observation.get("configuredRemoteOffersT140"),
            f"{arm} configuredRemoteOffersT140",
        )
        configured_answer = as_bool(
            observation.get("configuredAnswerAcceptsT140"),
            f"{arm} configuredAnswerAcceptsT140",
        )
        if configured_remote != remote_t140:
            raise ValueError(f"{arm}: observed offer disagrees with Java configured remote capability")
        if configured_answer != answer_accepts:
            raise ValueError(f"{arm}: observed answer disagrees with Java configured acceptance")

        if list(directory.glob("*.bin")):
            raise ValueError(f"{arm}: unexpected media datagram evidence in negotiation-only lane")

        result = {
            "schema": "baudot.rue-rtt-live-reduction@1",
            "arm": arm,
            "dialogEstablished": True,
            "ackObserved": True,
            "localRttEnabled": local_enabled,
            "remoteOffersT140": remote_t140,
            "answerAcceptsT140": answer_accepts,
            "rttNegotiated": negotiated,
            "firstT140CharacterObserved": first_observed,
            "rttReady": ready,
            "reason": reason,
            "signalingImplementation": "JAIN SIP",
            "verdictAuthority": "baudot-independent-python-reducer",
            "claimBoundary": "controlled live SIP/SDP negotiation only; no RTT media attempted",
        }
        (directory / "live-result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        results.append(result)
        print(
            f"{arm}: dialog=true remoteT140={str(remote_t140).lower()} "
            f"answerT140={str(answer_accepts).lower()} negotiated={str(negotiated).lower()} "
            "firstT140=false ready=false PASS"
        )

    summary = {
        "schema": "baudot.rue-rtt-live-reduction-summary@1",
        "arms": len(results),
        "dialogsEstablished": sum(1 for item in results if item["dialogEstablished"]),
        "negotiatedArms": sum(1 for item in results if item["rttNegotiated"]),
        "readyArms": sum(1 for item in results if item["rttReady"]),
        "claimBoundary": "live negotiation evidence does not establish RTT readiness",
    }
    (EVIDENCE / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("Live JAIN RUE RTT negotiation independent reduction: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
