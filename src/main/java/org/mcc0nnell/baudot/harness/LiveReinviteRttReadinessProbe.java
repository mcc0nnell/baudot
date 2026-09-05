package org.mcc0nnell.baudot.harness;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.Arrays;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import javax.sip.DialogTerminatedEvent;
import javax.sip.IOExceptionEvent;
import javax.sip.ListeningPoint;
import javax.sip.RequestEvent;
import javax.sip.ResponseEvent;
import javax.sip.ServerTransaction;
import javax.sip.SipFactory;
import javax.sip.SipListener;
import javax.sip.SipProvider;
import javax.sip.SipStack;
import javax.sip.TimeoutEvent;
import javax.sip.TransactionTerminatedEvent;
import javax.sip.address.Address;
import javax.sip.address.AddressFactory;
import javax.sip.address.SipURI;
import javax.sip.header.CSeqHeader;
import javax.sip.header.ContactHeader;
import javax.sip.header.HeaderFactory;
import javax.sip.header.ToHeader;
import javax.sip.message.MessageFactory;
import javax.sip.message.Request;
import javax.sip.message.Response;

/**
 * Live stale-SDP readiness gate for BAUDOT-INTEROP-003.
 *
 * A raw UDP peer establishes a real JAIN SIP dialog. A control re-INVITE gets
 * fresh text/t140 SDP and an independently observed RFC 4103 primary packet.
 * A later re-INVITE deliberately receives the prior answer SDP under 200 OK;
 * the peer follows the advertised stale port while the intended fresh receiver
 * listens elsewhere, proving that signaling success can coexist with RTT
 * readiness failure in this controlled mismatch.
 */
public final class LiveReinviteRttReadinessProbe {
    private static final String SCENARIO = "BAUDOT-INTEROP-003";
    private static final String CORRELATION = "jain-live-rtt-readiness-v1";
    private static final String HOST = "127.0.0.1";
    private static final int UAS_PORT = 5092;
    private static final int PEER_PORT = 5093;
    private static final int CONTROL_RTT_PORT = 42202;
    private static final int STALE_EXPECTED_RTT_PORT = 42203;
    private static final String CALL_ID = "baudot-live-rtt-readiness@127.0.0.1";
    private static final String FROM_TAG = "baudot-rtt-caller";
    private static final String TO_TAG = "baudot-rtt-callee";
    private static final Duration TIMEOUT = Duration.ofSeconds(5);

    private LiveReinviteRttReadinessProbe() {
    }

    public static void main(String[] args) throws Exception {
        int exit = run();
        System.exit(exit);
    }

