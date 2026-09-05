from __future__ import annotations

import unittest

from baudot_reference import PrimaryT140RtpPacket, RedundantT140Generation, Rfc2198T140Packet, T140Block


class FederationGatewaySemanticTests(unittest.TestCase):
    def test_red_redundancy_is_not_duplicated_into_current_stream(self) -> None:
        direct = PrimaryT140RtpPacket(
            payload_type=98,
            sequence_number=100,
            timestamp=1000,
            ssrc=0x01020304,
            marker=False,
            block=T140Block.from_text("H"),
        )
        red = Rfc2198T140Packet(
            red_payload_type=99,
            t140_payload_type=98,
            sequence_number=101,
            timestamp=1300,
            ssrc=0x01020304,
            marker=False,
            redundant=(RedundantT140Generation(300, T140Block.from_text("H")),),
            primary=T140Block.from_text("i"),
        )

        parsed_direct = PrimaryT140RtpPacket.from_bytes(
            direct.to_bytes(), expected_payload_type=98
        )
        parsed_red = Rfc2198T140Packet.from_bytes(
            red.to_bytes(),
            expected_red_payload_type=99,
            expected_t140_payload_type=98,
        )

        current_stream = parsed_direct.block.text + parsed_red.primary.text
        all_red_payloads_naively_concatenated = (
            parsed_direct.block.text
            + "".join(generation.block.text for generation in parsed_red.redundant)
            + parsed_red.primary.text
        )

        self.assertEqual(current_stream, "Hi")
        self.assertEqual(parsed_red.redundant[0].block.text, "H")
        self.assertEqual(all_red_payloads_naively_concatenated, "HHi")
        self.assertNotEqual(current_stream, all_red_payloads_naively_concatenated)


if __name__ == "__main__":
    unittest.main()
