package org.mcc0nnell.baudot.harness;

import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketTimeoutException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import javax.sip.ClientTransaction;
import javax.sip.Dialog;
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
import javax.sip.header.CallIdHeader;
import javax.sip.header.ContactHeader;
import javax.sip.header.ContentTypeHeader;
import javax.sip.header.FromHeader;
import javax.sip.header.HeaderFactory;
import javax.sip.header.MaxForwardsHeader;
import javax.sip.header.ToHeader;
import javax.sip.header.ViaHeader;
import javax.sip.message.MessageFactory;
import javax.sip.message.Request;
import javax.sip.message.Response;

/**
 * Routed RTT interoperability probe.
 *
 * <p>JAIN SIP owns only the SIP dialog and carriage of the SDP offer/answer.
 * Java sends and records opaque UDP datagrams. The datagrams are deliberately
 * not classified as valid RTP/RED/T.140 here; the Baudot Python reference
 * parser independently performs that validation after the routed run.</p>
 */
public final class RttSipProbe {
    static final int T140_PAYLOAD_TYPE = 98;
    static final int RED_PAYLOAD_TYPE = 99;
    static final int T140_CLOCK_RATE = 1000;
    static final int RED_TIMESTAMP_OFFSET = 300;
    static final int NORMAL_PRIMARY_SEQUENCE = 1;
    static final int NORMAL_RED_SEQUENCE = 2;
    static final int NORMAL_PRIMARY_TIMESTAMP = 1000;
    static final int NORMAL_RED_TIMESTAMP = 1300;
    static final int RECOVERY_PRIOR_SEQUENCE = 0;
    static final int RECOVERY_OMITTED_SEQUENCE = 1;
    static final int RECOVERY_RED_SEQUENCE = 2;
    static final int RECOVERY_PRIOR_TIMESTAMP = 700;
    static final int RECOVERY_OMITTED_TIMESTAMP = 1000;
    static final int RECOVERY_RED_TIMESTAMP = 1300;
    static final int SSRC = 0x42415544; // "BAUD"; deterministic test evidence only.

    private RttSipProbe() {
    }

    public static void main(String[] args) throws Exception {
        Config config = Config.fromEnvironment();
        int exit = switch (config.role()) {
            case CALLER -> runCaller(config);
            case CALLEE -> runCallee(config);
        };
        System.exit(exit);
    }

    private static int runCaller(Config config) throws Exception {
        try (EvidenceRecorder evidence = new EvidenceRecorder(
                config.evidenceRoot(), config.scenarioId(), config.correlationId(), "caller");
             SipEndpoint endpoint = SipEndpoint.caller(config, evidence)) {

            evidence.event("scenario.started", Map.of(
                    "role", "caller",
                    "scenario", config.scenarioId(),
                    "correlation", config.correlationId(),
                    "modality", "rtt",
                    "profile", config.profile().wireName()));

            endpoint.start();
            endpoint.sendInvite();
            boolean established = endpoint.awaitDialog(config.timeout());
            boolean sent = false;
            if (established) {
                sent = sendRttDatagrams(config, evidence);
            }

            evidence.result(Map.of(
                    "correlation.id", config.correlationId(),
                    "media.probe.sent", Boolean.toString(sent),
                    "role", "caller",
                    "rtt.datagrams.expected", "2",
                    "rtt.profile", config.profile().wireName(),
                    "scenario.expectMedia", "true",
                    "scenario.id", config.scenarioId(),
                    "signaling.dialog.established", Boolean.toString(established)));

            return established && sent ? 0 : 2;
        }
    }

    private static int runCallee(Config config) throws Exception {
        try (EvidenceRecorder evidence = new EvidenceRecorder(
                config.evidenceRoot(), config.scenarioId(), config.correlationId(), "callee");
             RttReceiver receiver = new RttReceiver(config, evidence);
             SipEndpoint endpoint = SipEndpoint.callee(config, evidence)) {

            evidence.event("scenario.started", Map.of(
                    "role", "callee",
                    "scenario", config.scenarioId(),
                    "correlation", config.correlationId(),
                    "modality", "rtt",
                    "profile", config.profile().wireName()));

            receiver.start();
            endpoint.start();

            boolean dialogEstablished = endpoint.awaitDialog(config.timeout());
            boolean datagramsReceived = receiver.await(config.timeout());

            evidence.result(Map.of(
                    "correlation.id", config.correlationId(),
                    "media.probe.received", Boolean.toString(datagramsReceived),
                    "role", "callee",
                    "rtt.datagrams.expected", "2",
                    "rtt.profile", config.profile().wireName(),
                    "scenario.expectMedia", "true",
                    "scenario.id", config.scenarioId(),
                    "signaling.ack.received", Boolean.toString(endpoint.ackReceived()),
                    "signaling.invite.received", Boolean.toString(endpoint.inviteReceived())));

            return dialogEstablished && datagramsReceived ? 0 : 3;
        }
    }