    private static int run() throws Exception {
        Path evidenceRoot = Path.of(env("BAUDOT_EVIDENCE_DIR", "target/evidence"));
        String controlAnswer = sdp(CONTROL_RTT_PORT, "answer-control");
        String expectedFreshAnswer = sdp(STALE_EXPECTED_RTT_PORT, "answer-stale-fresh");

        try (EvidenceRecorder evidence = new EvidenceRecorder(
                evidenceRoot, SCENARIO, CORRELATION, "live-rtt-readiness");
             LiveUas uas = new LiveUas(evidence, controlAnswer);
             DatagramSocket peer = new DatagramSocket(new InetSocketAddress(InetAddress.getByName(HOST), PEER_PORT))) {

            peer.setSoTimeout((int) TIMEOUT.toMillis());
            uas.start();

            RawResponse initial = transact(peer, evidence, 1, null, "initial", sdp(41201, "offer-initial"));
            require(initial.status() == Response.OK, "initial INVITE did not receive 200");
            require(TO_TAG.equals(initial.toTag()), "initial dialog To tag mismatch");
            sendAck(peer, evidence, 1, "initial-ack.request.sip");
            require(uas.awaitAck(1, TIMEOUT), "initial ACK not observed");

            boolean controlReceived;
            byte[] controlBytes;
            RawResponse control;
            try (DatagramSocket receiver = rttReceiver(CONTROL_RTT_PORT)) {
                control = transact(peer, evidence, 2, TO_TAG, "control", sdp(41202, "offer-control"));
                require(control.status() == Response.OK, "control re-INVITE did not receive 200");
                evidence.writeBytes("control.answer.sdp", control.body().getBytes(StandardCharsets.UTF_8));
                sendAck(peer, evidence, 2, "control-ack.request.sip");
                require(uas.awaitAck(2, TIMEOUT), "control ACK not observed");

                int advertised = textPort(control.body());
                byte[] packet = RttSipProbe.normalPrimaryPacket();
                evidence.writeBytes("control-rtt-sent.bin", packet);
                sendRtt(peer, advertised, packet, evidence, "control");
                controlBytes = receiveRtt(receiver, 1200);
                controlReceived = controlBytes != null;
                if (controlReceived) {
                    evidence.writeBytes("control-rtt-received.bin", controlBytes);
                }
            }

            RawResponse stale;
            boolean staleReceived;
            try (DatagramSocket intendedFreshReceiver = rttReceiver(STALE_EXPECTED_RTT_PORT)) {
                stale = transact(peer, evidence, 3, TO_TAG, "stale", sdp(41203, "offer-stale"));
                require(stale.status() == Response.OK, "stale-SDP re-INVITE did not receive 200");
                evidence.writeBytes("stale.answer.sdp", stale.body().getBytes(StandardCharsets.UTF_8));
                evidence.writeBytes("stale.expected-fresh-answer.sdp", expectedFreshAnswer.getBytes(StandardCharsets.UTF_8));
                sendAck(peer, evidence, 3, "stale-ack.request.sip");
                require(uas.awaitAck(3, TIMEOUT), "stale ACK not observed");

                int advertised = textPort(stale.body());
                byte[] packet = RttSipProbe.normalPrimaryPacket();
                evidence.writeBytes("stale-rtt-sent.bin", packet);
                sendRtt(peer, advertised, packet, evidence, "stale");
                byte[] observed = receiveRtt(intendedFreshReceiver, 900);
                staleReceived = observed != null;
                if (staleReceived) {
                    evidence.writeBytes("stale-rtt-received.bin", observed);
                } else {
                    evidence.writeBytes(
                            "stale-rtt-timeout.txt",
                            ("no datagram observed on intended fresh port " + STALE_EXPECTED_RTT_PORT + "\n")
                                    .getBytes(StandardCharsets.UTF_8));
                }
            }

            String controlHash = sha256(control.body().getBytes(StandardCharsets.UTF_8));
            String staleHash = sha256(stale.body().getBytes(StandardCharsets.UTF_8));
            String expectedFreshHash = sha256(expectedFreshAnswer.getBytes(StandardCharsets.UTF_8));
            boolean staleDetected = staleHash.equals(controlHash) && !staleHash.equals(expectedFreshHash);
            boolean controlWirePreserved = controlReceived
                    && Arrays.equals(controlBytes, RttSipProbe.normalPrimaryPacket());

            boolean pass = control.status() == Response.OK
                    && stale.status() == Response.OK
                    && textPort(control.body()) == CONTROL_RTT_PORT
                    && textPort(stale.body()) == CONTROL_RTT_PORT
                    && controlWirePreserved
                    && staleDetected
                    && !staleReceived;

            evidence.event("readiness.control.observed", Map.of(
                    "sipStatus", Integer.toString(control.status()),
                    "advertisedTextPort", Integer.toString(textPort(control.body())),
                    "datagramReceived", Boolean.toString(controlReceived),
                    "wireBytesPreserved", Boolean.toString(controlWirePreserved)));
            evidence.event("readiness.stale.observed", Map.of(
                    "sipStatus", Integer.toString(stale.status()),
                    "advertisedTextPort", Integer.toString(textPort(stale.body())),
                    "intendedFreshTextPort", Integer.toString(STALE_EXPECTED_RTT_PORT),
                    "datagramReceivedAtIntendedFreshPort", Boolean.toString(staleReceived),
                    "staleSdpDetected", Boolean.toString(staleDetected)));

            evidence.result(Map.ofEntries(
                    Map.entry("control.answer.sha256", controlHash),
                    Map.entry("control.datagram.received", Boolean.toString(controlReceived)),
                    Map.entry("control.rtt.advertisedPort", Integer.toString(textPort(control.body()))),
                    Map.entry("control.sip.status", Integer.toString(control.status())),
                    Map.entry("control.wireBytesPreserved", Boolean.toString(controlWirePreserved)),
                    Map.entry("correlation.id", CORRELATION),
                    Map.entry("harness.layer", "jain-sip-live-rtt-readiness"),
                    Map.entry("scenario.id", SCENARIO),
                    Map.entry("scenario.result", pass ? "PASS" : "FAIL"),
                    Map.entry("stale.answer.expectedFreshSha256", expectedFreshHash),
                    Map.entry("stale.answer.observedSha256", staleHash),
                    Map.entry("stale.answer.reusedControl", Boolean.toString(staleHash.equals(controlHash))),
                    Map.entry("stale.datagram.receivedAtIntendedFreshPort", Boolean.toString(staleReceived)),
                    Map.entry("stale.rtt.advertisedPort", Integer.toString(textPort(stale.body()))),
                    Map.entry("stale.rtt.intendedFreshPort", Integer.toString(STALE_EXPECTED_RTT_PORT)),
                    Map.entry("stale.sdp.detected", Boolean.toString(staleDetected)),
                    Map.entry("stale.sip.status", Integer.toString(stale.status()))));

            return pass ? 0 : 2;
        }
    }

