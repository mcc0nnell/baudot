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
 * Receives a PJSIP/PJMEDIA-native text call and preserves its RTT datagrams.
 *
 * <p>JAIN SIP owns only the controlled SIP UAS and SDP answer in this probe.
 * Java deliberately does not classify the UDP datagrams as RTP, RFC 4103, or
 * T.140. The independent Python reference parser owns that semantic verdict.</p>
 */
public final class PjsipNativeTextReceiverProbe implements SipListener, AutoCloseable {
    private static final String HOST = "127.0.0.1";
    private static final String SCENARIO = "PJSIP-NATIVE-T140";
    private static final String CORRELATION = "pjsip-2.17-native-text-v1";
    private static final Duration TIMEOUT = Duration.ofSeconds(12);

    private final int sipPort;
    private final int mediaPort;
    private final EvidenceRecorder evidence;
    private final SipStack stack;
    private final SipProvider provider;
    private final AddressFactory addresses;
    private final MessageFactory messages;
    private final CountDownLatch ack = new CountDownLatch(1);
    private final CountDownLatch bye = new CountDownLatch(1);
    private final AtomicBoolean inviteObserved = new AtomicBoolean();
    private final AtomicBoolean textOffered = new AtomicBoolean();
    private final AtomicBoolean t140Offered = new AtomicBoolean();
    private final AtomicBoolean ackObserved = new AtomicBoolean();
    private final AtomicBoolean byeObserved = new AtomicBoolean();
    private final AtomicInteger requestOrdinal = new AtomicInteger();

    private PjsipNativeTextReceiverProbe(int sipPort, int mediaPort, EvidenceRecorder evidence)
            throws Exception {
        this.sipPort = sipPort;
        this.mediaPort = mediaPort;
        this.evidence = evidence;

        SipFactory factory = SipFactory.getInstance();
        factory.setPathName("gov.nist");
        Properties properties = new Properties();
        properties.setProperty("javax.sip.STACK_NAME", "baudot-pjsip-native-t140-receiver");
        properties.setProperty("gov.nist.javax.sip.TRACE_LEVEL", "0");
        this.stack = factory.createSipStack(properties);
        this.addresses = factory.createAddressFactory();
        this.messages = factory.createMessageFactory();
        ListeningPoint point = stack.createListeningPoint(HOST, sipPort, ListeningPoint.UDP);
        this.provider = stack.createSipProvider(point);
        this.provider.addSipListener(this);
    }

