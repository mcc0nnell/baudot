package org.mcc0nnell.baudot.harness;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

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
import javax.sip.address.URI;
import javax.sip.header.CSeqHeader;
import javax.sip.header.CallIdHeader;
import javax.sip.header.ContactHeader;
import javax.sip.header.ContentTypeHeader;
import javax.sip.header.EventHeader;
import javax.sip.header.ExpiresHeader;
import javax.sip.header.FromHeader;
import javax.sip.header.HeaderFactory;
import javax.sip.header.MaxForwardsHeader;
import javax.sip.header.ReferToHeader;
import javax.sip.header.SubscriptionStateHeader;
import javax.sip.header.ToHeader;
import javax.sip.header.ViaHeader;
import javax.sip.message.MessageFactory;
import javax.sip.message.Request;
import javax.sip.message.Response;

/**
 * First live network gate for BAUDOT-INTEROP-004.
 *
 * <p>A raw referrer establishes a real dialog with a JAIN SIP provider role,
 * sends an in-dialog REFER, receives the implicit refer subscription NOTIFYs,
 * and answers them. The JAIN SIP provider role follows Refer-To with a new
 * INVITE to an independently addressed raw target provider. Only after the
 * replacement INVITE reaches 200 and the final NOTIFY is acknowledged does the
 * provider role tear down the old dialog.</p>
 *
 * <p>This gate proves live transfer signaling and target correlation only. It
 * deliberately does not claim replacement-leg RTT/media readiness.</p>
 */
public final class LiveReferProviderTransferProbe {
    private static final String SCENARIO = "BAUDOT-INTEROP-004";
    private static final String CORRELATION = "jain-live-refer-v1";
    private static final String HOST = "127.0.0.1";
    private static final int PROVIDER_A_PORT = 5120;
    private static final int REFERRER_PORT = 5121;
    private static final int PROVIDER_B_PORT = 5122;
    private static final String ORIGINAL_CALL_ID = "baudot-refer-original@127.0.0.1";
    private static final String REFERRER_TAG = "baudot-referrer";
    private static final String PROVIDER_A_TAG = "baudot-provider-a";
    private static final String PROVIDER_B_TAG = "baudot-provider-b";
    private static final Duration TIMEOUT = Duration.ofSeconds(5);

    private LiveReferProviderTransferProbe() {
    }

    public static void main(String[] args) {
        int exit;
        try {
            exit = run();
        } catch (Throwable failure) {
            failure.printStackTrace(System.err);
            exit = 2;
        }
        System.exit(exit);
    }