    private static RawResponse transact(
            DatagramSocket peer,
            EvidenceRecorder evidence,
            long cseq,
            String toTag,
            String label,
            String offer) throws Exception {
        String request = invite(cseq, toTag, "z9hG4bK-rtt-" + cseq, offer);
        sendSip(peer, request, evidence, label + ".request.sip");
        evidence.writeBytes(label + ".offer.sdp", offer.getBytes(StandardCharsets.UTF_8));
        return receiveFinal(peer, cseq, evidence, label);
    }

    private static void sendAck(DatagramSocket peer, EvidenceRecorder evidence, long cseq, String file)
            throws Exception {
        sendSip(peer, ack(cseq, "z9hG4bK-rtt-ack-" + cseq), evidence, file);
    }

    private static void sendSip(DatagramSocket socket, String message, EvidenceRecorder evidence, String file)
            throws Exception {
        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        evidence.writeBytes(file, bytes);
        socket.send(new DatagramPacket(bytes, bytes.length, InetAddress.getByName(HOST), UAS_PORT));
    }

    private static RawResponse receiveFinal(
            DatagramSocket socket, long expectedCseq, EvidenceRecorder evidence, String label) throws Exception {
        int ordinal = 0;
        while (true) {
            byte[] buffer = new byte[8192];
            DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
            socket.receive(packet);
            String raw = new String(packet.getData(), packet.getOffset(), packet.getLength(), StandardCharsets.UTF_8);
            RawResponse parsed = RawResponse.parse(raw);
            ordinal++;
            evidence.writeBytes(
                    label + "-response-" + ordinal + ".sip",
                    raw.getBytes(StandardCharsets.UTF_8));
            if (parsed.cseq() == expectedCseq && parsed.status() >= 200) {
                return parsed;
            }
        }
    }

    private static DatagramSocket rttReceiver(int port) throws Exception {
        DatagramSocket socket = new DatagramSocket(new InetSocketAddress(InetAddress.getByName(HOST), port));
        socket.setSoTimeout(1200);
        return socket;
    }

    private static void sendRtt(
            DatagramSocket peer, int port, byte[] packet, EvidenceRecorder evidence, String label) throws Exception {
        peer.send(new DatagramPacket(packet, packet.length, InetAddress.getByName(HOST), port));
        evidence.event("rtt.datagram.sent", Map.of(
                "label", label,
                "target", HOST + ":" + port,
                "bytes", Integer.toString(packet.length),
                "classification", "unvalidated"));
    }

    private static byte[] receiveRtt(DatagramSocket receiver, int timeoutMillis) throws Exception {
        receiver.setSoTimeout(timeoutMillis);
        byte[] buffer = new byte[2048];
        DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
        try {
            receiver.receive(packet);
            return Arrays.copyOfRange(packet.getData(), packet.getOffset(), packet.getOffset() + packet.getLength());
        } catch (SocketTimeoutException expected) {
            return null;
        }
    }