    private static boolean sendRttDatagrams(Config config, EvidenceRecorder evidence) {
        byte[][] datagrams = switch (config.profile()) {
            case NORMAL -> new byte[][] {normalPrimaryPacket(), normalRedPacket()};
            case RECOVERY -> new byte[][] {recoveryPriorPacket(), recoveryRedPacket()};
        };

        try {
            if (config.profile() == Profile.RECOVERY) {
                String plan = "{\n"
                        + "  \"injection\": \"controlled-source-omission\",\n"
                        + "  \"emittedSequenceNumbers\": [0, 2],\n"
                        + "  \"omittedSequenceNumbers\": [1],\n"
                        + "  \"omittedTimestamp\": 1000,\n"
                        + "  \"omittedT140Text\": \"B\",\n"
                        + "  \"recoveryCarrierSequence\": 2,\n"
                        + "  \"redundantTimestampOffset\": 300\n"
                        + "}\n";
                evidence.writeBytes("rtt-loss-plan.json", plan.getBytes(StandardCharsets.UTF_8));
                evidence.event("rtt.loss.injected", Map.of(
                        "injection", "controlled-source-omission",
                        "emitted", "0,2",
                        "omitted", "1",
                        "classification", "sender-controlled"));
            }

            try (DatagramSocket socket = new DatagramSocket(new InetSocketAddress(
                    InetAddress.getByName(config.callerSipIp()), config.mediaSourcePort()))) {
                for (int index = 0; index < datagrams.length; index++) {
                    byte[] content = datagrams[index];
                    evidence.writeBytes("rtt-datagram-" + (index + 1) + "-sent.bin", content);
                    DatagramPacket packet = new DatagramPacket(
                            content,
                            content.length,
                            InetAddress.getByName(config.mediaTargetIp()),
                            config.mediaTargetPort());
                    socket.send(packet);
                    evidence.event("rtt.datagram.sent", Map.of(
                            "index", Integer.toString(index + 1),
                            "target", config.mediaTargetIp() + ":" + config.mediaTargetPort(),
                            "bytes", Integer.toString(content.length),
                            "classification", "unvalidated",
                            "profile", config.profile().wireName()));
                    if (index + 1 < datagrams.length) {
                        Thread.sleep(50L);
                    }
                }
            }
            return true;
        } catch (Exception e) {
            evidence.event("rtt.datagram.send_failed", Map.of("error", e.toString()));
            return false;
        }
    }

    static byte[] normalPrimaryPacket() {
        return directPacket(NORMAL_PRIMARY_SEQUENCE, NORMAL_PRIMARY_TIMESTAMP, true, 'H');
    }

    static byte[] normalRedPacket() {
        return redPacket(NORMAL_RED_SEQUENCE, NORMAL_RED_TIMESTAMP, 'H', 'i');
    }

    static byte[] recoveryPriorPacket() {
        return directPacket(RECOVERY_PRIOR_SEQUENCE, RECOVERY_PRIOR_TIMESTAMP, true, 'A');
    }

    static byte[] recoveryRedPacket() {
        return redPacket(RECOVERY_RED_SEQUENCE, RECOVERY_RED_TIMESTAMP, 'B', 'C');
    }

    private static byte[] directPacket(int sequence, int timestamp, boolean marker, char text) {
        ByteBuffer packet = ByteBuffer.allocate(13).order(ByteOrder.BIG_ENDIAN);
        packet.put((byte) 0x80);
        packet.put((byte) ((marker ? 0x80 : 0x00) | T140_PAYLOAD_TYPE));
        packet.putShort((short) sequence);
        packet.putInt(timestamp);
        packet.putInt(SSRC);
        packet.put((byte) text);
        return packet.array();
    }