    private static int run() throws Exception {
        Path evidenceRoot = Path.of(env("BAUDOT_EVIDENCE_DIR", "target/evidence"));
        AtomicReference<Throwable> targetFailure = new AtomicReference<>();
        AtomicBoolean targetInviteObserved = new AtomicBoolean();
        AtomicBoolean targetAckObserved = new AtomicBoolean();

        try (EvidenceRecorder evidence = new EvidenceRecorder(
                    evidenceRoot, SCENARIO, CORRELATION, "live-refer-transfer");
             TransferProvider providerA = new TransferProvider(evidence);
             DatagramSocket referrer = new DatagramSocket(new InetSocketAddress(
                    InetAddress.getByName(HOST), REFERRER_PORT));
             DatagramSocket providerB = new DatagramSocket(new InetSocketAddress(
                    InetAddress.getByName(HOST), PROVIDER_B_PORT))) {

            referrer.setSoTimeout((int) TIMEOUT.toMillis());
            providerB.setSoTimeout((int) TIMEOUT.toMillis());
            providerA.start();

            Thread targetThread = new Thread(() -> {
                try {
                    runProviderB(providerB, evidence, targetInviteObserved, targetAckObserved);
                } catch (Throwable failure) {
                    targetFailure.set(failure);
                }
            }, "baudot-provider-b-raw-peer");
            targetThread.setDaemon(true);
            targetThread.start();

            String initialInvite = initialInvite();
            sendRaw(referrer, PROVIDER_A_PORT, initialInvite, evidence, "original-invite.request.sip");
            RawPacket initialFinal = receiveFinalResponse(
                    referrer, 1, Request.INVITE, evidence, "original-invite");
            require(initialFinal.message().statusCode() == Response.OK,
                    "original dialog did not receive 200 OK");
            require(PROVIDER_A_TAG.equals(initialFinal.message().toTag()),
                    "original 200 did not preserve expected provider-a To tag");

            sendRaw(referrer, PROVIDER_A_PORT, originalAck(), evidence, "original-ack.request.sip");
            require(providerA.awaitInitialAck(TIMEOUT), "provider-a did not observe original ACK");

            String refer = referRequest();
            sendRaw(referrer, PROVIDER_A_PORT, refer, evidence, "refer.request.sip");

            boolean referAccepted = false;
            boolean progressNotifyObserved = false;
            boolean finalNotifyObserved = false;
            boolean finalNotifyTerminated = false;
            boolean oldByeObserved = false;
            int referrerOrdinal = 0;
            long deadline = System.nanoTime() + Duration.ofSeconds(20).toNanos();

            while (System.nanoTime() < deadline
                    && !(referAccepted && finalNotifyObserved && oldByeObserved)) {
                RawPacket packet = receiveRaw(referrer);
                RawSip message = packet.message();
                referrerOrdinal++;
                evidence.writeBytes(
                        "referrer-wire-" + referrerOrdinal + ".sip",
                        packet.raw().getBytes(StandardCharsets.UTF_8));

                if (message.isResponse()) {
                    if (message.cseqNumber() == 2
                            && Request.REFER.equals(message.cseqMethod())
                            && is2xx(message.statusCode())) {
                        referAccepted = true;
                        evidence.event("refer.response.observed", Map.of(
                                "status", Integer.toString(message.statusCode()),
                                "cseq", "2"));
                    }
                    continue;
                }

                if (Request.NOTIFY.equals(message.method())) {
                    int sipfragStatus = message.sipfragStatus();
                    String subscriptionState = message.header("subscription-state");
                    String event = message.header("event");
                    evidence.event("refer.notify.observed", Map.of(
                            "sipfragStatus", Integer.toString(sipfragStatus),
                            "subscriptionState", subscriptionState == null ? "missing" : subscriptionState,
                            "event", event == null ? "missing" : event));
                    String response = rawResponse(
                            message, Response.OK, "OK", null,
                            "<sip:referrer@" + HOST + ":" + REFERRER_PORT + ">");
                    sendRaw(referrer, packet.port(), response, evidence,
                            "notify-" + referrerOrdinal + "-200.response.sip");

                    if (sipfragStatus > 0 && sipfragStatus < 200) {
                        progressNotifyObserved = true;
                    }
                    if (sipfragStatus >= 200) {
                        finalNotifyObserved = true;
                        finalNotifyTerminated = subscriptionState != null
                                && subscriptionState.toLowerCase().startsWith("terminated");
                    }
                    continue;
                }

                if (Request.BYE.equals(message.method())) {
                    oldByeObserved = true;
                    String response = rawResponse(message, Response.OK, "OK", null, null);
                    sendRaw(referrer, packet.port(), response, evidence, "old-leg-bye-200.response.sip");
                    evidence.event("old_leg.bye.observed", Map.of(
                            "afterReplacementEstablished",
                            Boolean.toString(providerA.replacementEstablished())));
                }
            }

            require(providerA.awaitReplacementEstablished(TIMEOUT),
                    "replacement provider-b dialog did not establish");
            require(providerA.awaitFinalNotifyAck(TIMEOUT),
                    "final REFER NOTIFY was not acknowledged");
            require(providerA.awaitOldByeResponse(TIMEOUT),
                    "old-leg BYE did not receive a final response");

            targetThread.join(TIMEOUT.toMillis());
            if (targetFailure.get() != null) {
                throw new IllegalStateException("provider-b raw peer failed", targetFailure.get());
            }

            boolean pass = referAccepted
                    && progressNotifyObserved
                    && finalNotifyObserved
                    && finalNotifyTerminated
                    && providerA.replacementEstablished()
                    && providerA.targetCorrelated()
                    && targetInviteObserved.get()
                    && targetAckObserved.get()
                    && oldByeObserved
                    && providerA.oldByeSentAfterReplacementEstablished();

            evidence.result(Map.ofEntries(
                    Map.entry("correlation.id", CORRELATION),
                    Map.entry("provider.source", "provider-a"),
                    Map.entry("provider.target", "provider-b"),
                    Map.entry("refer.accepted", Boolean.toString(referAccepted)),
                    Map.entry("notify.progress.observed", Boolean.toString(progressNotifyObserved)),
                    Map.entry("notify.final.observed", Boolean.toString(finalNotifyObserved)),
                    Map.entry("notify.final.terminated", Boolean.toString(finalNotifyTerminated)),
                    Map.entry("replacement.dialog.established", Boolean.toString(providerA.replacementEstablished())),
                    Map.entry("replacement.target.correlated", Boolean.toString(providerA.targetCorrelated())),
                    Map.entry("replacement.target.inviteObserved", Boolean.toString(targetInviteObserved.get())),
                    Map.entry("replacement.target.ackObserved", Boolean.toString(targetAckObserved.get())),
                    Map.entry("oldLeg.bye.observed", Boolean.toString(oldByeObserved)),
                    Map.entry("oldLeg.terminatedAfterReplacementEstablished",
                            Boolean.toString(providerA.oldByeSentAfterReplacementEstablished())),
                    Map.entry("live.referNotify.proven", Boolean.toString(pass)),
                    Map.entry("live.accessibilityHandoff.proven", "false"),
                    Map.entry("rtt.readiness.proven", "false"),
                    Map.entry("scenario.id", SCENARIO),
                    Map.entry("scenario.result", pass ? "PASS" : "FAIL")));

            return pass ? 0 : 3;
        }
    }

