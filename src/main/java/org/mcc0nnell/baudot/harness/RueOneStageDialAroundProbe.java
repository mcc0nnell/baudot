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
import javax.sip.header.CSeqHeader;
import javax.sip.header.CallIdHeader;
import javax.sip.header.ContactHeader;
import javax.sip.header.FromHeader;
import javax.sip.header.HeaderFactory;
import javax.sip.header.MaxForwardsHeader;
import javax.sip.header.RouteHeader;
import javax.sip.header.ToHeader;
import javax.sip.header.ViaHeader;
import javax.sip.message.MessageFactory;
import javax.sip.message.Request;
import javax.sip.message.Response;

/**
 * Live clean-room route proof for RFC 9248 one-stage dial-around semantics.
 *
 * <p>A synthetic RUE sends an INVITE physically to its synthetic default
 * provider while the Request-URI and To URI identify the called number at the
 * selected dial-around provider domain. The JAIN SIP default-provider role
 * forwards an independently constructed INVITE to a loopback provider-B peer
 * while preserving those URI semantics. Loopback transport routing is harness
 * plumbing only and is never promoted into DNS, TLS, provider, or production
 * routing conformance.</p>
 */
public final class RueOneStageDialAroundProbe {
    private static final String SCENARIO = "RUE-DIAL-001";
    private static final String CORRELATION = "jain-one-stage-dial-around-v1";
    private static final String HOST = "127.0.0.1";
    private static final int PROVIDER_A_PORT = 5140;
    private static final int RUE_PORT = 5141;
    private static final int PROVIDER_B_PORT = 5142;
    private static final Duration TIMEOUT = Duration.ofSeconds(6);

    private static final String DEFAULT_DOMAIN = "provider-a.example";
    private static final String DIAL_DOMAIN = "provider-b.example";
    private static final String RUE_NUMBER = "+12025550101";
    private static final String CALLED_NUMBER = "+12025550199";
    private static final String EXPECTED_TARGET =
            "sip:" + CALLED_NUMBER + "@" + DIAL_DOMAIN + ";user=phone";
    private static final String EXPECTED_SOURCE =
            "sip:" + RUE_NUMBER + "@" + DEFAULT_DOMAIN + ";user=phone";
    private static final String CALL_ID = "baudot-rue-dial-001@127.0.0.1";
    private static final String RUE_TAG = "baudot-rue-dial";
    private static final String PROVIDER_A_TAG = "baudot-provider-a-dial";
    private static final String PROVIDER_B_TAG = "baudot-provider-b-dial";