    private static byte[] redPacket(int sequence, int timestamp, char redundantText, char primaryText) {
        ByteBuffer packet = ByteBuffer.allocate(19).order(ByteOrder.BIG_ENDIAN);
        packet.put((byte) 0x80);
        packet.put((byte) RED_PAYLOAD_TYPE);
        packet.putShort((short) sequence);
        packet.putInt(timestamp);
        packet.putInt(SSRC);
        packet.put((byte) (0x80 | T140_PAYLOAD_TYPE));
        int packed = (RED_TIMESTAMP_OFFSET << 10) | 1;
        packet.put((byte) ((packed >>> 16) & 0xff));
        packet.put((byte) ((packed >>> 8) & 0xff));
        packet.put((byte) (packed & 0xff));
        packet.put((byte) T140_PAYLOAD_TYPE);
        packet.put((byte) redundantText);
        packet.put((byte) primaryText);
        return packet.array();
    }

    enum Role {
        CALLER,
        CALLEE
    }

    enum Profile {
        NORMAL("normal"),
        RECOVERY("recovery");

        private final String wireName;

        Profile(String wireName) {
            this.wireName = wireName;
        }

        String wireName() {
            return wireName;
        }

        static Profile fromEnvironment(String value) {
            return switch (value.trim().toLowerCase()) {
                case "normal" -> NORMAL;
                case "recovery" -> RECOVERY;
                default -> throw new IllegalArgumentException("Unsupported BAUDOT_RTT_PROFILE: " + value);
            };
        }
    }

    record Config(
            Role role,
            Profile profile,
            String scenarioId,
            String correlationId,
            String callerSipIp,
            int callerSipPort,
            String calleeSipBindIp,
            String calleeSipIp,
            int calleeSipPort,
            int mediaSourcePort,
            String mediaBindIp,
            int mediaBindPort,
            String mediaTargetIp,
            int mediaTargetPort,
            Duration timeout,
            Path evidenceRoot) {

        static Config fromEnvironment() {
            String roleValue = env("BAUDOT_ROLE", "caller").trim().toUpperCase();
            Role role = Role.valueOf(roleValue);
            Profile profile = Profile.fromEnvironment(env("BAUDOT_RTT_PROFILE", "normal"));
            String scenario = env("BAUDOT_SCENARIO", "003-rtt-rfc4103");
            String correlation = env("BAUDOT_CORRELATION", UUID.randomUUID().toString());
            String callerIp = env("BAUDOT_CALLER_SIP_IP", "127.0.0.1");
            String calleeIp = env("BAUDOT_CALLEE_SIP_IP", "127.0.0.1");
            String mediaBindIp = env("BAUDOT_MEDIA_BIND_IP", calleeIp);
            return new Config(
                    role,
                    profile,
                    scenario,
                    correlation,
                    callerIp,
                    envInt("BAUDOT_CALLER_SIP_PORT", 5070),
                    env("BAUDOT_CALLEE_SIP_BIND_IP", calleeIp),
                    calleeIp,
                    envInt("BAUDOT_CALLEE_SIP_PORT", 5080),
                    envInt("BAUDOT_MEDIA_SOURCE_PORT", 40001),
                    mediaBindIp,
                    envInt("BAUDOT_MEDIA_BIND_PORT", 40000),
                    env("BAUDOT_MEDIA_TARGET_IP", mediaBindIp),
                    envInt("BAUDOT_MEDIA_TARGET_PORT", 40000),
                    Duration.ofMillis(envInt("BAUDOT_TIMEOUT_MS", 5000)),
                    Path.of(env("BAUDOT_EVIDENCE_DIR", "target/evidence")));
        }

        private static String env(String name, String fallback) {
            String value = System.getenv(name);
            return value == null || value.isBlank() ? fallback : value;
        }

        private static int envInt(String name, int fallback) {
            return Integer.parseInt(env(name, Integer.toString(fallback)));
        }
    }

    private static final class RttReceiver implements AutoCloseable {
        private final Config config;
        private final EvidenceRecorder evidence;
        private final CountDownLatch received = new CountDownLatch(2);
        private final AtomicBoolean running = new AtomicBoolean();
        private DatagramSocket socket;
        private Thread thread;