    public static void main(String[] args) throws Exception {
        int sipPort = envInt("BAUDOT_PJSIP_REMOTE_PORT", 5290);
        int mediaPort = envInt("BAUDOT_PJSIP_MEDIA_PORT", 5292);
        Path root = Path.of(env("BAUDOT_EVIDENCE_ROOT", "target/evidence-external"));

        try (EvidenceRecorder evidence = new EvidenceRecorder(root, SCENARIO, CORRELATION, "jain-receiver");
             MediaReceiver media = new MediaReceiver(mediaPort, evidence);
             PjsipNativeTextReceiverProbe receiver =
                     new PjsipNativeTextReceiverProbe(sipPort, mediaPort, evidence)) {

            media.start();
            receiver.start();
            evidence.event("pjsip.native_text.receiver_ready", Map.of(
                    "sipBind", HOST + ":" + sipPort,
                    "mediaBind", HOST + ":" + mediaPort,
                    "semanticAuthority", "python-reference"));

            boolean packetObserved = media.awaitFirst(TIMEOUT);
            boolean ackObserved = receiver.ack.await(TIMEOUT.toMillis(), TimeUnit.MILLISECONDS);
            if (packetObserved) {
                Thread.sleep(650L);
            }

            boolean pass = receiver.inviteObserved.get()
                    && receiver.textOffered.get()
                    && receiver.t140Offered.get()
                    && ackObserved
                    && packetObserved;

            evidence.result(Map.ofEntries(
                    Map.entry("correlation.id", CORRELATION),
                    Map.entry("implementation", "pjsip/pjproject"),
                    Map.entry("implementation.release", "2.17"),
                    Map.entry("scenario.id", SCENARIO),
                    Map.entry("sip.invite.observed", Boolean.toString(receiver.inviteObserved.get())),
                    Map.entry("sip.text.offered", Boolean.toString(receiver.textOffered.get())),
                    Map.entry("sip.t140.offered", Boolean.toString(receiver.t140Offered.get())),
                    Map.entry("sip.ack.observed", Boolean.toString(receiver.ackObserved.get())),
                    Map.entry("rtt.datagram.observed", Boolean.toString(packetObserved)),
                    Map.entry("rtt.datagram.count", Integer.toString(media.packetCount())),
                    Map.entry("firstT140CharacterObserved", "UNCLASSIFIED_BY_JAVA"),
                    Map.entry("rttReady", "UNCLASSIFIED_BY_JAVA"),
                    Map.entry("scenario.result", pass ? "OBSERVED" : "INCOMPLETE"),
                    Map.entry("claim.sipConformance", "false"),
                    Map.entry("claim.rfc4103Conformance", "false"),
                    Map.entry("claim.t140Conformance", "false")));

            if (!pass) {
                throw new IllegalStateException("PJSIP native text wire observation was incomplete");
            }
        }

        // The NIST JAIN SIP implementation may retain non-daemon worker
        // threads after SipStack.stop() even though all Baudot evidence
        // resources have closed and their manifests have been written. This
        // probe is a standalone process, so terminate explicitly only after
        // successful resource closure rather than letting implementation
        // thread lifetime hold the external oracle gate open.
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
            evidence.writeBytes(
                    "sip-request-" + ordinal + ".sip",
                    request.toString().getBytes(StandardCharsets.UTF_8));

            if (Request.INVITE.equals(request.getMethod())) {
                handleInvite(event, request);
                return;
            }

            if (Request.ACK.equals(request.getMethod())) {
                ackObserved.set(true);
                ack.countDown();
                evidence.event("pjsip.native_text.ack_observed", Map.of());
                return;
            }

            if (Request.BYE.equals(request.getMethod())) {
                byeObserved.set(true);
                bye.countDown();
                ServerTransaction transaction = event.getServerTransaction();
                if (transaction == null) {
                    transaction = provider.getNewServerTransaction(request);
                }
                Response ok = messages.createResponse(Response.OK, request);
                evidence.writeBytes(
                        "bye-200.response.sip",
                        ok.toString().getBytes(StandardCharsets.UTF_8));
                transaction.sendResponse(ok);
                evidence.event("pjsip.native_text.bye_observed", Map.of());
            }
        } catch (Exception failure) {
            evidence.event("pjsip.native_text.request_error", Map.of(
                    "method", request.getMethod(),
                    "error", failure.toString()));
        }
    }

    private void handleInvite(RequestEvent event, Request request) throws Exception {
        inviteObserved.set(true);
        String body = request.getRawContent() == null
                ? ""
                : new String(request.getRawContent(), StandardCharsets.UTF_8);
        String lower = body.toLowerCase();
        boolean hasText = lower.contains("m=text ");
        boolean hasT140 = lower.contains("t140/1000");
        textOffered.set(hasText);
        t140Offered.set(hasT140);
        evidence.writeBytes("pjsip-offer.sdp", body.getBytes(StandardCharsets.UTF_8));
        evidence.event("pjsip.native_text.invite_observed", Map.of(
                "textOffered", Boolean.toString(hasText),
                "t140Offered", Boolean.toString(hasT140)));

        ServerTransaction transaction = event.getServerTransaction();
        if (transaction == null) {
            transaction = provider.getNewServerTransaction(request);
        }

        if (!hasText || !hasT140) {
            Response reject = messages.createResponse(Response.NOT_ACCEPTABLE_HERE, request);
            transaction.sendResponse(reject);
            return;
        }

        Response ok = messages.createResponse(Response.OK, request);
        ToHeader to = (ToHeader) ok.getHeader(ToHeader.NAME);
        if (to.getTag() == null) {
            to.setTag("baudot-pjsip-native-t140");
        }
        ok.addHeader(contact());

        String sdp = String.join("\r\n",
                "v=0",
                "o=baudot 1 1 IN IP4 " + HOST,
                "s=Baudot PJSIP native T.140 gate",
                "c=IN IP4 " + HOST,
                "t=0 0",
                "m=text " + mediaPort + " RTP/AVP 98",
                "a=rtpmap:98 t140/1000",
                "a=sendrecv",
                "");
        ContentTypeHeader contentType =
                SipFactory.getInstance().createHeaderFactory().createContentTypeHeader("application", "sdp");
        ok.setContent(sdp, contentType);
        evidence.writeBytes("baudot-answer.sdp", sdp.getBytes(StandardCharsets.UTF_8));
        evidence.writeBytes("invite-200.response.sip", ok.toString().getBytes(StandardCharsets.UTF_8));
        transaction.sendResponse(ok);
        evidence.event("pjsip.native_text.answer_sent", Map.of(
                "payloadType", "98",
                "clockRate", "1000",
                "mediaPort", Integer.toString(mediaPort)));
    }

    private ContactHeader contact() throws Exception {
        SipURI uri = addresses.createSipURI("baudot", HOST);
        uri.setPort(sipPort);
        uri.setTransportParam(ListeningPoint.UDP);
        Address address = addresses.createAddress(uri);
        return SipFactory.getInstance().createHeaderFactory().createContactHeader(address);
    }

    @Override
    public void processResponse(ResponseEvent event) {
        evidence.event("pjsip.native_text.unexpected_response", Map.of(
                "status", Integer.toString(event.getResponse().getStatusCode())));
    }

    @Override
    public void processTimeout(TimeoutEvent event) {
        evidence.event("pjsip.native_text.timeout", Map.of(
                "server", Boolean.toString(event.isServerTransaction())));
    }

    @Override
    public void processIOException(IOExceptionEvent event) {
        evidence.event("pjsip.native_text.io_error", Map.of(
                "host", String.valueOf(event.getHost()),
                "port", Integer.toString(event.getPort()),
                "transport", String.valueOf(event.getTransport())));
    }

    @Override
    public void processTransactionTerminated(TransactionTerminatedEvent event) {
        // Preserved packet evidence, not transaction lifecycle, owns this gate.
    }

    @Override
    public void processDialogTerminated(DialogTerminatedEvent event) {
        evidence.event("pjsip.native_text.dialog_terminated", Map.of(
                "dialog", String.valueOf(event.getDialog().getDialogId())));
    }

    @Override
    public void close() {
        try {
            stack.stop();
        } catch (Exception failure) {
            evidence.event("pjsip.native_text.stop_error", Map.of("error", failure.toString()));
        }
    }

    private static final class MediaReceiver implements AutoCloseable {
        private final EvidenceRecorder evidence;
        private final DatagramSocket socket;
        private final CountDownLatch first = new CountDownLatch(1);
        private final AtomicInteger packets = new AtomicInteger();
        private volatile boolean closed;
        private Thread thread;

        MediaReceiver(int port, EvidenceRecorder evidence) throws Exception {
            this.evidence = evidence;
            this.socket = new DatagramSocket(new InetSocketAddress(InetAddress.getByName(HOST), port));
            this.socket.setSoTimeout(2000);
        }

        void start() {
            thread = new Thread(this::run, "baudot-pjsip-native-t140-media");
            thread.setDaemon(true);
            thread.start();
        }

        boolean awaitFirst(Duration timeout) throws InterruptedException {
            return first.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
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
                    String filename = String.format("rtt-datagram-%03d.bin", ordinal);
                    evidence.writeBytes(filename, content);
                    evidence.event("pjsip.native_text.datagram_observed", Map.of(
                            "ordinal", Integer.toString(ordinal),
                            "bytes", Integer.toString(content.length),
                            "source", packet.getAddress().getHostAddress() + ":" + packet.getPort(),
                            "semanticClassification", "UNCLASSIFIED_BY_JAVA"));
                    first.countDown();
                } catch (SocketTimeoutException timeout) {
                    if (first.getCount() == 0) {
                        return;
                    }
                } catch (Exception failure) {
                    if (!closed) {
                        evidence.event("pjsip.native_text.media_error", Map.of(
                                "error", failure.toString()));
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