    private static void runProviderB(
            DatagramSocket socket,
            EvidenceRecorder evidence,
            AtomicBoolean inviteObserved,
            AtomicBoolean ackObserved) throws Exception {
        int ordinal = 0;
        while (!ackObserved.get()) {
            RawPacket packet = receiveRaw(socket);
            RawSip message = packet.message();
            ordinal++;
            evidence.writeBytes(
                    "provider-b-wire-" + ordinal + ".sip",
                    packet.raw().getBytes(StandardCharsets.UTF_8));

            if (Request.INVITE.equals(message.method())) {
                inviteObserved.set(true);
                require(message.startLine().contains("sip:provider-b@" + HOST + ":" + PROVIDER_B_PORT),
                        "replacement INVITE did not target provider-b");

                String ringing = rawResponse(
                        message, Response.RINGING, "Ringing", PROVIDER_B_TAG,
                        "<sip:provider-b@" + HOST + ":" + PROVIDER_B_PORT + ">");
                sendRaw(socket, packet.port(), ringing, evidence, "provider-b-180.response.sip");
                Thread.sleep(40L);
                String ok = rawResponse(
                        message, Response.OK, "OK", PROVIDER_B_TAG,
                        "<sip:provider-b@" + HOST + ":" + PROVIDER_B_PORT + ">");
                sendRaw(socket, packet.port(), ok, evidence, "provider-b-200.response.sip");
                continue;
            }

            if (Request.ACK.equals(message.method())) {
                ackObserved.set(true);
                evidence.event("provider_b.ack.observed", Map.of(
                        "callId", String.valueOf(message.header("call-id"))));
                return;
            }

            if (Request.BYE.equals(message.method())) {
                String ok = rawResponse(message, Response.OK, "OK", null, null);
                sendRaw(socket, packet.port(), ok, evidence, "provider-b-bye-200.response.sip");
            }
        }
    }

    private static String initialInvite() {
        return "INVITE sip:provider-a@" + HOST + ":" + PROVIDER_A_PORT + " SIP/2.0\r\n"
                + "Via: SIP/2.0/UDP " + HOST + ":" + REFERRER_PORT
                + ";branch=z9hG4bK-baudot-refer-initial;rport\r\n"
                + "Max-Forwards: 70\r\n"
                + "From: <sip:referrer@" + HOST + ":" + REFERRER_PORT + ">;tag=" + REFERRER_TAG + "\r\n"
                + "To: <sip:provider-a@" + HOST + ":" + PROVIDER_A_PORT + ">\r\n"
                + "Call-ID: " + ORIGINAL_CALL_ID + "\r\n"
                + "CSeq: 1 INVITE\r\n"
                + "Contact: <sip:referrer@" + HOST + ":" + REFERRER_PORT + ">\r\n"
                + "Content-Length: 0\r\n\r\n";
    }