        private RttReceiver(Config config, EvidenceRecorder evidence) {
            this.config = config;
            this.evidence = evidence;
        }

        void start() throws IOException {
            socket = new DatagramSocket(new InetSocketAddress(
                    InetAddress.getByName(config.mediaBindIp()), config.mediaBindPort()));
            socket.setSoTimeout(500);
            running.set(true);
            thread = new Thread(this::receiveLoop, "baudot-rtt-datagram-receiver");
            thread.setDaemon(true);
            thread.start();
            evidence.event("rtt.receiver.ready", Map.of(
                    "bind", config.mediaBindIp() + ":" + config.mediaBindPort(),
                    "classification", "opaque-udp",
                    "profile", config.profile().wireName()));
        }

        private void receiveLoop() {
            byte[] buffer = new byte[2048];
            int index = 0;
            while (running.get() && index < 2) {
                DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                try {
                    socket.receive(packet);
                    index++;
                    byte[] content = Arrays.copyOfRange(
                            packet.getData(), packet.getOffset(), packet.getOffset() + packet.getLength());
                    evidence.writeBytes("rtt-datagram-" + index + "-received.bin", content);
                    evidence.event("rtt.datagram.received", Map.of(
                            "index", Integer.toString(index),
                            "source", packet.getAddress().getHostAddress() + ":" + packet.getPort(),
                            "bytes", Integer.toString(packet.getLength()),
                            "classification", "unvalidated",
                            "profile", config.profile().wireName()));
                    received.countDown();
                } catch (SocketTimeoutException ignored) {
                    // Check running flag again.
                } catch (IOException e) {
                    if (running.get()) {
                        evidence.event("rtt.receiver.error", Map.of("error", e.toString()));
                    }
                    return;
                }
            }
        }