    private static String invite(long cseq, String toTag, String branch, String body) {
        String to = "<sip:callee@" + HOST + ":" + UAS_PORT + ">"
                + (toTag == null ? "" : ";tag=" + toTag);
        int length = body.getBytes(StandardCharsets.UTF_8).length;
        return "INVITE sip:callee@" + HOST + ":" + UAS_PORT + " SIP/2.0\r\n"
                + "Via: SIP/2.0/UDP " + HOST + ":" + PEER_PORT + ";branch=" + branch + ";rport\r\n"
                + "Max-Forwards: 70\r\n"
                + "From: <sip:caller@" + HOST + ":" + PEER_PORT + ">;tag=" + FROM_TAG + "\r\n"
                + "To: " + to + "\r\n"
                + "Call-ID: " + CALL_ID + "\r\n"
                + "CSeq: " + cseq + " INVITE\r\n"
                + "Contact: <sip:caller@" + HOST + ":" + PEER_PORT + ">\r\n"
                + "Content-Type: application/sdp\r\n"
                + "Content-Length: " + length + "\r\n\r\n"
                + body;
    }

    private static String ack(long cseq, String branch) {
        return "ACK sip:callee@" + HOST + ":" + UAS_PORT + " SIP/2.0\r\n"
                + "Via: SIP/2.0/UDP " + HOST + ":" + PEER_PORT + ";branch=" + branch + ";rport\r\n"
                + "Max-Forwards: 70\r\n"
                + "From: <sip:caller@" + HOST + ":" + PEER_PORT + ">;tag=" + FROM_TAG + "\r\n"
                + "To: <sip:callee@" + HOST + ":" + UAS_PORT + ">;tag=" + TO_TAG + "\r\n"
                + "Call-ID: " + CALL_ID + "\r\n"
                + "CSeq: " + cseq + " ACK\r\n"
                + "Content-Length: 0\r\n\r\n";
    }

    private static String sdp(int port, String session) {
        return "v=0\r\n"
                + "o=baudot 0 0 IN IP4 " + HOST + "\r\n"
                + "s=" + session + "\r\n"
                + "c=IN IP4 " + HOST + "\r\n"
                + "t=0 0\r\n"
                + "m=text " + port + " RTP/AVP 98\r\n"
                + "a=rtpmap:98 t140/1000\r\n"
                + "a=sendrecv\r\n";
    }

    private static int textPort(String body) {
        Matcher matcher = Pattern.compile("(?m)^m=text\\s+(\\d+)\\s+RTP/AVP\\s+.*$").matcher(body);
        if (!matcher.find()) {
            throw new IllegalArgumentException("response SDP has no m=text line: " + body);
        }
        return Integer.parseInt(matcher.group(1));
    }

    private static String sha256(byte[] bytes) throws Exception {
        byte[] hash = MessageDigest.getInstance("SHA-256").digest(bytes);
        StringBuilder builder = new StringBuilder(hash.length * 2);
        for (byte value : hash) {
            builder.append(String.format("%02x", value));
        }
        return builder.toString();
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }

    private static void require(boolean value, String message) {
        if (!value) {
            throw new IllegalStateException(message);
        }
    }

    private record RawResponse(int status, long cseq, String toTag, String body) {
        private static final Pattern STATUS = Pattern.compile("^SIP/2\\.0\\s+(\\d{3})", Pattern.MULTILINE);
        private static final Pattern CSEQ = Pattern.compile("(?im)^CSeq:\\s*(\\d+)\\s+INVITE\\s*$");
        private static final Pattern TO = Pattern.compile("(?im)^To:\\s*.*?;tag=([^;\\s>]+)");

        static RawResponse parse(String raw) {
            Matcher status = STATUS.matcher(raw);
            Matcher cseq = CSEQ.matcher(raw);
            Matcher to = TO.matcher(raw);
            if (!status.find() || !cseq.find()) {
                throw new IllegalArgumentException("unable to parse SIP response: " + raw);
            }
            int separator = raw.indexOf("\r\n\r\n");
            String body = separator < 0 ? "" : raw.substring(separator + 4);
            return new RawResponse(
                    Integer.parseInt(status.group(1)),
                    Long.parseLong(cseq.group(1)),
                    to.find() ? to.group(1) : "",
                    body);
        }
    }

