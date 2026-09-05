package org.mcc0nnell.baudot.harness;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Arrays;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

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
import javax.sip.header.ContactHeader;
import javax.sip.header.ContentTypeHeader;
import javax.sip.header.ToHeader;
import javax.sip.message.MessageFactory;
import javax.sip.message.Request;
import javax.sip.message.Response;

/**
 * Receives a PJSIP/PJMEDIA native RFC 2198 text call and preserves datagrams.
 *
 * <p>JAIN SIP owns only the controlled SIP UAS and SDP selection. Java never
 * parses RED or T.140 payloads. The independent Python reference reducer owns
 * the RFC 2198/T.140 and loss-recovery verdict.</p>
 */
public final class PjsipNativeRedReceiverProbe implements SipListener, AutoCloseable {
    private static final String HOST = "127.0.0.1";
    private static final String SCENARIO = "PJSIP-NATIVE-RFC2198";
    private static final Duration TIMEOUT = Duration.ofSeconds(12);

    private final int sipPort;
    private final int mediaPort;
    private final EvidenceRecorder evidence;
    private final SipStack stack;
    private final SipProvider provider;
    private final AddressFactory addresses;
    private final MessageFactory messages;
    private final CountDownLatch ack = new CountDownLatch(1);
    private final AtomicBoolean inviteObserved = new AtomicBoolean();
    private final AtomicBoolean textOffered = new AtomicBoolean();
    private final AtomicBoolean t140Offered = new AtomicBoolean();
    private final AtomicBoolean redOffered = new AtomicBoolean();
    private final AtomicBoolean redFmtpOffered = new AtomicBoolean();
    private final AtomicBoolean ackObserved = new AtomicBoolean();
    private final AtomicInteger requestOrdinal = new AtomicInteger();

    private PjsipNativeRedReceiverProbe(int sipPort, int mediaPort, EvidenceRecorder evidence)
            throws Exception {
        this.sipPort = sipPort;
        this.mediaPort = mediaPort;
        this.evidence = evidence;

        SipFactory factory = SipFactory.getInstance();
        factory.setPathName("gov.nist");
        Properties properties = new Properties();
        properties.setProperty("javax.sip.STACK_NAME", "baudot-pjsip-native-rfc2198-receiver");
        properties.setProperty("gov.nist.javax.sip.TRACE_LEVEL", "0");
        this.stack = factory.createSipStack(properties);
        this.addresses = factory.createAddressFactory();
        this.messages = factory.createMessageFactory();
        ListeningPoint point = stack.createListeningPoint(HOST, sipPort, ListeningPoint.UDP);
        this.provider = stack.createSipProvider(point);
        this.provider.addSipListener(this);
    }

    public static void main(String[] args) throws Exception {
        int sipPort = envInt("BAUDOT_PJSIP_REMOTE_PORT", 5310);
        int mediaPort = envInt("BAUDOT_PJSIP_MEDIA_PORT", 5312);
        String correlation = env("BAUDOT_PJSIP_RFC2198_CORRELATION", "pjsip-native-red-v1");
        String profile = env("BAUDOT_PJSIP_PROFILE_LABEL", "unknown");
        Path root = Path.of(env("BAUDOT_EVIDENCE_ROOT", "target/evidence-external"));

        try (EvidenceRecorder evidence = new EvidenceRecorder(root, SCENARIO, correlation, "jain-red-receiver");
             MediaReceiver media = new MediaReceiver(mediaPort, evidence);
             PjsipNativeRedReceiverProbe receiver =
                     new PjsipNativeRedReceiverProbe(sipPort, mediaPort, evidence)) {

            media.start();
            receiver.start();
            evidence.event("pjsip.native_red.receiver_ready", Map.of(
                    "sipBind", HOST + ":" + sipPort,
                    "mediaBind", HOST + ":" + mediaPort,
                    "profile", profile,
                    "semanticAuthority", "python-reference"));

            boolean packetsObserved = media.awaitMinimum(TIMEOUT);
            boolean ackObserved = receiver.ack.await(TIMEOUT.toMillis(), TimeUnit.MILLISECONDS);
            if (packetsObserved) {
                Thread.sleep(1000L);
            }

            boolean pass = receiver.inviteObserved.get()
                    && receiver.textOffered.get()
                    && receiver.t140Offered.get()
                    && receiver.redOffered.get()
                    && receiver.redFmtpOffered.get()
                    && ackObserved
                    && packetsObserved;

            evidence.result(Map.ofEntries(
                    Map.entry("correlation.id", correlation),
                    Map.entry("implementation", "pjsip/pjproject"),
                    Map.entry("implementation.profile", profile),
                    Map.entry("scenario.id", SCENARIO),
                    Map.entry("sip.invite.observed", Boolean.toString(receiver.inviteObserved.get())),
                    Map.entry("sip.text.offered", Boolean.toString(receiver.textOffered.get())),
                    Map.entry("sip.t140.offered", Boolean.toString(receiver.t140Offered.get())),
                    Map.entry("sip.red.offered", Boolean.toString(receiver.redOffered.get())),
                    Map.entry("sip.red.fmtpOffered", Boolean.toString(receiver.redFmtpOffered.get())),
                    Map.entry("sip.ack.observed", Boolean.toString(receiver.ackObserved.get())),
                    Map.entry("rtt.datagram.minimumTwoObserved", Boolean.toString(packetsObserved)),
                    Map.entry("rtt.datagram.count", Integer.toString(media.packetCount())),
                    Map.entry("rfc2198Observed", "UNCLASSIFIED_BY_JAVA"),
                    Map.entry("lossRecovered", "UNCLASSIFIED_BY_JAVA"),
                    Map.entry("scenario.result", pass ? "OBSERVED" : "INCOMPLETE"),
                    Map.entry("claim.sipConformance", "false"),
                    Map.entry("claim.rfc2198Conformance", "false"),
                    Map.entry("claim.rfc4103Conformance", "false"),
                    Map.entry("claim.t140Conformance", "false")));

            if (!pass) {
                throw new IllegalStateException("PJSIP native RFC2198 observation was incomplete");
            }
        }
        System.exit(0);
    }

