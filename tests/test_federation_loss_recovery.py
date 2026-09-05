from __future__ import annotations

import unittest

from baudot_reference import (
    PrimaryT140RtpPacket,
    RedundantT140Generation,
    Rfc2198T140Packet,
    T140Block,
    recover_forward_gap,
)


class FederationLossRecoveryTests(unittest.TestCase):
    def test_missing_generation_is_recovered_once_before_current_primary(self) -> None:
        prior = PrimaryT140RtpPacket(
            payload_type=98,
            sequence_number=0,
            timestamp=700,
            ssrc=0x42415544,
            marker=True,
            block=T140Block.from_text("A"),
        )
        carrier = Rfc2198T140Packet(
            red_payload_type=99,
            t140_payload_type=98,
            sequence_number=2,
            timestamp=1300,
            ssrc=0x42415544,
            marker=False,
            redundant=(RedundantT140Generation(300, T140Block.from_text("B")),),
            primary=T140Block.from_text("C"),
        )

        parsed_prior = PrimaryT140RtpPacket.from_bytes(
            prior.to_bytes(), expected_payload_type=98
        )
        parsed_carrier = Rfc2198T140Packet.from_bytes(
            carrier.to_bytes(),
            expected_red_payload_type=99,
            expected_t140_payload_type=98,
        )
        recovered = recover_forward_gap(parsed_prior.sequence_number, parsed_carrier)

        self.assertEqual(
            [(block.sequence_number, block.block.text, block.source) for block in recovered],
            [(1, "B", "redundant"), (2, "C", "primary")],
        )
        self.assertEqual(
            parsed_prior.block.text + "".join(block.block.text for block in recovered),
            "ABC",
        )
        self.assertNotIn("missing-marker", [block.source for block in recovered])


if __name__ == "__main__":
    unittest.main()
