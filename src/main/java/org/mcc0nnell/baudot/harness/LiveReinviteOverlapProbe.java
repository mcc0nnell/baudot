package org.mcc0nnell.baudot.harness;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
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
import javax.sip.header.ContentTypeHeader;
import javax.sip.header.HeaderFactory;
import javax.sip.header.ToHeader;
import javax.sip.message.MessageFactory;
import javax.sip.message.Request;
import javax.sip.message.Response;

/**
 * Live network gate for BAUDOT-INTEROP-003.
 *
 * A JAIN SIP UAS establishes a real dialog with a raw UDP peer. The peer then
 * injects two independent in-dialog INVITEs before the first is answered. The
 * first transaction is deliberately held in TRYING while the second arrives,
 * allowing the JAIN SIP dialog filter to exercise its Request Pending behavior.
 */
public final class LiveReinviteOverlapProbe {
    private static final String SCENARIO = "BAUDOT-INTEROP-003";
    private static final String CORRELATION = "jain-live-overlap-v1";
    private static final String CALL_ID = "baudot-live-reinvite@127.0.0.1";
    private static final String FROM_TAG = "baudot-live-caller";
    private static final String TO_TAG = "baudot-live-callee";
    private static final String HOST = "127.0.0.1";
    private static final int UAS_PORT = 5090;
    private static final int PEER_PORT = 5091;
    private static final Duration TIMEOUT = Duration.ofSeconds(5);

    private LiveReinviteOverlapProbe() {
    }

    public static void main(String[] args) throws Exception {
        Path evidenceRoot = Path.of(env("BAUDOT_EVIDENCE_DIR", "target/evidence"));
        try (EvidenceRecorder evidence = new EvidenceRecorder(
                evidenceRoot, SCENARIO, CORRELATION, "live-overlap");
             LiveUas uas = new LiveUas(evidence);
             DatagramSocket peer = new DatagramSocket(new InetSocketAddress(InetAddress.getByName(HOST), PEER_PORT))) {

            peer.setSoTimeout((int) TIMEOUT.toMillis());
            uas.start();

            String initialInvite = invite(1, null, "z9hG4bK-live-initial", sdp(41001, "offer-initial"));
            send(peer, initialInvite, evidence, "initial-invite.request.sip");
            RawResponse initial200 = receiveFinal(peer, 1, evidence, "initial");
            require(initial200.status() == Response.OK, "initial INVITE did not receive 200");
            require(TO_TAG.equals(initial200.toTag()), "initial 200 did not preserve expected To tag");

            String initialAck = ack(1, TO_TAG, "z9hG4bK-live-ack-1");
            send(peer, initialAck, evidence, "initial-ack.request.sip");
            require(uas.awaitInitialAck(TIMEOUT), "initial ACK was not observed by JAIN SIP UAS");

            String firstOffer = sdp(41002, "offer-reinvite-2");
            String firstReinvite = invite(2, TO_TAG, "z9hG4bK-live-reinvite-2", firstOffer);
            send(peer, firstReinvite, evidence, "reinvite-2.request.sip");
            evidence.writeBytes("reinvite-2.offer.sdp", firstOffer.getBytes(StandardCharsets.UTF_8));
            require(uas.awaitFirstReinvite(TIMEOUT), "first re-INVITE was not delivered to the application");

            String secondOffer = sdp(41003, "offer-reinvite-3");
            String secondReinvite = invite(3, TO_TAG, "z9hG4bK-live-reinvite-3", secondOffer);
            send(peer, secondReinvite, evidence, "reinvite-3.request.sip");
            evidence.writeBytes("reinvite-3.offer.sdp", secondOffer.getBytes(StandardCharsets.UTF_8));

            RawResponse secondFinal = receiveFinal(peer, 3, evidence, "reinvite-3");
            require(secondFinal.status() == Response.REQUEST_PENDING,
                    "overlapping re-INVITE did not receive 491 Request Pending");

            uas.completeFirstReinvite();
            RawResponse firstFinal = receiveFinal(peer, 2, evidence, "reinvite-2");
            require(firstFinal.status() == Response.OK, "first pending re-INVITE did not complete with 200");

            String reinviteAck = ack(2, TO_TAG, "z9hG4bK-live-ack-2");
            send(peer, reinviteAck, evidence, "reinvite-2-ack.request.sip");
            require(uas.awaitReinviteAck(TIMEOUT), "ACK for first re-INVITE was not observed");

            boolean secondReachedApplication = uas.secondReinviteDelivered();
            boolean pass = initial200.status() == Response.OK
                    && secondFinal.status() == Response.REQUEST_PENDING
                    && firstFinal.status() == Response.OK
                    && uas.initialAckReceived()
                    && uas.reinviteAckReceived();

            evidence.result(Map.ofEntries(
                    Map.entry("correlation.id", CORRELATION),
                    Map.entry("dialog.established", "true"),
                    Map.entry("first.reinvite.delivered", "true"),
                    Map.entry("first.reinvite.status", Integer.toString(firstFinal.status())),
                    Map.entry("glare.reinvite.status", Integer.toString(secondFinal.status())),
                    Map.entry("glare.reinvite.deliveredToApplication", Boolean.toString(secondReachedApplication)),
                    Map.entry("harness.layer", "jain-sip-live-dialog-overlap"),
                    Map.entry("live.dialog.overlap.proven", Boolean.toString(pass)),
                    Map.entry("media.readiness.proven", "false"),
                    Map.entry("scenario.id", SCENARIO),
                    Map.entry("scenario.result", pass ? "PASS" : "FAIL")));

            if (!pass) {
                throw new IllegalStateException("BAUDOT-INTEROP-003 live overlap gate failed");
            }
        }
    }