    private void start() throws Exception {
        stack.start();
    }

    @Override
    public void processRequest(RequestEvent event) {
        Request request = event.getRequest();
        int ordinal = requestOrdinal.incrementAndGet();
        try {
            evidence.writeBytes("sip-request-" + ordinal + ".sip",
                    request.toString().getBytes(StandardCharsets.UTF_8));

            if (Request.INVITE.equals(request.getMethod())) {
                handleInvite(event, request);
                return;
            }
            if (Request.ACK.equals(request.getMethod())) {
                ackObserved.set(true);
                ack.countDown();
                evidence.event("pjsip.native_red.ack_observed", Map.of());
                return;
            }
            if (Request.BYE.equals(request.getMethod())) {
                ServerTransaction transaction = event.getServerTransaction();
                if (transaction == null) {
                    transaction = provider.getNewServerTransaction(request);
                }
                Response ok = messages.createResponse(Response.OK, request);
                evidence.writeBytes("bye-200.response.sip", ok.toString().getBytes(StandardCharsets.UTF_8));
                transaction.sendResponse(ok);
                evidence.event("pjsip.native_red.bye_observed", Map.of());
            }
        } catch (Exception failure) {
            evidence.event("pjsip.native_red.request_error", Map.of(
                    "method", request.getMethod(), "error", failure.toString()));
        }
    }

    private void handleInvite(RequestEvent event, Request request) throws Exception {
        inviteObserved.set(true);
        String body = request.getRawContent() == null
                ? "" : new String(request.getRawContent(), StandardCharsets.UTF_8);
        String lower = body.toLowerCase();
        boolean hasText = lower.contains("m=text ");
        boolean hasT140 = lower.contains("t140/1000");
        boolean hasRed = lower.contains("red/1000");
        boolean hasRedFmtp = lower.contains("fmtp:100") && lower.contains("98/98/98");
        textOffered.set(hasText);
        t140Offered.set(hasT140);
        redOffered.set(hasRed);
        redFmtpOffered.set(hasRedFmtp);
        evidence.writeBytes("pjsip-offer.sdp", body.getBytes(StandardCharsets.UTF_8));
        evidence.event("pjsip.native_red.invite_observed", Map.of(
                "textOffered", Boolean.toString(hasText),
                "t140Offered", Boolean.toString(hasT140),
                "redOffered", Boolean.toString(hasRed),
                "redFmtpOffered", Boolean.toString(hasRedFmtp)));

        ServerTransaction transaction = event.getServerTransaction();
        if (transaction == null) {
            transaction = provider.getNewServerTransaction(request);
        }
        if (!hasText || !hasT140 || !hasRed || !hasRedFmtp) {
            transaction.sendResponse(messages.createResponse(Response.NOT_ACCEPTABLE_HERE, request));
            return;
        }

        Response ok = messages.createResponse(Response.OK, request);
        ToHeader to = (ToHeader) ok.getHeader(ToHeader.NAME);
        if (to.getTag() == null) {
            to.setTag("baudot-pjsip-native-rfc2198");
        }
        ok.addHeader(contact());

        String sdp = String.join("\r\n",
                "v=0",
                "o=baudot 3 3 IN IP4 " + HOST,
                "s=Baudot PJSIP native RFC2198 gate",
                "c=IN IP4 " + HOST,
                "t=0 0",
                "m=text " + mediaPort + " RTP/AVP 100 98",
                "a=rtpmap:100 red/1000",
                "a=fmtp:100 98/98/98",
                "a=rtpmap:98 t140/1000",
                "a=sendrecv",
                "");
        ContentTypeHeader contentType = SipFactory.getInstance().createHeaderFactory()
                .createContentTypeHeader("application", "sdp");
        ok.setContent(sdp, contentType);
        evidence.writeBytes("baudot-answer.sdp", sdp.getBytes(StandardCharsets.UTF_8));
        evidence.writeBytes("invite-200.response.sip", ok.toString().getBytes(StandardCharsets.UTF_8));
        transaction.sendResponse(ok);
        evidence.event("pjsip.native_red.answer_sent", Map.of(
                "redPayloadType", "100",
                "t140PayloadType", "98",
                "redundancyLevel", "2",
                "mediaPort", Integer.toString(mediaPort)));
    }