    private static String originalAck() {
        return "ACK sip:provider-a@" + HOST + ":" + PROVIDER_A_PORT + " SIP/2.0\r\n"
                + "Via: SIP/2.0/UDP " + HOST + ":" + REFERRER_PORT
                + ";branch=z9hG4bK-baudot-refer-ack;rport\r\n"
                + "Max-Forwards: 70\r\n"
                + "From: <sip:referrer@" + HOST + ":" + REFERRER_PORT + ">;tag=" + REFERRER_TAG + "\r\n"
                + "To: <sip:provider-a@" + HOST + ":" + PROVIDER_A_PORT + ">;tag=" + PROVIDER_A_TAG + "\r\n"
                + "Call-ID: " + ORIGINAL_CALL_ID + "\r\n"
                + "CSeq: 1 ACK\r\n"
                + "Content-Length: 0\r\n\r\n";
    }

    private static String referRequest() {
        return "REFER sip:provider-a@" + HOST + ":" + PROVIDER_A_PORT + " SIP/2.0\r\n"
                + "Via: SIP/2.0/UDP " + HOST + ":" + REFERRER_PORT
                + ";branch=z9hG4bK-baudot-refer-2;rport\r\n"
                + "Max-Forwards: 70\r\n"
                + "From: <sip:referrer@" + HOST + ":" + REFERRER_PORT + ">;tag=" + REFERRER_TAG + "\r\n"
                + "To: <sip:provider-a@" + HOST + ":" + PROVIDER_A_PORT + ">;tag=" + PROVIDER_A_TAG + "\r\n"
                + "Call-ID: " + ORIGINAL_CALL_ID + "\r\n"
                + "CSeq: 2 REFER\r\n"
                + "Contact: <sip:referrer@" + HOST + ":" + REFERRER_PORT + ">\r\n"
                + "Refer-To: <sip:provider-b@" + HOST + ":" + PROVIDER_B_PORT + ">\r\n"
                + "Content-Length: 0\r\n\r\n";
    }

    private static RawPacket receiveFinalResponse(
            DatagramSocket socket,
            long cseq,
            String method,
            EvidenceRecorder evidence,
            String prefix) throws Exception {
        int ordinal = 0;
        while (true) {
            RawPacket packet = receiveRaw(socket);
            ordinal++;
            evidence.writeBytes(
                    prefix + "-response-" + ordinal + ".sip",
                    packet.raw().getBytes(StandardCharsets.UTF_8));
            RawSip message = packet.message();
            if (message.isResponse()
                    && message.cseqNumber() == cseq
                    && method.equals(message.cseqMethod())
                    && message.statusCode() >= 200) {
                return packet;
            }
        }
    }

    private static RawPacket receiveRaw(DatagramSocket socket) throws Exception {
        byte[] buffer = new byte[16384];
        DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
        socket.receive(packet);
        String raw = new String(
                packet.getData(), packet.getOffset(), packet.getLength(), StandardCharsets.UTF_8);
        return new RawPacket(raw, RawSip.parse(raw), packet.getAddress(), packet.getPort());
    }

    private static void sendRaw(
            DatagramSocket socket,
            int port,
            String message,
            EvidenceRecorder evidence,
            String filename) throws Exception {
        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        evidence.writeBytes(filename, bytes);
        DatagramPacket packet = new DatagramPacket(
                bytes, bytes.length, InetAddress.getByName(HOST), port);
        socket.send(packet);
    }

    private static String rawResponse(
            RawSip request,
            int status,
            String reason,
            String toTag,
            String contact) {
        String to = request.header("to");
        if (toTag != null && to != null && !to.toLowerCase().contains(";tag=")) {
            to = to + ";tag=" + toTag;
        }
        StringBuilder response = new StringBuilder();
        response.append("SIP/2.0 ").append(status).append(' ').append(reason).append("\r\n");
        appendHeader(response, "Via", request.header("via"));
        appendHeader(response, "From", request.header("from"));
        appendHeader(response, "To", to);
        appendHeader(response, "Call-ID", request.header("call-id"));
        appendHeader(response, "CSeq", request.header("cseq"));
        if (contact != null) {
            appendHeader(response, "Contact", contact);
        }
        response.append("Content-Length: 0\r\n\r\n");
        return response.toString();
    }

    private static void appendHeader(StringBuilder builder, String name, String value) {
        if (value != null) {
            builder.append(name).append(": ").append(value).append("\r\n");
        }
    }