        boolean await(Duration timeout) throws InterruptedException {
            return received.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        @Override
        public void close() {
            running.set(false);
            if (socket != null) {
                socket.close();
            }
            if (thread != null) {
                try {
                    thread.join(1000);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }
    }

    private static final class SipEndpoint implements SipListener, AutoCloseable {
        private final Config config;
        private final EvidenceRecorder evidence;
        private final boolean caller;
        private final CountDownLatch dialog = new CountDownLatch(1);
        private final AtomicBoolean inviteReceived = new AtomicBoolean();
        private final AtomicBoolean ackReceived = new AtomicBoolean();
        private final SipStack stack;
        private final SipProvider provider;
        private final AddressFactory addressFactory;
        private final HeaderFactory headerFactory;
        private final MessageFactory messageFactory;
        private ClientTransaction inviteTransaction;

        private SipEndpoint(Config config, EvidenceRecorder evidence, boolean caller) throws Exception {
            this.config = config;
            this.evidence = evidence;
            this.caller = caller;
            SipFactory factory = SipFactory.getInstance();
            factory.setPathName("gov.nist");
            Properties properties = new Properties();
            properties.setProperty("javax.sip.STACK_NAME",
                    "baudot-rtt-" + (caller ? "caller-" : "callee-")
                            + config.correlationId().replace("-", ""));
            properties.setProperty("gov.nist.javax.sip.TRACE_LEVEL", "0");
            this.stack = factory.createSipStack(properties);
            this.addressFactory = factory.createAddressFactory();
            this.headerFactory = factory.createHeaderFactory();
            this.messageFactory = factory.createMessageFactory();
            String bindIp = caller ? config.callerSipIp() : config.calleeSipBindIp();
            int port = caller ? config.callerSipPort() : config.calleeSipPort();
            ListeningPoint point = stack.createListeningPoint(bindIp, port, ListeningPoint.UDP);
            this.provider = stack.createSipProvider(point);
            this.provider.addSipListener(this);
        }

        static SipEndpoint caller(Config config, EvidenceRecorder evidence) throws Exception {
            return new SipEndpoint(config, evidence, true);
        }

        static SipEndpoint callee(Config config, EvidenceRecorder evidence) throws Exception {
            return new SipEndpoint(config, evidence, false);
        }

        void start() throws Exception {
            stack.start();
            evidence.event("sip.endpoint.ready", Map.of(
                    "role", caller ? "caller" : "callee",
                    "transport", "udp"));
        }

        void sendInvite() throws Exception {
            if (!caller) {
                throw new IllegalStateException("Only the caller can send INVITE");
            }
            SipURI requestUri = addressFactory.createSipURI("callee", config.calleeSipIp());
            requestUri.setPort(config.calleeSipPort());
            requestUri.setTransportParam(ListeningPoint.UDP);
            Address fromAddress = addressFactory.createAddress(
                    sipUri("caller", config.callerSipIp(), config.callerSipPort()));
            FromHeader from = headerFactory.createFromHeader(fromAddress, randomTag());
            Address toAddress = addressFactory.createAddress(
                    sipUri("callee", config.calleeSipIp(), config.calleeSipPort()));
            ToHeader to = headerFactory.createToHeader(toAddress, null);
            List<ViaHeader> vias = new ArrayList<>();
            ViaHeader via = headerFactory.createViaHeader(
                    config.callerSipIp(), config.callerSipPort(), ListeningPoint.UDP, null);
            via.setRPort();
            vias.add(via);
            CallIdHeader callId = provider.getNewCallId();
            CSeqHeader cseq = headerFactory.createCSeqHeader(1L, Request.INVITE);
            MaxForwardsHeader maxForwards = headerFactory.createMaxForwardsHeader(70);
            Request invite = messageFactory.createRequest(
                    requestUri, Request.INVITE, callId, cseq, from, to, vias, maxForwards);
            invite.addHeader(headerFactory.createContactHeader(fromAddress));
            ContentTypeHeader contentType = headerFactory.createContentTypeHeader("application", "sdp");
            invite.setContent(offerSdp(config), contentType);
            inviteTransaction = provider.getNewClientTransaction(invite);
            evidence.event("sip.invite.sent", Map.of(
                    "target", config.calleeSipIp() + ":" + config.calleeSipPort(),
                    "callId", callId.getCallId(),
                    "rport", "requested",
                    "modality", "rtt"));
            inviteTransaction.sendRequest();
        }

        boolean awaitDialog(Duration timeout) throws InterruptedException {
            return dialog.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        boolean inviteReceived() {
            return inviteReceived.get();
        }

        boolean ackReceived() {
            return ackReceived.get();
        }

        @Override
        public void processRequest(RequestEvent event) {
            if (caller) {
                return;
            }
            Request request = event.getRequest();
            if (Request.ACK.equals(request.getMethod())) {
                ackReceived.set(true);
                dialog.countDown();
                evidence.event("sip.ack.received", Map.of());
                return;
            }
            if (!Request.INVITE.equals(request.getMethod())) {
                return;
            }
            try {
                inviteReceived.set(true);
                ServerTransaction transaction = event.getServerTransaction();
                if (transaction == null) {
                    transaction = provider.getNewServerTransaction(request);
                }
                CallIdHeader callId = (CallIdHeader) request.getHeader(CallIdHeader.NAME);
                evidence.event("sip.invite.received", Map.of(
                        "callId", callId == null ? "unknown" : callId.getCallId(),
                        "modality", "rtt"));
                byte[] rawOffer = request.getRawContent();
                if (rawOffer == null || rawOffer.length == 0) {
                    throw new IllegalStateException("RTT INVITE did not contain SDP");
                }
                evidence.writeBytes("offer.sdp", rawOffer);
                evidence.event("sdp.offer.captured", Map.of(
                        "bytes", Integer.toString(rawOffer.length),
                        "classification", "unvalidated"));
                Response ok = messageFactory.createResponse(Response.OK, request);
                ToHeader to = (ToHeader) ok.getHeader(ToHeader.NAME);
                if (to.getTag() == null) {
                    to.setTag(randomTag());
                }
                Address contactAddress = addressFactory.createAddress(
                        sipUri("callee", config.calleeSipIp(), config.calleeSipPort()));
                ContactHeader contact = headerFactory.createContactHeader(contactAddress);
                ok.addHeader(contact);
                ok.setContent(answerSdp(config),
                        headerFactory.createContentTypeHeader("application", "sdp"));
                transaction.sendResponse(ok);
                evidence.event("sip.200.sent", Map.of("status", "200", "modality", "rtt"));
            } catch (Exception e) {
                evidence.event("sip.request.error", Map.of("error", e.toString()));
            }
        }

        @Override
        public void processResponse(ResponseEvent event) {
            if (!caller) {
                return;
            }
            Response response = event.getResponse();
            CSeqHeader cseq = (CSeqHeader) response.getHeader(CSeqHeader.NAME);
            if (response.getStatusCode() != Response.OK || cseq == null || !Request.INVITE.equals(cseq.getMethod())) {
                return;
            }
            try {
                byte[] rawAnswer = response.getRawContent();
                if (rawAnswer == null || rawAnswer.length == 0) {
                    throw new IllegalStateException("RTT 200 OK did not contain SDP");
                }
                evidence.writeBytes("answer.sdp", rawAnswer);
                evidence.event("sdp.answer.captured", Map.of(
                        "bytes", Integer.toString(rawAnswer.length),
                        "classification", "unvalidated"));
                Dialog sipDialog = event.getDialog();
                if (sipDialog == null && inviteTransaction != null) {
                    sipDialog = inviteTransaction.getDialog();
                }
                if (sipDialog == null) {
                    throw new IllegalStateException("200 OK arrived without a SIP dialog");
                }
                Request ack = sipDialog.createAck(cseq.getSeqNumber());
                sipDialog.sendAck(ack);
                dialog.countDown();
                evidence.event("sip.dialog.established", Map.of(
                        "status", Integer.toString(response.getStatusCode()),
                        "modality", "rtt"));
            } catch (Exception e) {
                evidence.event("sip.response.error", Map.of("error", e.toString()));
            }
        }

        @Override
        public void processTimeout(TimeoutEvent event) {
            evidence.event("sip.timeout", Map.of("server", Boolean.toString(event.isServerTransaction())));
        }

        @Override
        public void processIOException(IOExceptionEvent event) {
            evidence.event("sip.io_error", Map.of(
                    "host", String.valueOf(event.getHost()),
                    "port", Integer.toString(event.getPort()),
                    "transport", String.valueOf(event.getTransport())));
        }

        @Override
        public void processTransactionTerminated(TransactionTerminatedEvent event) {
            evidence.event("sip.transaction.terminated", Map.of(
                    "server", Boolean.toString(event.isServerTransaction())));
        }

        @Override
        public void processDialogTerminated(DialogTerminatedEvent event) {
            evidence.event("sip.dialog.terminated", Map.of(
                    "dialog", String.valueOf(event.getDialog().getDialogId())));
        }

        private String sipUri(String user, String host, int port) throws Exception {
            SipURI uri = addressFactory.createSipURI(user, host);
            uri.setPort(port);
            uri.setTransportParam(ListeningPoint.UDP);
            return uri.toString();
        }

        private static String randomTag() {
            return UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        }

        @Override
        public void close() {
            try {
                stack.stop();
            } catch (Exception e) {
                evidence.event("sip.stop.error", Map.of("error", e.toString()));
            }
        }
    }

    static String offerSdp(Config config) {
        return rttSdp(config.callerSipIp(), config.mediaSourcePort(), "sendonly");
    }

    static String answerSdp(Config config) {
        return rttSdp(config.mediaTargetIp(), config.mediaTargetPort(), "recvonly");
    }

    private static String rttSdp(String ip, int port, String direction) {
        return "v=0\r\n"
                + "o=baudot 0 0 IN IP4 " + ip + "\r\n"
                + "s=Baudot RTT probe\r\n"
                + "c=IN IP4 " + ip + "\r\n"
                + "t=0 0\r\n"
                + "m=text " + port + " RTP/AVP " + RED_PAYLOAD_TYPE + " " + T140_PAYLOAD_TYPE + "\r\n"
                + "a=rtpmap:" + RED_PAYLOAD_TYPE + " red/" + T140_CLOCK_RATE + "\r\n"
                + "a=fmtp:" + RED_PAYLOAD_TYPE + " " + T140_PAYLOAD_TYPE + "/" + T140_PAYLOAD_TYPE
                + "/" + T140_PAYLOAD_TYPE + "\r\n"
                + "a=rtpmap:" + T140_PAYLOAD_TYPE + " t140/" + T140_CLOCK_RATE + "\r\n"
                + "a=" + direction + "\r\n";
    }
}
