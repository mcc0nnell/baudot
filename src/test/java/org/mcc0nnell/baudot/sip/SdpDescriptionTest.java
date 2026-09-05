package org.mcc0nnell.baudot.sip;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class SdpDescriptionTest {
    @Test
    void derivesStableNegotiatedCodecFactsFromOfferAndAnswer() {
        SdpDescription offer = SdpDescription.parse(("""
                v=0
                m=video 40000 RTP/AVP 96 97
                a=rtpmap:96 H264/90000
                a=rtpmap:97 VP8/90000
                """).getBytes(StandardCharsets.UTF_8));
        SdpDescription answer = SdpDescription.parse(("""
                v=0
                m=video 40002 RTP/AVP 96
                a=rtpmap:96 H264/90000
                """).getBytes(StandardCharsets.UTF_8));

        assertEquals("video RTP/AVP [H264/90000,VP8/90000]", offer.semanticSummary());
        assertEquals("video RTP/AVP [H264/90000]", answer.semanticSummary());
        assertEquals("video RTP/AVP [H264/90000]", offer.negotiatedWith(answer).semanticSummary());
    }
}
