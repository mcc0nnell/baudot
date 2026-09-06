import unittest

from scripts.validate_rue_rtt_negotiation import reduce_case, remote_offers_t140


class RueRttNegotiationTests(unittest.TestCase):
    def test_t140_must_be_in_text_media_section(self):
        sdp = (
            "v=0\r\n"
            "m=audio 49170 RTP/AVP 98\r\n"
            "a=rtpmap:98 t140/1000\r\n"
        )
        self.assertFalse(remote_offers_t140(sdp))

    def test_remote_absent_cannot_negotiate_or_ready(self):
        result = reduce_case(
            {
                "id": "negative-remote-absent",
                "localRttEnabled": True,
                "remoteOffer": "v=0\r\nm=audio 49170 RTP/AVP 0\r\na=rtpmap:0 PCMU/8000\r\n",
                "answerAcceptsT140": False,
                "firstT140CharacterObserved": False,
            }
        )
        self.assertFalse(result["remoteOffersT140"])
        self.assertFalse(result["rttNegotiated"])
        self.assertFalse(result["rttReady"])
        self.assertEqual("remote-no-t140", result["reason"])

    def test_local_disabled_cannot_negotiate_or_ready(self):
        result = reduce_case(
            {
                "id": "negative-local-disabled",
                "localRttEnabled": False,
                "remoteOffer": "v=0\r\nm=text 49174 RTP/AVP 98\r\na=rtpmap:98 t140/1000\r\n",
                "answerAcceptsT140": False,
                "firstT140CharacterObserved": False,
            }
        )
        self.assertTrue(result["remoteOffersT140"])
        self.assertFalse(result["rttNegotiated"])
        self.assertFalse(result["rttReady"])
        self.assertEqual("local-rtt-disabled", result["reason"])

    def test_negotiated_without_observed_text_is_not_ready(self):
        result = reduce_case(
            {
                "id": "negotiated-no-text",
                "localRttEnabled": True,
                "remoteOffer": "v=0\r\nm=text 49178 RTP/AVP 98\r\na=rtpmap:98 t140/1000\r\n",
                "answerAcceptsT140": True,
                "firstT140CharacterObserved": False,
            }
        )
        self.assertTrue(result["rttNegotiated"])
        self.assertFalse(result["rttReady"])
        self.assertEqual("negotiated-awaiting-t140", result["reason"])

    def test_ready_requires_negotiation_and_first_text(self):
        result = reduce_case(
            {
                "id": "positive-ready-control",
                "localRttEnabled": True,
                "remoteOffer": "v=0\r\nm=text 49180 RTP/AVP 98\r\na=rtpmap:98 t140/1000\r\n",
                "answerAcceptsT140": True,
                "firstT140CharacterObserved": True,
            }
        )
        self.assertTrue(result["rttNegotiated"])
        self.assertTrue(result["rttReady"])
        self.assertEqual("ready", result["reason"])


if __name__ == "__main__":
    unittest.main()