    private RueOneStageDialAroundProbe() {
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
        AtomicReference<Throwable> peerFailure = new AtomicReference<>();
        AtomicBoolean providerBInviteObserved = new AtomicBoolean();
        AtomicBoolean providerBTargetPreserved = new AtomicBoolean();
        AtomicBoolean providerBToPreserved = new AtomicBoolean();
        AtomicBoolean providerBSourcePreserved = new AtomicBoolean();
        AtomicBoolean providerBAckObserved = new AtomicBoolean();

        try (EvidenceRecorder evidence = new EvidenceRecorder(
                    evidenceRoot, SCENARIO, CORRELATION, "route-proof");
             DefaultProvider providerA = new DefaultProvider(evidence);
             DatagramSocket rue = new DatagramSocket(new InetSocketAddress(
                    InetAddress.getByName(HOST), RUE_PORT));
             DatagramSocket providerB = new DatagramSocket(new InetSocketAddress(
                    InetAddress.getByName(HOST), PROVIDER_B_PORT))) {

            rue.setSoTimeout((int) TIMEOUT.toMillis());
            providerB.setSoTimeout((int) TIMEOUT.toMillis());
            providerA.start();

            Thread peer = new Thread(() -> {
                try {
                    runProviderB(
                            providerB,
                            evidence,
                            providerBInviteObserved,
                            providerBTargetPreserved,
                            providerBToPreserved,
                            providerBSourcePreserved,
                            providerBAckObserved);
                } catch (Throwable failure) {
                    peerFailure.set(failure);
                }
            }, "baudot-rue-dial-provider-b");
            peer.setDaemon(true);
            peer.start();

            String invite = rueInvite();
            sendRaw(rue, PROVIDER_A_PORT, invite, evidence, "rue-invite.request.sip");

            RawPacket finalResponse = receiveFinalResponse(
                    rue, 1, Request.INVITE, evidence, "rue-invite");
            require(finalResponse.message().statusCode() == Response.OK,
                    "RUE did not receive a 200 OK from the default-provider hop");
            require(PROVIDER_A_TAG.equals(finalResponse.message().toTag()),
                    "RUE final response did not carry the expected default-provider To tag");

            sendRaw(
                    rue,
                    PROVIDER_A_PORT,
                    rueAck(PROVIDER_A_TAG),
                    evidence,
                    "rue-ack.request.sip");

            require(providerA.awaitRueAck(TIMEOUT),
                    "default provider did not observe the RUE ACK");
            require(providerA.awaitForwardedFinal(TIMEOUT),
                    "default provider did not complete the forwarded provider-B leg");

            peer.join(TIMEOUT.toMillis());
            if (peerFailure.get() != null) {
                throw new IllegalStateException("provider-B peer failed", peerFailure.get());
            }

            boolean pass = providerA.inboundTargetPreserved()
                    && providerA.inboundToPreserved()
                    && providerA.inboundSourcePreserved()
                    && providerA.forwardedTargetPreserved()
                    && providerBInviteObserved.get()
                    && providerBTargetPreserved.get()
                    && providerBToPreserved.get()
                    && providerBSourcePreserved.get()
                    && providerBAckObserved.get()
                    && providerA.rueAckObserved();

            evidence.result(Map.ofEntries(
                    Map.entry("scenario.id", SCENARIO),
                    Map.entry("correlation.id", CORRELATION),
                    Map.entry("called.number", CALLED_NUMBER),
                    Map.entry("default.provider.domain", DEFAULT_DOMAIN),
                    Map.entry("selected.provider.domain", DIAL_DOMAIN),
                    Map.entry("expected.requestUri", EXPECTED_TARGET),
                    Map.entry("rue.inboundTargetPreserved", Boolean.toString(providerA.inboundTargetPreserved())),
                    Map.entry("rue.inboundToPreserved", Boolean.toString(providerA.inboundToPreserved())),
                    Map.entry("rue.inboundSourcePreserved", Boolean.toString(providerA.inboundSourcePreserved())),
                    Map.entry("providerA.forwardedTargetPreserved", Boolean.toString(providerA.forwardedTargetPreserved())),
                    Map.entry("providerB.inviteObserved", Boolean.toString(providerBInviteObserved.get())),
                    Map.entry("providerB.targetPreserved", Boolean.toString(providerBTargetPreserved.get())),
                    Map.entry("providerB.toPreserved", Boolean.toString(providerBToPreserved.get())),
                    Map.entry("providerB.sourcePreserved", Boolean.toString(providerBSourcePreserved.get())),
                    Map.entry("providerB.ackObserved", Boolean.toString(providerBAckObserved.get())),
                    Map.entry("rue.final200Observed", "true"),
                    Map.entry("rue.ackObservedByDefaultProvider", Boolean.toString(providerA.rueAckObserved())),
                    Map.entry("dialog.established", Boolean.toString(pass)),
                    Map.entry("media.offered", "false"),
                    Map.entry("media.readiness.proven", "false"),
                    Map.entry("rtt.readiness.proven", "false"),
                    Map.entry("video.readiness.proven", "false"),
                    Map.entry("transport.claim", "loopback-udp-harness-only"),
                    Map.entry("claim", "rfc9248-one-stage-dial-around-route-semantics-only"),
                    Map.entry("scenario.result", pass ? "PASS" : "FAIL")));

            return pass ? 0 : 3;
        }
    }

