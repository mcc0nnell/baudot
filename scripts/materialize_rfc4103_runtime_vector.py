#!/usr/bin/env python3
"""Materialize one canonical RFC 4103 primary RTP vector for runtime replay.

The canonical JSON + Python reference implementation remain authoritative for
packet construction. Runtime adapters consume the emitted packet bytes and
metadata rather than maintaining another serializer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from baudot_reference.rfc4103 import PrimaryT140RtpPacket
from baudot_reference.t140block import T140Block

SUITE_PATH = ROOT / "testkit" / "rfc4103" / "primary-rtp-v1.json"


def _load_suite() -> dict:
    with SUITE_PATH.open("r", encoding="utf-8") as handle:
        suite = json.load(handle)
    if not isinstance(suite, dict):
        raise ValueError("RFC 4103 runtime suite root must be an object")
    return suite


def _select(suite: dict, vector_id: str) -> dict:
    vectors = suite.get("vectors")
    if not isinstance(vectors, list):
        raise ValueError("RFC 4103 runtime suite vectors must be a list")
    for vector in vectors:
        if isinstance(vector, dict) and vector.get("id") == vector_id:
            return vector
    raise ValueError(f"unknown RFC 4103 primary vector: {vector_id}")


def _canonical_packet(vector: dict) -> bytes:
    fields = vector["fields"]
    packet = PrimaryT140RtpPacket(
        payload_type=fields["payloadType"],
        sequence_number=fields["sequenceNumber"],
        timestamp=fields["timestamp"],
        ssrc=fields["ssrc"],
        marker=fields["marker"],
        block=T140Block.from_hex(fields["t140blockHex"]),
    ).to_bytes()
    expected = bytes.fromhex(vector["packetHex"])
    if packet != expected:
        raise ValueError(f"canonical packet diverges for {vector['id']}")
    return packet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vector", default="multibyte-primary-block")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    suite = _load_suite()
    vector = _select(suite, args.vector)
    packet = _canonical_packet(vector)
    fields = vector["fields"]

    args.output.mkdir(parents=True, exist_ok=True)
    packet_path = args.output / "packet.bin"
    properties_path = args.output / "vector.properties"
    packet_path.write_bytes(packet)

    metadata = {
        "suite.id": str(suite["id"]),
        "suite.version": str(suite["version"]),
        "vector.id": str(vector["id"]),
        "packet.sha256": hashlib.sha256(packet).hexdigest(),
        "packet.hex": packet.hex(" "),
        "rtp.payloadType": str(fields["payloadType"]),
        "rtp.sequenceNumber": str(fields["sequenceNumber"]),
        "rtp.timestamp": str(fields["timestamp"]),
        "rtp.ssrc": str(fields["ssrc"]),
        "rtp.marker": str(fields["marker"]).lower(),
        "t140block.hex": " ".join(fields["t140blockHex"].split()),
    }
    properties_path.write_text(
        "".join(f"{key}={value}\n" for key, value in metadata.items()),
        encoding="utf-8",
    )

    print(f"{suite['id']}@{suite['version']} / {vector['id']}")
    print(f"packet={packet_path}")
    print(f"sha256={metadata['packet.sha256']}")


if __name__ == "__main__":
    main()
