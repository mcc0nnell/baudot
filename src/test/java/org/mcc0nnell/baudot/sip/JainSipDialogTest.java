package org.mcc0nnell.baudot.sip;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.DatagramSocket;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;

class JainSipDialogTest {
    private static final Duration SIP_TIMEOUT = Duration.ofSeconds(5);
    private static final int H264_PAYLOAD_TYPE = 96;

    @Test
    void provesDialogSdpAndFirstRtpPacketWithCanonicalEvidence() throws Exception {
        SipTrace trace = new SipTrace();
        int[] sipPorts = reserveTwoUdpPorts();
        List<String> expectedSignals = expectedSignals();
        List<String> expectedSdp = expectedSdp();
        List<String> expectedRtp = List.of(
                "alice rtp-ready video",
                "bob rtp-ready video",
                "bob <- RTP video payload-type=96 payload-bytes=4",
                "bob rtp-payload-match video payload-type=96"
        );
        Path evidence = Path.of("target", "baudot-evidence", "sip-dialog-rtp.json");

        try (RtpProbe aliceRtp = new RtpProbe("alice", "video", trace);
             RtpProbe bobRtp = new RtpProbe("bob", "video", trace);
             JainSipEndpoint alice = new JainSipEndpoint("alice", "alice", sipPorts[0], trace);
             JainSipEndpoint bob = new JainSipEndpoint(
                     "bob", "bob", sipPorts[1], trace, videoAnswer(bobRtp.port()))) {

            alice.invite("bob", sipPorts[1], videoOffer(aliceRtp.port()));
            assertTrue(alice.awaitEstablished(SIP_TIMEOUT), "SIP dialog did not establish");

            SdpDescription.Codec negotiated = negotiatedH264(trace);
            int payloadType = Integer.parseInt(negotiated.payloadType());
            aliceRtp.sendTo(bobRtp.port(), payloadType, new byte[] {1, 2, 3, 4});
            assertTrue(bobRtp.awaitFirstPacket(Duration.ofSeconds(1), payloadType).isPresent(),
                    "Expected first RTP packet was not observed");

            alice.hangup();
            assertTrue(alice.awaitCompletion(SIP_TIMEOUT), "SIP dialog did not terminate");
        } finally {
            SipEvidenceWriter.write(
                    evidence,
                    expectedSignals,
                    trace.sentSignals(),
                    expectedSdp,
                    trace.sdpFacts(),
                    expectedRtp,
                    trace.rtpFacts(),
                    trace.mediaTransportProven());
        }

        assertEquals(expectedSignals, trace.sentSignals());
        assertEquals(expectedSdp, trace.sdpFacts());
        assertEquals(expectedRtp, trace.rtpFacts());
        assertTrue(trace.mediaTransportProven());
        assertTrue(java.nio.file.Files.isRegularFile(evidence));
    }

    @Test
    void classifiesSuccessfulSignalingAndSdpWithNoRtpAsTransportNotProven() throws Exception {
        SipTrace trace = new SipTrace();
        int[] sipPorts = reserveTwoUdpPorts();
        List<String> expectedSignals = expectedSignals();
        List<String> expectedSdp = expectedSdp();
        List<String> expectedRtp = List.of(
                "alice rtp-ready video",
                "bob rtp-ready video",
                "bob rtp-timeout video payload-type=96"
        );
        Path evidence = Path.of("target", "baudot-evidence", "sip-dialog-no-rtp.json");

        try (RtpProbe aliceRtp = new RtpProbe("alice", "video", trace);
             RtpProbe bobRtp = new RtpProbe("bob", "video", trace);
             JainSipEndpoint alice = new JainSipEndpoint("alice", "alice", sipPorts[0], trace);
             JainSipEndpoint bob = new JainSipEndpoint(
                     "bob", "bob", sipPorts[1], trace, videoAnswer(bobRtp.port()))) {

            alice.invite("bob", sipPorts[1], videoOffer(aliceRtp.port()));
            assertTrue(alice.awaitEstablished(SIP_TIMEOUT), "SIP dialog did not establish");

            int payloadType = Integer.parseInt(negotiatedH264(trace).payloadType());
            assertTrue(bobRtp.awaitFirstPacket(Duration.ofMillis(150), payloadType).isEmpty(),
                    "No-RTP fixture unexpectedly received a packet");

            alice.hangup();
            assertTrue(alice.awaitCompletion(SIP_TIMEOUT), "SIP dialog did not terminate");
        } finally {
            SipEvidenceWriter.write(
                    evidence,
                    expectedSignals,
                    trace.sentSignals(),
                    expectedSdp,
                    trace.sdpFacts(),
                    expectedRtp,
                    trace.rtpFacts(),
                    trace.mediaTransportProven());
        }

        assertEquals(expectedSignals, trace.sentSignals());
        assertEquals(expectedSdp, trace.sdpFacts());
        assertEquals(expectedRtp, trace.rtpFacts());
        assertFalse(trace.mediaTransportProven(),
                "A matched negative fixture must not be reported as successful media transport");
        assertTrue(java.nio.file.Files.isRegularFile(evidence));
    }

    private static SdpDescription.Codec negotiatedH264(SipTrace trace) {
        SdpDescription negotiated = trace.negotiatedSdp()
                .orElseThrow(() -> new AssertionError("No negotiated SDP was observed"));
        SdpDescription.Codec codec = negotiated.findCodec("video", "H264")
                .orElseThrow(() -> new AssertionError("H.264 was not negotiated"));
        assertEquals(String.valueOf(H264_PAYLOAD_TYPE), codec.payloadType());
        return codec;
    }

    private static List<String> expectedSignals() {
        return List.of(
                "alice -> INVITE",
                "bob -> 100 INVITE",
                "bob -> 180 INVITE",
                "bob -> 200 INVITE",
                "alice -> ACK",
                "alice -> BYE",
                "bob -> 200 BYE"
        );
    }

    private static List<String> expectedSdp() {
        return List.of(
                "bob <- offer video RTP/AVP [H264/90000,VP8/90000]",
                "alice <- answer video RTP/AVP [H264/90000]",
                "negotiated video RTP/AVP [H264/90000]"
        );
    }

    private static String videoOffer(int rtpPort) {
        return String.join("\r\n",
                "v=0",
                "o=alice 1 1 IN IP4 127.0.0.1",
                "s=Baudot",
                "c=IN IP4 127.0.0.1",
                "t=0 0",
                "m=video " + rtpPort + " RTP/AVP 96 97",
                "a=rtpmap:96 H264/90000",
                "a=rtpmap:97 VP8/90000",
                "a=sendrecv",
                "");
    }

    private static String videoAnswer(int rtpPort) {
        return String.join("\r\n",
                "v=0",
                "o=bob 1 1 IN IP4 127.0.0.1",
                "s=Baudot",
                "c=IN IP4 127.0.0.1",
                "t=0 0",
                "m=video " + rtpPort + " RTP/AVP 96",
                "a=rtpmap:96 H264/90000",
                "a=sendrecv",
                "");
    }

    private static int[] reserveTwoUdpPorts() throws Exception {
        try (DatagramSocket first = new DatagramSocket(0);
             DatagramSocket second = new DatagramSocket(0)) {
            return new int[] {first.getLocalPort(), second.getLocalPort()};
        }
    }
}