    private static final class LiveUas implements SipListener, AutoCloseable {
        private final EvidenceRecorder evidence;
        private final String controlAnswer;
        private final CountDownLatch ack1 = new CountDownLatch(1);
        private final CountDownLatch ack2 = new CountDownLatch(1);
        private final CountDownLatch ack3 = new CountDownLatch(1);
        private final SipStack stack;
        private final SipProvider provider;
        private final AddressFactory addresses;
        private final HeaderFactory headers;
        private final MessageFactory messages;

        LiveUas(EvidenceRecorder evidence, String controlAnswer) throws Exception {
            this.evidence = evidence;
            this.controlAnswer = controlAnswer;
            SipFactory factory = SipFactory.getInstance();
            factory.setPathName("gov.nist");
            Properties properties = new Properties();
            properties.setProperty("javax.sip.STACK_NAME", "baudot-live-rtt-readiness");
            properties.setProperty("gov.nist.javax.sip.TRACE_LEVEL", "0");
            stack = factory.createSipStack(properties);
            addresses = factory.createAddressFactory();
            headers = factory.createHeaderFactory();
            messages = factory.createMessageFactory();
            ListeningPoint point = stack.createListeningPoint(HOST, UAS_PORT, ListeningPoint.UDP);
            provider = stack.createSipProvider(point);
            provider.addSipListener(this);
        }

        void start() throws Exception {
            stack.start();
            evidence.event("live.uas.ready", Map.of("bind", HOST + ":" + UAS_PORT));
        }

        boolean awaitAck(long cseq, Duration timeout) throws InterruptedException {
            CountDownLatch latch = cseq == 1 ? ack1 : cseq == 2 ? ack2 : ack3;
            return latch.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        @Override
        public void processRequest(RequestEvent event) {
            Request request = event.getRequest();
            CSeqHeader cseq = (CSeqHeader) request.getHeader(CSeqHeader.NAME);
            long sequence = cseq == null ? -1 : cseq.getSeqNumber();
            try {
                if (Request.ACK.equals(request.getMethod())) {
                    if (sequence == 1) ack1.countDown();
                    if (sequence == 2) ack2.countDown();
                    if (sequence == 3) ack3.countDown();
                    evidence.event("live.ack.received", Map.of("cseq", Long.toString(sequence)));
                    return;
                }
                if (!Request.INVITE.equals(request.getMethod())) {
                    return;
                }
                ServerTransaction transaction = event.getServerTransaction();
                if (transaction == null) {
                    transaction = provider.getNewServerTransaction(request);
                }
                Response ok = messages.createResponse(Response.OK, request);
                ToHeader to = (ToHeader) ok.getHeader(ToHeader.NAME);
                if (to.getTag() == null) {
                    to.setTag(TO_TAG);
                }
                addContact(ok);
                String answer = sequence == 1 ? sdp(42201, "answer-initial") : controlAnswer;
                ok.setContent(answer, headers.createContentTypeHeader("application", "sdp"));
                transaction.sendResponse(ok);
                evidence.event("live.invite.response.sent", Map.of(
                        "cseq", Long.toString(sequence),
                        "status", "200",
                        "answerTextPort", Integer.toString(textPort(answer)),
                        "answerMode", sequence == 3 ? "deliberate-stale-reuse" : "fresh"));
            } catch (Exception error) {
                evidence.event("live.uas.error", Map.of(
                        "cseq", Long.toString(sequence),
                        "error", error.toString()));
            }
        }

        private void addContact(Response response) throws Exception {
            SipURI uri = addresses.createSipURI("callee", HOST);
            uri.setPort(UAS_PORT);
            uri.setTransportParam(ListeningPoint.UDP);
            Address address = addresses.createAddress(uri);
            ContactHeader contact = headers.createContactHeader(address);
            response.addHeader(contact);
        }

        @Override public void processResponse(ResponseEvent event) { }
        @Override public void processTimeout(TimeoutEvent event) { }
        @Override public void processIOException(IOExceptionEvent event) { }
        @Override public void processTransactionTerminated(TransactionTerminatedEvent event) { }
        @Override public void processDialogTerminated(DialogTerminatedEvent event) { }

        @Override
        public void close() {
            try {
                stack.stop();
            } catch (Exception ignored) {
                // The process boundary is additionally guarded by the runner timeout.
            }
        }
    }
}
