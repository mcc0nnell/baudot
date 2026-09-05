package org.mcc0nnell.baudot.harness;

import java.io.IOException;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
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
 * Minimal interoperability probe. It deliberately records signaling and a UDP
 * media-path heartbeat as separate observations. The heartbeat is not RTP and
 * is not a media-conformance claim; it exists to prove independent reachability.
 */
public final class BaudotProbe {
    private BaudotProbe() {
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
                    "correlation", config.correlationId()));

            endpoint.start();
            endpoint.sendInvite();
            boolean established = endpoint.awaitDialog(config.timeout());
            boolean sent = false;
            if (established) {
                sent = sendMediaProbe(config, evidence);
            }

            evidence.result(Map.of(
                    "correlation.id", config.correlationId(),
                    "media.probe.sent", Boolean.toString(sent),
                    "role", "caller",
                    "scenario.expectMedia", Boolean.toString(config.expectMedia()),
                    "scenario.id", config.scenarioId(),
                    "signaling.dialog.established", Boolean.toString(established)));

            return established && sent ? 0 : 2;
        }
    }

    private static int runCallee(Config config) throws Exception {
        try (EvidenceRecorder evidence = new EvidenceRecorder(
                config.evidenceRoot(), config.scenarioId(), config.correlationId(), "callee");
             MediaReceiver media = new MediaReceiver(config, evidence);
             SipEndpoint endpoint = SipEndpoint.callee(config, evidence)) {

            evidence.event("scenario.started", Map.of(
                    "role", "callee",
                    "scenario", config.scenarioId(),
                    "correlation", config.correlationId()));

            media.start();
            endpoint.start();

            boolean dialogEstablished = endpoint.awaitDialog(config.timeout());
            boolean mediaReceived = media.await(config.timeout());

            evidence.result(Map.of(
                    "correlation.id", config.correlationId(),
                    "media.probe.received", Boolean.toString(mediaReceived),
                    "role", "callee",
                    "scenario.expectMedia", Boolean.toString(config.expectMedia()),
                    "scenario.id", config.scenarioId(),
                    "signaling.ack.received", Boolean.toString(endpoint.ackReceived()),
                    "signaling.invite.received", Boolean.toString(endpoint.inviteReceived())));

            boolean expectationMatched = mediaReceived == config.expectMedia();
            return dialogEstablished && expectationMatched ? 0 : 3;
        }
    }

    private static boolean sendMediaProbe(Config config, EvidenceRecorder evidence) {
        byte[] payload = ("BAUDOT1|" + config.correlationId()).getBytes(StandardCharsets.UTF_8);
        try (DatagramSocket socket = new DatagramSocket()) {
            DatagramPacket packet = new DatagramPacket(
                    payload,
                    payload.length,
                    InetAddress.getByName(config.mediaTargetIp()),
                    config.mediaTargetPort());
            socket.send(packet);
            evidence.event("media.probe.sent", Map.of(
                    "target", config.mediaTargetIp() + ":" + config.mediaTargetPort(),
                    "bytes", Integer.toString(payload.length)));
            return true;
        } catch (IOException e) {
            evidence.event("media.probe.send_failed", Map.of("error", e.toString()));
            return false;
        }
    }

    enum Role {
        CALLER,
        CALLEE
    }

    record Config(
            Role role,
            String scenarioId,
            String correlationId,
            String callerSipIp,
            int callerSipPort,
            String calleeSipBindIp,
            String calleeSipIp,
            int calleeSipPort,
            String mediaBindIp,
            int mediaBindPort,
            String mediaTargetIp,
            int mediaTargetPort,
            boolean expectMedia,
            Duration timeout,
            Path evidenceRoot) {

        static Config fromEnvironment() {
            String roleValue = env("BAUDOT_ROLE", "caller").trim().toUpperCase();
            Role role = Role.valueOf(roleValue);
            String scenario = env("BAUDOT_SCENARIO", "001-signaling-media");
            String correlation = env("BAUDOT_CORRELATION", UUID.randomUUID().toString());
            String callerIp = env("BAUDOT_CALLER_SIP_IP", "127.0.0.1");
            String calleeIp = env("BAUDOT_CALLEE_SIP_IP", "127.0.0.1");
            String mediaBindIp = env("BAUDOT_MEDIA_BIND_IP", calleeIp);
            return new Config(
                    role,
                    scenario,
                    correlation,
                    callerIp,
                    envInt("BAUDOT_CALLER_SIP_PORT", 5070),
                    env("BAUDOT_CALLEE_SIP_BIND_IP", calleeIp),
                    calleeIp,
                    envInt("BAUDOT_CALLEE_SIP_PORT", 5080),
                    mediaBindIp,
                    envInt("BAUDOT_MEDIA_BIND_PORT", 40000),
                    env("BAUDOT_MEDIA_TARGET_IP", mediaBindIp),
                    envInt("BAUDOT_MEDIA_TARGET_PORT", 40000),
                    Boolean.parseBoolean(env("BAUDOT_EXPECT_MEDIA", "true")),
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

    private static final class MediaReceiver implements AutoCloseable {
        private final Config config;
        private final EvidenceRecorder evidence;
        private final CountDownLatch received = new CountDownLatch(1);
        private final AtomicBoolean running = new AtomicBoolean();
        private DatagramSocket socket;
        private Thread thread;

        private MediaReceiver(Config config, EvidenceRecorder evidence) {
            this.config = config;
            this.evidence = evidence;
        }

        void start() throws IOException {
            socket = new DatagramSocket(new InetSocketAddress(
                    InetAddress.getByName(config.mediaBindIp()), config.mediaBindPort()));
            socket.setSoTimeout(500);
            running.set(true);
            thread = new Thread(this::receiveLoop, "baudot-media-probe");
            thread.setDaemon(true);
            thread.start();
            evidence.event("media.receiver.ready", Map.of(
                    "bind", config.mediaBindIp() + ":" + config.mediaBindPort()));
        }

        private void receiveLoop() {
            byte[] buffer = new byte[2048];
            while (running.get()) {
                DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                try {
                    socket.receive(packet);
                    String payload = new String(packet.getData(), packet.getOffset(), packet.getLength(), StandardCharsets.UTF_8);
                    if (("BAUDOT1|" + config.correlationId()).equals(payload)) {
                        evidence.event("media.probe.received", Map.of(
                                "source", packet.getAddress().getHostAddress() + ":" + packet.getPort(),
                                "bytes", Integer.toString(packet.getLength())));
                        received.countDown();
                        return;
                    }
                    evidence.event("media.probe.ignored", Map.of("reason", "correlation_mismatch"));
                } catch (SocketTimeoutException ignored) {
                    // Check running flag again.
                } catch (IOException e) {
                    if (running.get()) {
                        evidence.event("media.receiver.error", Map.of("error", e.toString()));
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
                    "baudot-" + (caller ? "caller-" : "callee-") + config.correlationId().replace("-", ""));
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
            invite.setContent(sdp(config.callerSipIp(), 9, "inactive"), contentType);

            inviteTransaction = provider.getNewClientTransaction(invite);
            evidence.event("sip.invite.sent", Map.of(
                    "target", config.calleeSipIp() + ":" + config.calleeSipPort(),
                    "callId", callId.getCallId(),
                    "rport", "requested"));
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
                        "callId", callId == null ? "unknown" : callId.getCallId()));

                Response ok = messageFactory.createResponse(Response.OK, request);
                ToHeader to = (ToHeader) ok.getHeader(ToHeader.NAME);
                if (to.getTag() == null) {
                    to.setTag(randomTag());
                }
                Address contactAddress = addressFactory.createAddress(
                        sipUri("callee", config.calleeSipIp(), config.calleeSipPort()));
                ContactHeader contact = headerFactory.createContactHeader(contactAddress);
                ok.addHeader(contact);
                ok.setContent(
                        sdp(config.mediaTargetIp(), config.mediaTargetPort(), "recvonly"),
                        headerFactory.createContentTypeHeader("application", "sdp"));
                transaction.sendResponse(ok);
                evidence.event("sip.200.sent", Map.of("status", "200"));
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
                        "status", Integer.toString(response.getStatusCode())));
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

        private static String sdp(String ip, int port, String direction) {
            return "v=0\r\n"
                    + "o=baudot 0 0 IN IP4 " + ip + "\r\n"
                    + "s=Baudot probe\r\n"
                    + "c=IN IP4 " + ip + "\r\n"
                    + "t=0 0\r\n"
                    + "m=audio " + port + " RTP/AVP 0\r\n"
                    + "a=" + direction + "\r\n";
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
}