    private static void runProviderB(
            DatagramSocket socket,
            EvidenceRecorder evidence,
            AtomicBoolean inviteObserved,
            AtomicBoolean targetPreserved,
            AtomicBoolean toPreserved,
            AtomicBoolean sourcePreserved,
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
                targetPreserved.set(message.startLine().equals(
                        "INVITE " + EXPECTED_TARGET + " SIP/2.0"));
                toPreserved.set(uriHeaderContains(message.header("to"), EXPECTED_TARGET));
                sourcePreserved.set(uriHeaderContains(message.header("from"), EXPECTED_SOURCE));

                evidence.event("dial.provider_b.invite", Map.of(
                        "requestUriPreserved", Boolean.toString(targetPreserved.get()),
                        "toPreserved", Boolean.toString(toPreserved.get()),
                        "sourcePreserved", Boolean.toString(sourcePreserved.get())));

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
                evidence.event("dial.provider_b.ack", Map.of("observed", "true"));
            }
        }
    }

    private static String rueInvite() {
        return "INVITE " + EXPECTED_TARGET + " SIP/2.0\r\n"
                + "Via: SIP/2.0/UDP " + HOST + ":" + RUE_PORT
                + ";branch=z9hG4bK-baudot-rue-dial-001;rport\r\n"
                + "Max-Forwards: 70\r\n"
                + "From: \"Baudot RUE\" <" + EXPECTED_SOURCE + ">;tag=" + RUE_TAG + "\r\n"
                + "To: <" + EXPECTED_TARGET + ">\r\n"
                + "Call-ID: " + CALL_ID + "\r\n"
                + "CSeq: 1 INVITE\r\n"
                + "Contact: <sip:rue@" + HOST + ":" + RUE_PORT + ">\r\n"
                + "Content-Length: 0\r\n\r\n";
    }

    private static String rueAck(String toTag) {
        return "ACK " + EXPECTED_TARGET + " SIP/2.0\r\n"
                + "Via: SIP/2.0/UDP " + HOST + ":" + RUE_PORT
                + ";branch=z9hG4bK-baudot-rue-dial-ack;rport\r\n"
                + "Max-Forwards: 70\r\n"
                + "From: \"Baudot RUE\" <" + EXPECTED_SOURCE + ">;tag=" + RUE_TAG + "\r\n"
                + "To: <" + EXPECTED_TARGET + ">;tag=" + toTag + "\r\n"
                + "Call-ID: " + CALL_ID + "\r\n"
                + "CSeq: 1 ACK\r\n"
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

    private static boolean uriHeaderContains(String header, String uri) {
        return header != null && header.contains("<" + uri + ">");
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

        private RawSip(String startLine, Map<String, String> headers) {
            this.startLine = startLine;
            this.headers = headers;
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
            return new RawSip(lines[0], headers);
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
    }

    private static final class DefaultProvider implements SipListener, AutoCloseable {
        private final EvidenceRecorder evidence;
        private final SipStack stack;
        private final SipProvider provider;
        private final AddressFactory addresses;
        private final HeaderFactory headers;
        private final MessageFactory messages;
        private final CountDownLatch rueAck = new CountDownLatch(1);
        private final CountDownLatch forwardedFinal = new CountDownLatch(1);
        private final AtomicBoolean inboundTargetPreserved = new AtomicBoolean();
        private final AtomicBoolean inboundToPreserved = new AtomicBoolean();
        private final AtomicBoolean inboundSourcePreserved = new AtomicBoolean();
        private final AtomicBoolean forwardedTargetPreserved = new AtomicBoolean();
        private final AtomicBoolean rueFinalSent = new AtomicBoolean();

        private volatile Request inboundInvite;
        private volatile ServerTransaction inboundServerTransaction;
        private volatile ClientTransaction forwardTransaction;

        DefaultProvider(EvidenceRecorder evidence) throws Exception {
            this.evidence = evidence;
            SipFactory factory = SipFactory.getInstance();
            factory.setPathName("gov.nist");
            Properties properties = new Properties();
            properties.setProperty("javax.sip.STACK_NAME", "baudot-rue-dial-provider-a");
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
            evidence.event("dial.provider_a.ready", Map.of(
                    "bind", HOST + ":" + PROVIDER_A_PORT,
                    "role", "synthetic-default-provider"));
        }

        boolean awaitRueAck(Duration timeout) throws InterruptedException {
            return rueAck.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        boolean awaitForwardedFinal(Duration timeout) throws InterruptedException {
            return forwardedFinal.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        boolean rueAckObserved() {
            return rueAck.getCount() == 0;
        }

        boolean inboundTargetPreserved() {
            return inboundTargetPreserved.get();
        }

        boolean inboundToPreserved() {
            return inboundToPreserved.get();
        }

        boolean inboundSourcePreserved() {
            return inboundSourcePreserved.get();
        }

        boolean forwardedTargetPreserved() {
            return forwardedTargetPreserved.get();
        }

        @Override
        public void processRequest(RequestEvent event) {
            Request request = event.getRequest();
            try {
                evidence.writeBytes(
                        "provider-a-incoming-" + request.getMethod().toLowerCase() + ".sip",
                        request.toString().getBytes(StandardCharsets.UTF_8));

                if (Request.ACK.equals(request.getMethod())) {
                    rueAck.countDown();
                    evidence.event("dial.rue.ack", Map.of("observed", "true"));
                    return;
                }

                if (!Request.INVITE.equals(request.getMethod())) {
                    return;
                }

                inboundInvite = request;
                inboundServerTransaction = event.getServerTransaction();
                if (inboundServerTransaction == null) {
                    inboundServerTransaction = provider.getNewServerTransaction(request);
                }

                FromHeader from = (FromHeader) request.getHeader(FromHeader.NAME);
                ToHeader to = (ToHeader) request.getHeader(ToHeader.NAME);
                inboundTargetPreserved.set(EXPECTED_TARGET.equals(request.getRequestURI().toString()));
                inboundToPreserved.set(to != null
                        && EXPECTED_TARGET.equals(to.getAddress().getURI().toString()));
                inboundSourcePreserved.set(from != null
                        && EXPECTED_SOURCE.equals(from.getAddress().getURI().toString()));
                require(request.getRawContent() == null || request.getRawContent().length == 0,
                        "RUE-DIAL-001 must remain signaling-only");

                evidence.event("dial.provider_a.received", Map.of(
                        "requestUriPreserved", Boolean.toString(inboundTargetPreserved.get()),
                        "toPreserved", Boolean.toString(inboundToPreserved.get()),
                        "sourcePreserved", Boolean.toString(inboundSourcePreserved.get())));

                Response trying = messages.createResponse(Response.TRYING, request);
                inboundServerTransaction.sendResponse(trying);
                forwardToProviderB(request, from, to);
            } catch (Throwable failure) {
                throw new IllegalStateException("default-provider request processing failed", failure);
            }
        }

        private void forwardToProviderB(Request original, FromHeader originalFrom, ToHeader originalTo)
                throws Exception {
            ArrayList<ViaHeader> vias = new ArrayList<>();
            vias.add(headers.createViaHeader(
                    HOST,
                    PROVIDER_A_PORT,
                    ListeningPoint.UDP,
                    "z9hG4bK-baudot-rue-dial-forward"));

            CallIdHeader inboundCallId = (CallIdHeader) original.getHeader(CallIdHeader.NAME);
            CallIdHeader callId = headers.createCallIdHeader(inboundCallId.getCallId());
            CSeqHeader cseq = headers.createCSeqHeader(1L, Request.INVITE);
            FromHeader from = headers.createFromHeader(
                    (Address) originalFrom.getAddress().clone(), originalFrom.getTag());
            ToHeader to = headers.createToHeader((Address) originalTo.getAddress().clone(), null);
            MaxForwardsHeader maxForwards = headers.createMaxForwardsHeader(69);

            Request forwarded = messages.createRequest(
                    addresses.createURI(EXPECTED_TARGET),
                    Request.INVITE,
                    callId,
                    cseq,
                    from,
                    to,
                    vias,
                    maxForwards);

            Address contactAddress = addresses.createAddress(
                    "<sip:provider-a@" + HOST + ":" + PROVIDER_A_PORT + ">");
            ContactHeader contact = headers.createContactHeader(contactAddress);
            forwarded.addHeader(contact);

            SipURI routeUri = addresses.createSipURI(null, HOST);
            routeUri.setPort(PROVIDER_B_PORT);
            routeUri.setLrParam();
            RouteHeader route = headers.createRouteHeader(addresses.createAddress(routeUri));
            forwarded.addHeader(route);

            forwardedTargetPreserved.set(EXPECTED_TARGET.equals(forwarded.getRequestURI().toString()));
            evidence.writeBytes(
                    "provider-a-forwarded-invite.sip",
                    forwarded.toString().getBytes(StandardCharsets.UTF_8));
            evidence.event("dial.provider_a.forward", Map.of(
                    "requestUriPreserved", Boolean.toString(forwardedTargetPreserved.get()),
                    "transportRoute", HOST + ":" + PROVIDER_B_PORT,
                    "transportRouteAuthority", "harness-only"));

            forwardTransaction = provider.getNewClientTransaction(forwarded);
            forwardTransaction.sendRequest();
        }

        @Override
        public void processResponse(ResponseEvent event) {
            Response response = event.getResponse();
            try {
                CSeqHeader cseq = (CSeqHeader) response.getHeader(CSeqHeader.NAME);
                if (cseq == null || !Request.INVITE.equals(cseq.getMethod())) {
                    return;
                }

                evidence.writeBytes(
                        "provider-a-provider-b-response-" + response.getStatusCode() + ".sip",
                        response.toString().getBytes(StandardCharsets.UTF_8));

                if (response.getStatusCode() == Response.RINGING && inboundServerTransaction != null) {
                    Response ringing = messages.createResponse(Response.RINGING, inboundInvite);
                    ToHeader to = (ToHeader) ringing.getHeader(ToHeader.NAME);
                    to.setTag(PROVIDER_A_TAG);
                    inboundServerTransaction.sendResponse(ringing);
                    return;
                }

                if (response.getStatusCode() < 200 || response.getStatusCode() >= 300) {
                    return;
                }

                Dialog dialog = event.getDialog();
                if (dialog == null && forwardTransaction != null) {
                    dialog = forwardTransaction.getDialog();
                }
                require(dialog != null, "forwarded provider-B dialog was not created");
                Request ack = dialog.createAck(cseq.getSeqNumber());
                evidence.writeBytes(
                        "provider-a-to-provider-b-ack.sip",
                        ack.toString().getBytes(StandardCharsets.UTF_8));
                dialog.sendAck(ack);

                if (rueFinalSent.compareAndSet(false, true)) {
                    Response ok = messages.createResponse(Response.OK, inboundInvite);
                    ToHeader to = (ToHeader) ok.getHeader(ToHeader.NAME);
                    to.setTag(PROVIDER_A_TAG);
                    Address contactAddress = addresses.createAddress(
                            "<sip:provider-a@" + HOST + ":" + PROVIDER_A_PORT + ">");
                    ok.addHeader(headers.createContactHeader(contactAddress));
                    inboundServerTransaction.sendResponse(ok);
                    forwardedFinal.countDown();
                    evidence.event("dial.provider_a.final", Map.of(
                            "providerBDialogEstablished", "true",
                            "rueFinalSent", "true"));
                }
            } catch (Throwable failure) {
                throw new IllegalStateException("default-provider response processing failed", failure);
            }
        }

        @Override
        public void processTimeout(TimeoutEvent event) {
            throw new IllegalStateException("RUE-DIAL-001 SIP transaction timed out");
        }

        @Override
        public void processIOException(IOExceptionEvent event) {
            throw new IllegalStateException("RUE-DIAL-001 SIP IO error: " + event);
        }

        @Override
        public void processTransactionTerminated(TransactionTerminatedEvent event) {
            // Evidence is transaction-specific; terminal readiness is reduced by run().
        }

        @Override
        public void processDialogTerminated(DialogTerminatedEvent event) {
            // No teardown semantics are claimed by this route-only lane.
        }

        @Override
        public void close() {
            try {
                provider.removeSipListener(this);
            } catch (Throwable ignored) {
                // Best-effort cleanup only.
            }
            stack.stop();
        }
    }
}