    private static boolean is2xx(int status) {
        return status >= 200 && status < 300;
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

    private record RawPacket(String raw, RawSip message, InetAddress address, int port) {
    }

    private static final class RawSip {
        private final String startLine;
        private final Map<String, String> headers;
        private final String body;

        private RawSip(String startLine, Map<String, String> headers, String body) {
            this.startLine = startLine;
            this.headers = headers;
            this.body = body;
        }

        static RawSip parse(String raw) {
            String[] parts = raw.split("\\r\\n\\r\\n", 2);
            String[] lines = parts[0].split("\\r\\n");
            Map<String, String> headers = new LinkedHashMap<>();
            for (int i = 1; i < lines.length; i++) {
                int colon = lines[i].indexOf(':');
                if (colon > 0) {
                    headers.putIfAbsent(
                            lines[i].substring(0, colon).trim().toLowerCase(),
                            lines[i].substring(colon + 1).trim());
                }
            }
            return new RawSip(lines[0], headers, parts.length == 2 ? parts[1] : "");
        }

        String startLine() {
            return startLine;
        }

        boolean isResponse() {
            return startLine.startsWith("SIP/2.0 ");
        }

        String method() {
            if (isResponse()) {
                return null;
            }
            int space = startLine.indexOf(' ');
            return space > 0 ? startLine.substring(0, space) : startLine;
        }

        int statusCode() {
            if (!isResponse()) {
                return -1;
            }
            String[] tokens = startLine.split(" ", 3);
            return Integer.parseInt(tokens[1]);
        }

        String header(String name) {
            return headers.get(name.toLowerCase());
        }

        long cseqNumber() {
            String cseq = header("cseq");
            if (cseq == null) {
                return -1;
            }
            String[] tokens = cseq.split("\\s+", 2);
            return Long.parseLong(tokens[0]);
        }

        String cseqMethod() {
            String cseq = header("cseq");
            if (cseq == null) {
                return null;
            }
            String[] tokens = cseq.split("\\s+", 2);
            return tokens.length == 2 ? tokens[1] : null;
        }

        String toTag() {
            String to = header("to");
            if (to == null) {
                return null;
            }
            String lower = to.toLowerCase();
            int tag = lower.indexOf(";tag=");
            if (tag < 0) {
                return null;
            }
            String value = to.substring(tag + 5);
            int semicolon = value.indexOf(';');
            return semicolon >= 0 ? value.substring(0, semicolon) : value;
        }

        int sipfragStatus() {
            String trimmed = body.trim();
            if (!trimmed.startsWith("SIP/2.0 ")) {
                return -1;
            }
            String[] tokens = trimmed.split("\\s+", 3);
            return tokens.length >= 2 ? Integer.parseInt(tokens[1]) : -1;
        }
    }

    private static final class TransferProvider implements SipListener, AutoCloseable {
        private final EvidenceRecorder evidence;
        private final SipStack stack;
        private final SipProvider provider;
        private final AddressFactory addresses;
        private final HeaderFactory headers;
        private final MessageFactory messages;
        private final CountDownLatch initialAck = new CountDownLatch(1);
        private final CountDownLatch replacementEstablished = new CountDownLatch(1);
        private final CountDownLatch finalNotifyAck = new CountDownLatch(1);
        private final CountDownLatch oldByeResponse = new CountDownLatch(1);
        private final AtomicBoolean targetCorrelated = new AtomicBoolean();
        private final AtomicBoolean oldByeSentAfterReplacementEstablished = new AtomicBoolean();
        private final AtomicInteger requestOrdinal = new AtomicInteger();
        private final AtomicInteger responseOrdinal = new AtomicInteger();

        private volatile Dialog originalDialog;
        private volatile Dialog replacementDialog;
        private volatile ClientTransaction finalNotifyTransaction;
        private volatile long referCseq = -1;
        private volatile boolean oldByeSent;

        TransferProvider(EvidenceRecorder evidence) throws Exception {
            this.evidence = evidence;
            SipFactory factory = SipFactory.getInstance();
            factory.setPathName("gov.nist");
            Properties properties = new Properties();
            properties.setProperty("javax.sip.STACK_NAME", "baudot-live-refer-provider-a");
            properties.setProperty("gov.nist.javax.sip.TRACE_LEVEL", "0");
            this.stack = factory.createSipStack(properties);
            this.addresses = factory.createAddressFactory();
            this.headers = factory.createHeaderFactory();
            this.messages = factory.createMessageFactory();
            ListeningPoint point = stack.createListeningPoint(HOST, PROVIDER_A_PORT, ListeningPoint.UDP);
            this.provider = stack.createSipProvider(point);
            this.provider.addSipListener(this);
        }

        void start() throws Exception {
            stack.start();
            evidence.event("refer.provider.ready", Map.of(
                    "provider", "provider-a",
                    "bind", HOST + ":" + PROVIDER_A_PORT));
        }

        boolean awaitInitialAck(Duration timeout) throws InterruptedException {
            return initialAck.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        boolean awaitReplacementEstablished(Duration timeout) throws InterruptedException {
            return replacementEstablished.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        boolean awaitFinalNotifyAck(Duration timeout) throws InterruptedException {
            return finalNotifyAck.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        boolean awaitOldByeResponse(Duration timeout) throws InterruptedException {
            return oldByeResponse.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        boolean replacementEstablished() {
            return replacementEstablished.getCount() == 0;
        }

        boolean targetCorrelated() {
            return targetCorrelated.get();
        }

        boolean oldByeSentAfterReplacementEstablished() {
            return oldByeSentAfterReplacementEstablished.get();
        }

        @Override
        public void processRequest(RequestEvent event) {
            Request request = event.getRequest();
            int ordinal = requestOrdinal.incrementAndGet();
            try {
                evidence.writeBytes(
                        "provider-a-incoming-request-" + ordinal + ".sip",
                        request.toString().getBytes(StandardCharsets.UTF_8));
                CSeqHeader cseq = (CSeqHeader) request.getHeader(CSeqHeader.NAME);
                long sequence = cseq == null ? -1 : cseq.getSeqNumber();

                if (Request.ACK.equals(request.getMethod())) {
                    if (sequence == 1) {
                        initialAck.countDown();
                        evidence.event("refer.original.ack", Map.of("cseq", "1"));
                    }
                    return;
                }

                if (Request.INVITE.equals(request.getMethod())) {
                    handleOriginalInvite(event, request);
                    return;
                }

                if (Request.REFER.equals(request.getMethod())) {
                    handleRefer(event, request, sequence);
                }
            } catch (Exception failure) {
                evidence.event("refer.provider.request_error", Map.of(
                        "method", request.getMethod(),
                        "error", failure.toString()));
            }
        }

        private void handleOriginalInvite(RequestEvent event, Request request) throws Exception {
            ServerTransaction transaction = event.getServerTransaction();
            if (transaction == null) {
                transaction = provider.getNewServerTransaction(request);
            }
            Response ok = messages.createResponse(Response.OK, request);
            ToHeader to = (ToHeader) ok.getHeader(ToHeader.NAME);
            if (to.getTag() == null) {
                to.setTag(PROVIDER_A_TAG);
            }
            ok.addHeader(contact("provider-a", PROVIDER_A_PORT));
            evidence.writeBytes("original-invite-200.response.sip",
                    ok.toString().getBytes(StandardCharsets.UTF_8));
            transaction.sendResponse(ok);
            originalDialog = transaction.getDialog();
            evidence.event("refer.original.dialog_established", Map.of(
                    "dialog", originalDialog == null ? "none" : String.valueOf(originalDialog.getDialogId())));
        }

        private void handleRefer(RequestEvent event, Request request, long sequence) throws Exception {
            ReferToHeader referTo = (ReferToHeader) request.getHeader(ReferToHeader.NAME);
            if (referTo == null) {
                ServerTransaction transaction = event.getServerTransaction();
                if (transaction == null) {
                    transaction = provider.getNewServerTransaction(request);
                }
                Response bad = messages.createResponse(Response.BAD_REQUEST, request);
                transaction.sendResponse(bad);
                return;
            }

            referCseq = sequence;
            originalDialog = event.getDialog() == null ? originalDialog : event.getDialog();
            URI uri = referTo.getAddress().getURI();
            if (uri instanceof SipURI sipUri) {
                int port = sipUri.getPort() == -1 ? 5060 : sipUri.getPort();
                targetCorrelated.set(
                        "provider-b".equals(sipUri.getUser())
                                && HOST.equals(sipUri.getHost())
                                && port == PROVIDER_B_PORT);
            }

            ServerTransaction transaction = event.getServerTransaction();
            if (transaction == null) {
                transaction = provider.getNewServerTransaction(request);
            }
            Response accepted = messages.createResponse(202, request);
            accepted.addHeader(contact("provider-a", PROVIDER_A_PORT));
            ExpiresHeader expires = headers.createExpiresHeader(30);
            accepted.addHeader(expires);
            evidence.writeBytes("refer-202.response.sip",
                    accepted.toString().getBytes(StandardCharsets.UTF_8));
            transaction.sendResponse(accepted);
            evidence.event("refer.accepted", Map.of(
                    "status", "202",
                    "targetCorrelated", Boolean.toString(targetCorrelated.get())));

            sendNotify(Response.TRYING, "Trying", false);
            sendReplacementInvite();
        }

        private void sendReplacementInvite() throws Exception {
            SipURI requestUri = addresses.createSipURI("provider-b", HOST);
            requestUri.setPort(PROVIDER_B_PORT);
            requestUri.setTransportParam(ListeningPoint.UDP);

            SipURI fromUri = addresses.createSipURI("provider-a", HOST);
            fromUri.setPort(PROVIDER_A_PORT);
            Address fromAddress = addresses.createAddress(fromUri);
            FromHeader from = headers.createFromHeader(fromAddress, "baudot-provider-a-transfer");

            Address toAddress = addresses.createAddress(requestUri);
            ToHeader to = headers.createToHeader(toAddress, null);

            ArrayList<ViaHeader> vias = new ArrayList<>();
            vias.add(headers.createViaHeader(HOST, PROVIDER_A_PORT, ListeningPoint.UDP, null));
            CallIdHeader callId = provider.getNewCallId();
            CSeqHeader cseq = headers.createCSeqHeader(1L, Request.INVITE);
            MaxForwardsHeader maxForwards = headers.createMaxForwardsHeader(70);

            Request invite = messages.createRequest(
                    requestUri, Request.INVITE, callId, cseq, from, to, vias, maxForwards);
            invite.addHeader(contact("provider-a", PROVIDER_A_PORT));
            ClientTransaction transaction = provider.getNewClientTransaction(invite);
            evidence.writeBytes("replacement-invite.request.sip",
                    invite.toString().getBytes(StandardCharsets.UTF_8));
            transaction.sendRequest();
            evidence.event("refer.replacement.invite_sent", Map.of(
                    "target", requestUri.toString(),
                    "targetCorrelated", Boolean.toString(targetCorrelated.get())));
        }

        private void sendNotify(int status, String reason, boolean terminal) throws Exception {
            require(originalDialog != null, "original dialog unavailable for NOTIFY");
            Request notify = originalDialog.createRequest(Request.NOTIFY);
            EventHeader event = headers.createEventHeader("refer");
            if (referCseq >= 0) {
                event.setEventId(Long.toString(referCseq));
            }
            notify.setHeader(event);

            String state = terminal
                    ? SubscriptionStateHeader.TERMINATED
                    : status > 100 ? SubscriptionStateHeader.ACTIVE : SubscriptionStateHeader.PENDING;
            SubscriptionStateHeader subscription = headers.createSubscriptionStateHeader(state);
            if (terminal) {
                subscription.setReasonCode("noresource");
            }
            notify.setHeader(subscription);
            notify.setHeader(contact("provider-a", PROVIDER_A_PORT));

            ContentTypeHeader contentType = headers.createContentTypeHeader("message", "sipfrag");
            contentType.setParameter("version", "2.0");
            notify.setContent("SIP/2.0 " + status + " " + reason + "\r\n", contentType);
            ClientTransaction transaction = provider.getNewClientTransaction(notify);
            if (terminal) {
                finalNotifyTransaction = transaction;
            }
            evidence.writeBytes("notify-" + status + ".request.sip",
                    notify.toString().getBytes(StandardCharsets.UTF_8));
            originalDialog.sendRequest(transaction);
            evidence.event("refer.notify.sent", Map.of(
                    "sipfragStatus", Integer.toString(status),
                    "subscriptionState", state));
        }

        private synchronized void sendOldBye() throws Exception {
            if (oldByeSent) {
                return;
            }
            oldByeSent = true;
            boolean afterReplacement = replacementEstablished();
            oldByeSentAfterReplacementEstablished.set(afterReplacement);
            Request bye = originalDialog.createRequest(Request.BYE);
            ClientTransaction transaction = provider.getNewClientTransaction(bye);
            evidence.writeBytes("old-leg-bye.request.sip",
                    bye.toString().getBytes(StandardCharsets.UTF_8));
            originalDialog.sendRequest(transaction);
            evidence.event("old_leg.bye.sent", Map.of(
                    "afterReplacementEstablished", Boolean.toString(afterReplacement)));
        }

        @Override
        public void processResponse(ResponseEvent event) {
            Response response = event.getResponse();
            int ordinal = responseOrdinal.incrementAndGet();
            try {
                evidence.writeBytes(
                        "provider-a-incoming-response-" + ordinal + ".sip",
                        response.toString().getBytes(StandardCharsets.UTF_8));
                CSeqHeader cseq = (CSeqHeader) response.getHeader(CSeqHeader.NAME);
                if (cseq == null) {
                    return;
                }

                if (Request.INVITE.equals(cseq.getMethod())) {
                    int status = response.getStatusCode();
                    if (status > 100 && status < 200) {
                        sendNotify(status, response.getReasonPhrase(), false);
                    } else if (is2xx(status)) {
                        replacementDialog = event.getDialog() != null
                                ? event.getDialog()
                                : event.getClientTransaction().getDialog();
                        require(replacementDialog != null, "replacement dialog missing after 2xx");
                        Request ack = replacementDialog.createAck(cseq.getSeqNumber());
                        evidence.writeBytes("replacement-ack.request.sip",
                                ack.toString().getBytes(StandardCharsets.UTF_8));
                        replacementDialog.sendAck(ack);
                        replacementEstablished.countDown();
                        evidence.event("refer.replacement.established", Map.of(
                                "status", Integer.toString(status),
                                "dialog", String.valueOf(replacementDialog.getDialogId())));
                        sendNotify(status, response.getReasonPhrase(), true);
                    }
                    return;
                }

                if (Request.NOTIFY.equals(cseq.getMethod())
                        && finalNotifyTransaction != null
                        && event.getClientTransaction() == finalNotifyTransaction
                        && is2xx(response.getStatusCode())) {
                    finalNotifyAck.countDown();
                    evidence.event("refer.final_notify.acknowledged", Map.of(
                            "status", Integer.toString(response.getStatusCode())));
                    sendOldBye();
                    return;
                }

                if (Request.BYE.equals(cseq.getMethod()) && is2xx(response.getStatusCode())) {
                    oldByeResponse.countDown();
                    evidence.event("old_leg.bye.completed", Map.of(
                            "status", Integer.toString(response.getStatusCode())));
                }
            } catch (Exception failure) {
                evidence.event("refer.provider.response_error", Map.of(
                        "status", Integer.toString(response.getStatusCode()),
                        "error", failure.toString()));
            }
        }

        private ContactHeader contact(String user, int port) throws Exception {
            SipURI uri = addresses.createSipURI(user, HOST);
            uri.setPort(port);
            uri.setTransportParam(ListeningPoint.UDP);
            Address address = addresses.createAddress(uri);
            return headers.createContactHeader(address);
        }

        @Override
        public void processTimeout(TimeoutEvent event) {
            evidence.event("refer.timeout", Map.of(
                    "server", Boolean.toString(event.isServerTransaction())));
        }

        @Override
        public void processIOException(IOExceptionEvent event) {
            evidence.event("refer.io_error", Map.of(
                    "host", String.valueOf(event.getHost()),
                    "port", Integer.toString(event.getPort()),
                    "transport", String.valueOf(event.getTransport())));
        }

        @Override
        public void processTransactionTerminated(TransactionTerminatedEvent event) {
            evidence.event("refer.transaction.terminated", Map.of(
                    "server", Boolean.toString(event.isServerTransaction())));
        }

        @Override
        public void processDialogTerminated(DialogTerminatedEvent event) {
            evidence.event("refer.dialog.terminated", Map.of(
                    "dialog", String.valueOf(event.getDialog().getDialogId())));
        }

        @Override
        public void close() {
            try {
                stack.stop();
            } catch (Exception failure) {
                evidence.event("refer.stop_error", Map.of("error", failure.toString()));
            }
        }
    }
}