    private static void send(DatagramSocket socket, String message, EvidenceRecorder evidence, String filename)
            throws Exception {
        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        evidence.writeBytes(filename, bytes);
        DatagramPacket packet = new DatagramPacket(
                bytes, bytes.length, InetAddress.getByName(HOST), UAS_PORT);
        socket.send(packet);
        evidence.event("wire.request.sent", Map.of(
                "file", filename,
                "bytes", Integer.toString(bytes.length)));
    }

    private static RawResponse receiveFinal(
            DatagramSocket socket, long expectedCseq, EvidenceRecorder evidence, String label) throws Exception {
        int ordinal = 0;
        while (true) {
            byte[] buffer = new byte[8192];
            DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
            socket.receive(packet);
            String raw = new String(packet.getData(), packet.getOffset(), packet.getLength(), StandardCharsets.UTF_8);
            RawResponse response = RawResponse.parse(raw);
            ordinal++;
            evidence.writeBytes(
                    label + "-response-" + ordinal + ".sip",
                    raw.getBytes(StandardCharsets.UTF_8));
            evidence.event("wire.response.received", Map.of(
                    "label", label,
                    "status", Integer.toString(response.status()),
                    "cseq", Long.toString(response.cseq()),
                    "method", response.method()));
            if (response.cseq() == expectedCseq && response.status() >= 200) {
                return response;
            }
        }
    }

    private static String invite(long cseq, String toTag, String branch, String body) {
        String to = "<sip:callee@" + HOST + ":" + UAS_PORT + ">"
                + (toTag == null ? "" : ";tag=" + toTag);
        byte[] bodyBytes = body.getBytes(StandardCharsets.UTF_8);
        return "INVITE sip:callee@" + HOST + ":" + UAS_PORT + " SIP/2.0\r\n"
                + "Via: SIP/2.0/UDP " + HOST + ":" + PEER_PORT + ";branch=" + branch + ";rport\r\n"
                + "Max-Forwards: 70\r\n"
                + "From: <sip:caller@" + HOST + ":" + PEER_PORT + ">;tag=" + FROM_TAG + "\r\n"
                + "To: " + to + "\r\n"
                + "Call-ID: " + CALL_ID + "\r\n"
                + "CSeq: " + cseq + " INVITE\r\n"
                + "Contact: <sip:caller@" + HOST + ":" + PEER_PORT + ">\r\n"
                + "Content-Type: application/sdp\r\n"
                + "Content-Length: " + bodyBytes.length + "\r\n"
                + "\r\n"
                + body;
    }