    private ContactHeader contact() throws Exception {
        SipURI uri = addresses.createSipURI("baudot-red", HOST);
        uri.setPort(sipPort);
        uri.setTransportParam(ListeningPoint.UDP);
        Address address = addresses.createAddress(uri);
        return SipFactory.getInstance().createHeaderFactory().createContactHeader(address);
    }

    @Override
    public void processResponse(ResponseEvent event) {
        evidence.event("pjsip.native_red.unexpected_response", Map.of(
                "status", Integer.toString(event.getResponse().getStatusCode())));
    }

    @Override
    public void processTimeout(TimeoutEvent event) {
        evidence.event("pjsip.native_red.timeout", Map.of(
                "server", Boolean.toString(event.isServerTransaction())));
    }

    @Override
    public void processIOException(IOExceptionEvent event) {
        evidence.event("pjsip.native_red.io_error", Map.of(
                "host", String.valueOf(event.getHost()),
                "port", Integer.toString(event.getPort()),
                "transport", String.valueOf(event.getTransport())));
    }

    @Override public void processTransactionTerminated(TransactionTerminatedEvent event) {}
    @Override public void processDialogTerminated(DialogTerminatedEvent event) {}

    @Override
    public void close() {
        try {
            stack.stop();
        } catch (Exception failure) {
            evidence.event("pjsip.native_red.stop_error", Map.of("error", failure.toString()));
        }
    }

    private static final class MediaReceiver implements AutoCloseable {
        private final EvidenceRecorder evidence;
        private final DatagramSocket socket;
        private final AtomicInteger packets = new AtomicInteger();
        private final CountDownLatch minimumTwo = new CountDownLatch(2);
        private volatile boolean closed;
        private Thread thread;

        MediaReceiver(int port, EvidenceRecorder evidence) throws Exception {
            this.evidence = evidence;
            this.socket = new DatagramSocket(new InetSocketAddress(InetAddress.getByName(HOST), port));
            this.socket.setSoTimeout(2600);
        }

        void start() {
            thread = new Thread(this::run, "baudot-pjsip-native-rfc2198-media");
            thread.setDaemon(true);
            thread.start();
        }

        boolean awaitMinimum(Duration timeout) throws InterruptedException {
            return minimumTwo.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        int packetCount() {
            return packets.get();
        }

        private void run() {
            while (!closed) {
                try {
                    byte[] buffer = new byte[4096];
                    DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                    socket.receive(packet);
                    byte[] content = Arrays.copyOfRange(
                            packet.getData(), packet.getOffset(), packet.getOffset() + packet.getLength());
                    int ordinal = packets.incrementAndGet();
                    evidence.writeBytes(String.format("rtt-datagram-%03d.bin", ordinal), content);
                    evidence.event("pjsip.native_red.datagram_observed", Map.of(
                            "ordinal", Integer.toString(ordinal),
                            "bytes", Integer.toString(content.length),
                            "source", packet.getAddress().getHostAddress() + ":" + packet.getPort(),
                            "semanticClassification", "UNCLASSIFIED_BY_JAVA"));
                    if (minimumTwo.getCount() > 0) {
                        minimumTwo.countDown();
                    }
                } catch (SocketTimeoutException timeout) {
                    if (minimumTwo.getCount() == 0) {
                        return;
                    }
                } catch (Exception failure) {
                    if (!closed) {
                        evidence.event("pjsip.native_red.media_error", Map.of("error", failure.toString()));
                    }
                    return;
                }
            }
        }

        @Override
        public void close() {
            closed = true;
            socket.close();
            if (thread != null) {
                try {
                    thread.join(500L);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                }
            }
        }
    }

    private static int envInt(String name, int fallback) {
        return Integer.parseInt(env(name, Integer.toString(fallback)));
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }
}
