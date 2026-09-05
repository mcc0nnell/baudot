package org.mcc0nnell.baudot.sip;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.DatagramSocket;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;

class JainSipDialogTest {
    private static final String VIDEO_OFFER = String.join("\r\n",
            "v=0",
            "o=alice 1 1 IN IP4 127.0.0.1",
            "s=Baudot",
            "c=IN IP4 127.0.0.1",
            "t=0 0",
            "m=video 40000 RTP/AVP 96 97",
            "a=rtpmap:96 H264/90000",
            "a=rtpmap:97 VP8/90000",
            "a=sendrecv",
            "");

    private static final String VIDEO_ANSWER = String.join("\r\n",
            "v=0",
            "o=bob 1 1 IN IP4 127.0.0.1",
            "s=Baudot",
            "c=IN IP4 127.0.0.1",
            "t=0 0",
            "m=video 40002 RTP/AVP 96",
            "a=rtpmap:96 H264/90000",
            "a=sendrecv",
            "");

    @Test
    void provesDialogAndSdpNegotiationWithCanonicalEvidence() throws Exception {
        SipTrace trace = new SipTrace();
        int[] ports = reserveTwoUdpPorts();
        List<String> expectedSignals = List.of(
                "alice -> INVITE",
                "bob -> 100 INVITE",
                "bob -> 180 INVITE",
                "bob -> 200 INVITE",
                "alice -> ACK",
                "alice -> BYE",
                "bob -> 200 BYE"
        );
        List<String> expectedSdp = List.of(
                "bob <- offer video RTP/AVP [H264/90000,VP8/90000]",
                "alice <- answer video RTP/AVP [H264/90000]",
                "negotiated video RTP/AVP [H264/90000]"
        );
        Path evidence = Path.of("target", "baudot-evidence", "sip-dialog.json");

        try (JainSipEndpoint alice = new JainSipEndpoint("alice", "alice", ports[0], trace);
             JainSipEndpoint bob = new JainSipEndpoint("bob", "bob", ports[1], trace, VIDEO_ANSWER)) {

            alice.invite("bob", ports[1], VIDEO_OFFER);
            assertTrue(alice.awaitCompletion(Duration.ofSeconds(5)), "SIP dialog did not complete");
        } finally {
            SipEvidenceWriter.write(
                    evidence,
                    expectedSignals,
                    trace.sentSignals(),
                    expectedSdp,
                    trace.sdpFacts());
        }

        assertEquals(expectedSignals, trace.sentSignals());
        assertEquals(expectedSdp, trace.sdpFacts());
        assertTrue(java.nio.file.Files.isRegularFile(evidence));
    }

    private static int[] reserveTwoUdpPorts() throws Exception {
        try (DatagramSocket first = new DatagramSocket(0);
             DatagramSocket second = new DatagramSocket(0)) {
            return new int[] {first.getLocalPort(), second.getLocalPort()};
        }
    }
}