    private static String ack(long cseq, String toTag, String branch) {
        return "ACK sip:callee@" + HOST + ":" + UAS_PORT + " SIP/2.0\r\n"
                + "Via: SIP/2.0/UDP " + HOST + ":" + PEER_PORT + ";branch=" + branch + ";rport\r\n"
                + "Max-Forwards: 70\r\n"
                + "From: <sip:caller@" + HOST + ":" + PEER_PORT + ">;tag=" + FROM_TAG + "\r\n"
                + "To: <sip:callee@" + HOST + ":" + UAS_PORT + ">;tag=" + toTag + "\r\n"
                + "Call-ID: " + CALL_ID + "\r\n"
                + "CSeq: " + cseq + " ACK\r\n"
                + "Content-Length: 0\r\n"
                + "\r\n";
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

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    private record RawResponse(int status, long cseq, String method, String toTag) {
        private static final Pattern STATUS = Pattern.compile("^SIP/2\\.0\\s+(\\d{3})", Pattern.MULTILINE);
        private static final Pattern CSEQ = Pattern.compile("(?im)^CSeq:\\s*(\\d+)\\s+([A-Z]+)\\s*$");
        private static final Pattern TO = Pattern.compile("(?im)^To:\\s*.*?;tag=([^;\\s>]+)");

        static RawResponse parse(String raw) {
            Matcher status = STATUS.matcher(raw);
            Matcher cseq = CSEQ.matcher(raw);
            Matcher to = TO.matcher(raw);
            if (!status.find() || !cseq.find()) {
                throw new IllegalArgumentException("Unable to parse SIP response: " + raw);
            }
            return new RawResponse(
                    Integer.parseInt(status.group(1)),
                    Long.parseLong(cseq.group(1)),
                    cseq.group(2),
                    to.find() ? to.group(1) : "");
        }
    }

    private static final class LiveUas implements SipListener, AutoCloseable {
        private final EvidenceRecorder evidence;
        private final CountDownLatch initialAck = new CountDownLatch(1);
        private final CountDownLatch firstReinvite = new CountDownLatch(1);
        private final CountDownLatch reinviteAck = new CountDownLatch(1);
        private final AtomicBoolean secondDelivered = new AtomicBoolean();

        private final SipStack stack;
        private final SipProvider provider;
        private final AddressFactory addresses;
        private final HeaderFactory headers;
        private final MessageFactory messages;

        private volatile ServerTransaction pendingFirstTransaction;
        private volatile Request pendingFirstRequest;

        LiveUas(EvidenceRecorder evidence) throws Exception {
            this.evidence = evidence;
            SipFactory factory = SipFactory.getInstance();
            factory.setPathName("gov.nist");

            Properties properties = new Properties();
            properties.setProperty("javax.sip.STACK_NAME", "baudot-live-reinvite-overlap");
            properties.setProperty("gov.nist.javax.sip.TRACE_LEVEL", "0");
            this.stack = factory.createSipStack(properties);
            this.addresses = factory.createAddressFactory();
            this.headers = factory.createHeaderFactory();
            this.messages = factory.createMessageFactory();

            ListeningPoint point = stack.createListeningPoint(HOST, UAS_PORT, ListeningPoint.UDP);
            this.provider = stack.createSipProvider(point);
            this.provider.addSipListener(this);
        }

        void start() throws Exception {
            stack.start();
            evidence.event("live.uas.ready", Map.of(
                    "bind", HOST + ":" + UAS_PORT,
                    "transport", "udp"));
        }

        boolean awaitInitialAck(Duration timeout) throws InterruptedException {
            return initialAck.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        boolean awaitFirstReinvite(Duration timeout) throws InterruptedException {
            return firstReinvite.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        boolean awaitReinviteAck(Duration timeout) throws InterruptedException {
            return reinviteAck.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        boolean initialAckReceived() {
            return initialAck.getCount() == 0;
        }

        boolean reinviteAckReceived() {
            return reinviteAck.getCount() == 0;
        }

        boolean secondReinviteDelivered() {
            return secondDelivered.get();
        }

        synchronized void completeFirstReinvite() throws Exception {
            require(pendingFirstTransaction != null && pendingFirstRequest != null,
                    "no pending first re-INVITE to complete");
            Response ok = messages.createResponse(Response.OK, pendingFirstRequest);
            addContact(ok);
            ok.setContent(
                    sdp(42002, "answer-reinvite-2"),
                    headers.createContentTypeHeader("application", "sdp"));
            pendingFirstTransaction.sendResponse(ok);
            evidence.event("live.reinvite.response.sent", Map.of(
                    "cseq", "2",
                    "status", "200"));
        }

        @Override
        public void processRequest(RequestEvent event) {
            Request request = event.getRequest();
            CSeqHeader cseq = (CSeqHeader) request.getHeader(CSeqHeader.NAME);
            long sequence = cseq == null ? -1 : cseq.getSeqNumber();
            try {
                if (Request.ACK.equals(request.getMethod())) {
                    evidence.event("live.ack.received", Map.of("cseq", Long.toString(sequence)));
                    if (sequence == 1) {
                        initialAck.countDown();
                    } else if (sequence == 2) {
                        reinviteAck.countDown();
                    }
                    return;
                }

                if (!Request.INVITE.equals(request.getMethod())) {
                    return;
                }

                ServerTransaction transaction = event.getServerTransaction();
                if (transaction == null) {
                    transaction = provider.getNewServerTransaction(request);
                }
                evidence.event("live.invite.delivered", Map.of(
                        "cseq", Long.toString(sequence),
                        "dialog", event.getDialog() == null ? "none" : String.valueOf(event.getDialog().getDialogId())));

                if (sequence == 1) {
                    Response ok = messages.createResponse(Response.OK, request);
                    ToHeader to = (ToHeader) ok.getHeader(ToHeader.NAME);
                    if (to.getTag() == null) {
                        to.setTag(TO_TAG);
                    }
                    addContact(ok);
                    ok.setContent(
                            sdp(42001, "answer-initial"),
                            headers.createContentTypeHeader("application", "sdp"));
                    transaction.sendResponse(ok);
                    evidence.event("live.initial.response.sent", Map.of("status", "200"));
                    return;
                }

                if (sequence == 2) {
                    pendingFirstTransaction = transaction;
                    pendingFirstRequest = request;
                    firstReinvite.countDown();
                    evidence.event("live.reinvite.held", Map.of(
                            "cseq", "2",
                            "state", String.valueOf(transaction.getState())));
                    return;
                }

                if (sequence == 3) {
                    secondDelivered.set(true);
                    Response pending = messages.createResponse(Response.REQUEST_PENDING, request);
                    transaction.sendResponse(pending);
                    evidence.event("live.reinvite.application_491", Map.of(
                            "cseq", "3",
                            "status", "491"));
                }
            } catch (Exception e) {
                evidence.event("live.uas.error", Map.of(
                        "cseq", Long.toString(sequence),
                        "error", e.toString()));
            }
        }

        private void addContact(Response response) throws Exception {
            SipURI contactUri = addresses.createSipURI("callee", HOST);
            contactUri.setPort(UAS_PORT);
            contactUri.setTransportParam(ListeningPoint.UDP);
            Address contactAddress = addresses.createAddress(contactUri);
            ContactHeader contact = headers.createContactHeader(contactAddress);
            response.addHeader(contact);
        }

        @Override
        public void processResponse(ResponseEvent event) {
            // UAS-only harness.
        }

        @Override
        public void processTimeout(TimeoutEvent event) {
            evidence.event("live.timeout", Map.of(
                    "server", Boolean.toString(event.isServerTransaction())));
        }

        @Override
        public void processIOException(IOExceptionEvent event) {
            evidence.event("live.io_error", Map.of(
                    "host", String.valueOf(event.getHost()),
                    "port", Integer.toString(event.getPort()),
                    "transport", String.valueOf(event.getTransport())));
        }

        @Override
        public void processTransactionTerminated(TransactionTerminatedEvent event) {
            evidence.event("live.transaction.terminated", Map.of(
                    "server", Boolean.toString(event.isServerTransaction())));
        }

        @Override
        public void processDialogTerminated(DialogTerminatedEvent event) {
            evidence.event("live.dialog.terminated", Map.of(
                    "dialog", String.valueOf(event.getDialog().getDialogId())));
        }

        @Override
        public void close() {
            try {
                stack.stop();
            } catch (Exception e) {
                evidence.event("live.stop.error", Map.of("error", e.toString()));
            }
        }
    }
}
