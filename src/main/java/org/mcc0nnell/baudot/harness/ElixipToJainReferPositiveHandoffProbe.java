package org.mcc0nnell.baudot.harness;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
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
import javax.sip.address.AddressFactory;
import javax.sip.address.SipURI;
import javax.sip.address.URI;
import javax.sip.header.CSeqHeader;
import javax.sip.header.CallIdHeader;
import javax.sip.header.ContactHeader;
import javax.sip.header.ContentTypeHeader;
import javax.sip.header.EventHeader;
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

/** Reverse-direction positive BAUDOT-INTEROP-004 accessibility-handoff gate. */
public final class ElixipToJainReferPositiveHandoffProbe {
    private static final String SCENARIO = "BAUDOT-INTEROP-004";
    private static final String CORRELATION = "elixip-to-jain-positive-handoff-v1";
    private static final String ROLE = "elixip-to-jain-positive-handoff";
    private static final String HOST = "127.0.0.1";
    private static final int PROVIDER_A_PORT = 5290;
    private static final int PROVIDER_B_PORT = 5293;
    private static final int MEDIA_PORT = 42650;
    private static final int PROVIDER_B_MEDIA_PORT = 42651;
    private static final int T140_PT = 98;
    private static final Duration SIP_TIMEOUT = Duration.ofSeconds(12);
    private static final Duration RTT_WINDOW = Duration.ofMillis(2500);

    private ElixipToJainReferPositiveHandoffProbe() {
    }

    public static void main(String[] args) {
        int exit = 2;
        try {
            Path root = Path.of(env("BAUDOT_EVIDENCE_DIR", "target/evidence-external"));
            boolean pass = run(root);
            exit = pass ? 0 : 3;
        } catch (Throwable failure) {
            failure.printStackTrace(System.err);
        }
        System.exit(exit);
    }

    private static boolean run(Path root) throws Exception {
        try (EvidenceRecorder evidence = new EvidenceRecorder(root, SCENARIO, CORRELATION, ROLE);
             MediaReceiver media = new MediaReceiver(evidence);
             TransferProcessor providerA = new TransferProcessor(evidence, media);
             DatagramSocket providerB = new DatagramSocket(new InetSocketAddress(
                     InetAddress.getByName(HOST), PROVIDER_B_PORT))) {

            providerB.setSoTimeout((int) SIP_TIMEOUT.toMillis());
            AtomicBoolean targetInviteObserved = new AtomicBoolean();
            AtomicBoolean targetAckObserved = new AtomicBoolean();
            AtomicReference<Throwable> targetFailure = new AtomicReference<>();
            Thread targetThread = new Thread(() -> {
                try {
                    runProviderB(providerB, evidence, targetInviteObserved, targetAckObserved);
                } catch (Throwable failure) {
                    targetFailure.set(failure);
                }
            }, "baudot-reverse-positive-provider-b");
            targetThread.setDaemon(true);
            targetThread.start();

            providerA.start();
            System.out.println("BAUDOT-JAIN reversePositiveServerReady=true sipPort=" + PROVIDER_A_PORT);

            require(providerA.awaitInitialAck(SIP_TIMEOUT), "Elixip original ACK missing");
            require(providerA.awaitReferReceived(SIP_TIMEOUT), "Elixip REFER missing");
            require(providerA.awaitReplacementEstablished(SIP_TIMEOUT),
                    "replacement dialog did not establish");
            require(providerA.awaitFinalNotifyAck(SIP_TIMEOUT),
                    "terminal NOTIFY was not acknowledged by Elixip");
            require(media.await(Duration.ofSeconds(4)), "positive RTT observation did not complete");
            require(media.datagramObserved(), "replacement RTT datagram was not observed");
            require(media.canonicalBytesMatched(), "replacement RTT bytes were not canonical");
            require(providerA.awaitOldByeResponse(SIP_TIMEOUT),
                    "original-leg BYE did not receive 2xx from Elixip");

            targetThread.join(SIP_TIMEOUT.toMillis());
            if (targetFailure.get() != null) {
                throw new IllegalStateException("controlled provider-b failed", targetFailure.get());
            }

            boolean pass = providerA.referReceived()
                    && providerA.targetCorrelated()
                    && providerA.replacementEstablished()
                    && providerA.rttNegotiated()
                    && targetInviteObserved.get()
                    && targetAckObserved.get()
                    && media.datagramObserved()
                    && media.canonicalBytesMatched()
                    && providerA.oldByeSent()
                    && providerA.oldByeCompleted()
                    && providerA.oldByeAfterRttObservation();

            evidence.result(Map.ofEntries(
                    Map.entry("scenario.id", SCENARIO),
                    Map.entry("correlation.id", CORRELATION),
                    Map.entry("arm.id", "positive"),
                    Map.entry("provider.sourceImplementation", "Elixip"),
                    Map.entry("provider.transferImplementation", "JAIN-SIP"),
                    Map.entry("original.dialog.ackObserved", Boolean.toString(providerA.initialAckObserved())),
                    Map.entry("refer.observed", Boolean.toString(providerA.referReceived())),
                    Map.entry("refer.target.correlated", Boolean.toString(providerA.targetCorrelated())),
                    Map.entry("notify.final.acknowledged", Boolean.toString(providerA.finalNotifyAcknowledged())),
                    Map.entry("replacement.dialog.established", Boolean.toString(providerA.replacementEstablished())),
                    Map.entry("replacement.target.inviteObserved", Boolean.toString(targetInviteObserved.get())),
                    Map.entry("replacement.target.ackObserved", Boolean.toString(targetAckObserved.get())),
                    Map.entry("rtt.negotiated", Boolean.toString(providerA.rttNegotiated())),
                    Map.entry("rtt.datagram.observed", Boolean.toString(media.datagramObserved())),
                    Map.entry("rtt.canonicalBytesMatched", Boolean.toString(media.canonicalBytesMatched())),
                    Map.entry("firstT140CharacterObserved", "UNCLASSIFIED_BY_JAVA"),
                    Map.entry("rttReady", "UNCLASSIFIED_BY_JAVA"),
                    Map.entry("oldLeg.bye.sent", Boolean.toString(providerA.oldByeSent())),
                    Map.entry("oldLeg.bye.completed", Boolean.toString(providerA.oldByeCompleted())),
                    Map.entry("oldLeg.bye.afterRttObservation", Boolean.toString(providerA.oldByeAfterRttObservation())),
                    Map.entry("scenarioResult", pass ? "PASS" : "FAIL"),
                    Map.entry("claimBoundary",
                            "Elixip-originated REFER into JAIN transfer processor plus Baudot-owned canonical replacement RTT stimulus; no SIP/RFC4103/T140/VRS conformance claim")));
            return pass;
        }
    }

    private static final class MediaReceiver implements AutoCloseable {
        private final EvidenceRecorder evidence;
        private final DatagramSocket socket;
        private final CountDownLatch finished = new CountDownLatch(1);
        private final AtomicBoolean observed = new AtomicBoolean();
        private final AtomicBoolean canonical = new AtomicBoolean();
        private final AtomicLong observedAtNanos = new AtomicLong(-1L);
        private final AtomicReference<Throwable> failure = new AtomicReference<>();

        MediaReceiver(EvidenceRecorder evidence) throws Exception {
            this.evidence = evidence;
            this.socket = new DatagramSocket(new InetSocketAddress(InetAddress.getByName(HOST), MEDIA_PORT));
            this.socket.setSoTimeout((int) RTT_WINDOW.toMillis());
        }

        void start() {
            Thread thread = new Thread(() -> {
                try {
                    byte[] buffer = new byte[2048];
                    DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                    socket.receive(packet);
                    byte[] content = Arrays.copyOfRange(
                            packet.getData(), packet.getOffset(), packet.getOffset() + packet.getLength());
                    observedAtNanos.set(System.nanoTime());
                    observed.set(true);
                    canonical.set(Arrays.equals(content, RttSipProbe.normalPrimaryPacket()));
                    evidence.writeBytes("rtt-datagram-received.bin", content);
                    evidence.event("refer.rtt.observed", Map.of(
                            "bytes", Integer.toString(content.length),
                            "canonicalBytesMatched", Boolean.toString(canonical.get()),
                            "classification", "byte-match-only"));
                } catch (SocketTimeoutException timeout) {
                    evidence.event("refer.rtt.observation_timeout", Map.of(
                            "windowMs", Long.toString(RTT_WINDOW.toMillis()),
                            "classification", "positive-packet-not-observed"));
                } catch (Throwable throwable) {
                    failure.set(throwable);
                } finally {
                    finished.countDown();
                }
            }, "baudot-reverse-positive-rtt-window");
            thread.setDaemon(true);
            thread.start();
        }

        boolean await(Duration timeout) throws Exception {
            boolean done = finished.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
            if (failure.get() != null) {
                throw new IllegalStateException("RTT receiver failed", failure.get());
            }
            return done;
        }

        boolean datagramObserved() { return observed.get(); }
        boolean canonicalBytesMatched() { return canonical.get(); }
        long observedAtNanos() { return observedAtNanos.get(); }

        @Override
        public void close() { socket.close(); }
    }

    private static final class TransferProcessor implements SipListener, AutoCloseable {
        private final EvidenceRecorder evidence;
        private final MediaReceiver media;
        private final SipStack stack;
        private final SipProvider provider;
        private final AddressFactory addresses;
        private final HeaderFactory headers;
        private final MessageFactory messages;
        private final CountDownLatch initialAck = new CountDownLatch(1);
        private final CountDownLatch referReceived = new CountDownLatch(1);
        private final CountDownLatch replacementEstablished = new CountDownLatch(1);
        private final CountDownLatch finalNotifyAck = new CountDownLatch(1);
        private final CountDownLatch oldByeResponse = new CountDownLatch(1);
        private final AtomicBoolean targetCorrelated = new AtomicBoolean();
        private final AtomicBoolean rttNegotiated = new AtomicBoolean();
        private final AtomicBoolean oldByeSent = new AtomicBoolean();
        private final AtomicBoolean oldByeCompleted = new AtomicBoolean();
        private final AtomicBoolean oldByeAfterRtt = new AtomicBoolean();

        private volatile Dialog originalDialog;
        private volatile ClientTransaction finalNotifyTransaction;
        private volatile long referCseq = -1;

        TransferProcessor(EvidenceRecorder evidence, MediaReceiver media) throws Exception {
            this.evidence = evidence;
            this.media = media;
            SipFactory factory = SipFactory.getInstance();
            factory.setPathName("gov.nist");
            Properties properties = new Properties();
            properties.setProperty("javax.sip.STACK_NAME", "baudot-elixip-to-jain-positive");
            properties.setProperty("gov.nist.javax.sip.TRACE_LEVEL", "0");
            this.stack = factory.createSipStack(properties);
            this.addresses = factory.createAddressFactory();
            this.headers = factory.createHeaderFactory();
            this.messages = factory.createMessageFactory();
            ListeningPoint point = stack.createListeningPoint(HOST, PROVIDER_A_PORT, ListeningPoint.UDP);
            this.provider = stack.createSipProvider(point);
            this.provider.addSipListener(this);
        }

        void start() throws Exception { stack.start(); }
        boolean awaitInitialAck(Duration t) throws InterruptedException { return initialAck.await(t.toMillis(), TimeUnit.MILLISECONDS); }
        boolean awaitReferReceived(Duration t) throws InterruptedException { return referReceived.await(t.toMillis(), TimeUnit.MILLISECONDS); }
        boolean awaitReplacementEstablished(Duration t) throws InterruptedException { return replacementEstablished.await(t.toMillis(), TimeUnit.MILLISECONDS); }
        boolean awaitFinalNotifyAck(Duration t) throws InterruptedException { return finalNotifyAck.await(t.toMillis(), TimeUnit.MILLISECONDS); }
        boolean awaitOldByeResponse(Duration t) throws InterruptedException { return oldByeResponse.await(t.toMillis(), TimeUnit.MILLISECONDS); }
        boolean initialAckObserved() { return initialAck.getCount() == 0; }
        boolean referReceived() { return referReceived.getCount() == 0; }
        boolean replacementEstablished() { return replacementEstablished.getCount() == 0; }
        boolean finalNotifyAcknowledged() { return finalNotifyAck.getCount() == 0; }
        boolean targetCorrelated() { return targetCorrelated.get(); }
        boolean rttNegotiated() { return rttNegotiated.get(); }
        boolean oldByeSent() { return oldByeSent.get(); }
        boolean oldByeCompleted() { return oldByeCompleted.get(); }
        boolean oldByeAfterRttObservation() { return oldByeAfterRtt.get(); }

        @Override
        public void processRequest(RequestEvent event) {
            Request request = event.getRequest();
            try {
                CSeqHeader cseq = (CSeqHeader) request.getHeader(CSeqHeader.NAME);
                long sequence = cseq == null ? -1 : cseq.getSeqNumber();
                if (Request.INVITE.equals(request.getMethod())) {
                    evidence.writeBytes("original-invite.request.sip", request.toString().getBytes(StandardCharsets.UTF_8));
                    ServerTransaction tx = event.getServerTransaction();
                    if (tx == null) tx = provider.getNewServerTransaction(request);
                    Response ok = messages.createResponse(Response.OK, request);
                    ToHeader to = (ToHeader) ok.getHeader(ToHeader.NAME);
                    if (to.getTag() == null) to.setTag("baudot-jain-reverse-positive-provider-a");
                    ok.addHeader(contact("provider-a", PROVIDER_A_PORT));
                    evidence.writeBytes("original-invite-200.response.sip", ok.toString().getBytes(StandardCharsets.UTF_8));
                    tx.sendResponse(ok);
                    originalDialog = tx.getDialog();
                    return;
                }
                if (Request.ACK.equals(request.getMethod())) {
                    initialAck.countDown();
                    evidence.writeBytes("original-ack.request.sip", request.toString().getBytes(StandardCharsets.UTF_8));
                    return;
                }
                if (Request.REFER.equals(request.getMethod())) {
                    evidence.writeBytes("refer.request.sip", request.toString().getBytes(StandardCharsets.UTF_8));
                    handleRefer(event, request, sequence);
                }
            } catch (Exception failure) {
                evidence.event("reverse_positive.provider_request_error", Map.of(
                        "method", request.getMethod(), "error", failure.toString()));
            }
        }

        private void handleRefer(RequestEvent event, Request request, long sequence) throws Exception {
            ReferToHeader referTo = (ReferToHeader) request.getHeader(ReferToHeader.NAME);
            require(referTo != null, "REFER missing Refer-To");
            referCseq = sequence;
            originalDialog = event.getDialog() == null ? originalDialog : event.getDialog();
            URI uri = referTo.getAddress().getURI();
            if (uri instanceof SipURI sipUri) {
                int port = sipUri.getPort() == -1 ? 5060 : sipUri.getPort();
                targetCorrelated.set("provider-b".equals(sipUri.getUser())
                        && HOST.equals(sipUri.getHost()) && port == PROVIDER_B_PORT);
            }
            ServerTransaction tx = event.getServerTransaction();
            if (tx == null) tx = provider.getNewServerTransaction(request);
            Response accepted = messages.createResponse(202, request);
            accepted.addHeader(contact("provider-a", PROVIDER_A_PORT));
            accepted.addHeader(headers.createExpiresHeader(30));
            evidence.writeBytes("refer-202.response.sip", accepted.toString().getBytes(StandardCharsets.UTF_8));
            tx.sendResponse(accepted);
            referReceived.countDown();
            sendNotify(Response.TRYING, "Trying", false);
            sendReplacementInvite();
        }

        private void sendReplacementInvite() throws Exception {
            SipURI requestUri = addresses.createSipURI("provider-b", HOST);
            requestUri.setPort(PROVIDER_B_PORT);
            requestUri.setTransportParam(ListeningPoint.UDP);
            SipURI fromUri = addresses.createSipURI("provider-a", HOST);
            fromUri.setPort(PROVIDER_A_PORT);
            FromHeader from = headers.createFromHeader(
                    addresses.createAddress(fromUri), "baudot-jain-reverse-positive-transfer");
            ToHeader to = headers.createToHeader(addresses.createAddress(requestUri), null);
            ArrayList<ViaHeader> vias = new ArrayList<>();
            vias.add(headers.createViaHeader(HOST, PROVIDER_A_PORT, ListeningPoint.UDP, null));
            CallIdHeader callId = provider.getNewCallId();
            CSeqHeader cseq = headers.createCSeqHeader(1L, Request.INVITE);
            MaxForwardsHeader max = headers.createMaxForwardsHeader(70);
            Request invite = messages.createRequest(requestUri, Request.INVITE, callId, cseq, from, to, vias, max);
            invite.addHeader(contact("provider-a", PROVIDER_A_PORT));
            invite.setContent(sdp(MEDIA_PORT, "baudot-reverse-positive-replacement-offer"),
                    headers.createContentTypeHeader("application", "sdp"));
            evidence.writeBytes("replacement-invite.request.sip", invite.toString().getBytes(StandardCharsets.UTF_8));
            media.start();
            provider.getNewClientTransaction(invite).sendRequest();
        }

        private void sendNotify(int status, String reason, boolean terminal) throws Exception {
            require(originalDialog != null, "original dialog unavailable for NOTIFY");
            Request notify = originalDialog.createRequest(Request.NOTIFY);
            EventHeader event = headers.createEventHeader("refer");
            event.setEventId(Long.toString(referCseq));
            notify.setHeader(event);
            String state = terminal ? SubscriptionStateHeader.TERMINATED
                    : status > 100 ? SubscriptionStateHeader.ACTIVE : SubscriptionStateHeader.PENDING;
            SubscriptionStateHeader subscription = headers.createSubscriptionStateHeader(state);
            if (terminal) subscription.setReasonCode("noresource");
            notify.setHeader(subscription);
            notify.setHeader(contact("provider-a", PROVIDER_A_PORT));
            ContentTypeHeader contentType = headers.createContentTypeHeader("message", "sipfrag");
            contentType.setParameter("version", "2.0");
            notify.setContent("SIP/2.0 " + status + " " + reason + "\r\n", contentType);
            ClientTransaction tx = provider.getNewClientTransaction(notify);
            if (terminal) finalNotifyTransaction = tx;
            evidence.writeBytes("notify-" + status + ".request.sip", notify.toString().getBytes(StandardCharsets.UTF_8));
            originalDialog.sendRequest(tx);
        }

        private synchronized void sendOldBye() throws Exception {
            if (!oldByeSent.compareAndSet(false, true)) return;
            oldByeAfterRtt.set(media.observedAtNanos() > 0 && media.canonicalBytesMatched());
            Request bye = originalDialog.createRequest(Request.BYE);
            ClientTransaction tx = provider.getNewClientTransaction(bye);
            evidence.writeBytes("old-leg-bye-sent.request.sip", bye.toString().getBytes(StandardCharsets.UTF_8));
            originalDialog.sendRequest(tx);
            evidence.event("old_leg.bye.sent", Map.of(
                    "afterCanonicalRttObservation", Boolean.toString(oldByeAfterRtt.get())));
        }

        @Override
        public void processResponse(ResponseEvent event) {
            Response response = event.getResponse();
            try {
                CSeqHeader cseq = (CSeqHeader) response.getHeader(CSeqHeader.NAME);
                if (cseq == null) return;
                if (Request.INVITE.equals(cseq.getMethod())) {
                    evidence.writeBytes("replacement-response-" + response.getStatusCode() + ".sip",
                            response.toString().getBytes(StandardCharsets.UTF_8));
                    int status = response.getStatusCode();
                    if (status > 100 && status < 200) {
                        sendNotify(status, response.getReasonPhrase(), false);
                    } else if (is2xx(status)) {
                        String body = response.getRawContent() == null ? ""
                                : new String(response.getRawContent(), StandardCharsets.UTF_8);
                        rttNegotiated.set(body.contains("m=text ")
                                && body.toLowerCase().contains("t140/1000"));
                        require(rttNegotiated.get(), "replacement 2xx did not negotiate text/t140");
                        Dialog replacement = event.getDialog() != null
                                ? event.getDialog() : event.getClientTransaction().getDialog();
                        require(replacement != null, "missing replacement dialog");
                        Request ack = replacement.createAck(cseq.getSeqNumber());
                        evidence.writeBytes("replacement-ack.request.sip", ack.toString().getBytes(StandardCharsets.UTF_8));
                        replacement.sendAck(ack);
                        replacementEstablished.countDown();
                        sendNotify(status, response.getReasonPhrase(), true);
                    }
                    return;
                }
                if (Request.NOTIFY.equals(cseq.getMethod())
                        && finalNotifyTransaction != null
                        && event.getClientTransaction() == finalNotifyTransaction
                        && is2xx(response.getStatusCode())) {
                    finalNotifyAck.countDown();
                    boolean complete = media.await(Duration.ofSeconds(4));
                    if (complete && media.datagramObserved() && media.canonicalBytesMatched()) {
                        sendOldBye();
                    } else {
                        evidence.event("old_leg.preserved", Map.of(
                                "reason", "canonical replacement RTT readiness not observed"));
                    }
                    return;
                }
                if (Request.BYE.equals(cseq.getMethod()) && is2xx(response.getStatusCode())) {
                    oldByeCompleted.set(true);
                    oldByeResponse.countDown();
                    evidence.writeBytes("old-leg-bye-200.response.sip",
                            response.toString().getBytes(StandardCharsets.UTF_8));
                    evidence.event("old_leg.bye.completed", Map.of(
                            "status", Integer.toString(response.getStatusCode())));
                }
            } catch (Exception failure) {
                evidence.event("reverse_positive.provider_response_error", Map.of(
                        "status", Integer.toString(response.getStatusCode()), "error", failure.toString()));
            }
        }

        private ContactHeader contact(String user, int port) throws Exception {
            SipURI uri = addresses.createSipURI(user, HOST);
            uri.setPort(port);
            uri.setTransportParam(ListeningPoint.UDP);
            return headers.createContactHeader(addresses.createAddress(uri));
        }

        @Override public void processTimeout(TimeoutEvent event) { evidence.event("reverse_positive.timeout", Map.of("server", Boolean.toString(event.isServerTransaction()))); }
        @Override public void processIOException(IOExceptionEvent event) { evidence.event("reverse_positive.io_error", Map.of("host", String.valueOf(event.getHost()), "port", Integer.toString(event.getPort()))); }
        @Override public void processTransactionTerminated(TransactionTerminatedEvent event) { }
        @Override public void processDialogTerminated(DialogTerminatedEvent event) { }
        @Override public void close() { try { stack.stop(); } catch (Exception ignored) { } }
    }

    private static void runProviderB(
            DatagramSocket socket,
            EvidenceRecorder evidence,
            AtomicBoolean inviteObserved,
            AtomicBoolean ackObserved) throws Exception {
        int ordinal = 0;
        int offerPort = -1;
        while (!ackObserved.get()) {
            RawPacket packet = receiveRaw(socket);
            RawSip message = packet.message();
            ordinal++;
            evidence.writeBytes("provider-b-wire-" + ordinal + ".sip",
                    packet.raw().getBytes(StandardCharsets.UTF_8));
            if (Request.INVITE.equals(message.method())) {
                inviteObserved.set(true);
                offerPort = textMediaPort(message.body());
                require(offerPort == MEDIA_PORT, "replacement offer did not advertise expected m=text port");
                require(message.body().toLowerCase().contains("t140/1000"),
                        "replacement offer did not negotiate text/t140");
                sendRaw(socket, packet.port(), rawResponse(message, Response.RINGING, "Ringing",
                                "baudot-provider-b-reverse-positive",
                                "<sip:provider-b@" + HOST + ":" + PROVIDER_B_PORT + ">", null, null),
                        evidence, "provider-b-180.response.sip");
                String answer = sdp(PROVIDER_B_MEDIA_PORT, "baudot-reverse-positive-provider-b-answer");
                sendRaw(socket, packet.port(), rawResponse(message, Response.OK, "OK",
                                "baudot-provider-b-reverse-positive",
                                "<sip:provider-b@" + HOST + ":" + PROVIDER_B_PORT + ">",
                                "application/sdp", answer),
                        evidence, "provider-b-200.response.sip");
                continue;
            }
            if (Request.ACK.equals(message.method())) {
                ackObserved.set(true);
                evidence.event("provider_b.ack.observed", Map.of("direction", "elixip-to-jain-positive"));
                require(offerPort > 0, "missing negotiated RTT target port");
                byte[] packetBytes = RttSipProbe.normalPrimaryPacket();
                evidence.writeBytes("rtt-datagram-sent.bin", packetBytes);
                DatagramPacket rtt = new DatagramPacket(packetBytes, packetBytes.length,
                        InetAddress.getByName(HOST), offerPort);
                socket.send(rtt);
                evidence.event("provider_b.rtt.sent", Map.of(
                        "target", HOST + ":" + offerPort,
                        "bytes", Integer.toString(packetBytes.length),
                        "classification", "canonical-bytes-unparsed"));
            }
        }
    }

    private static int textMediaPort(String sdp) {
        for (String line : sdp.split("\\r?\\n")) {
            if (line.startsWith("m=text ")) {
                String[] parts = line.trim().split("\\s+");
                if (parts.length >= 2) return Integer.parseInt(parts[1]);
            }
        }
        return -1;
    }

    private static String sdp(int port, String sessionName) {
        return "v=0\r\n" + "o=baudot 0 0 IN IP4 " + HOST + "\r\n"
                + "s=" + sessionName + "\r\n" + "c=IN IP4 " + HOST + "\r\n"
                + "t=0 0\r\n" + "m=text " + port + " RTP/AVP " + T140_PT + "\r\n"
                + "a=rtpmap:" + T140_PT + " t140/1000\r\n" + "a=sendrecv\r\n";
    }

    private static RawPacket receiveRaw(DatagramSocket socket) throws Exception {
        byte[] buffer = new byte[16384];
        DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
        socket.receive(packet);
        String raw = new String(packet.getData(), packet.getOffset(), packet.getLength(), StandardCharsets.UTF_8);
        return new RawPacket(raw, RawSip.parse(raw), packet.getPort());
    }

    private static void sendRaw(DatagramSocket socket, int port, String message,
            EvidenceRecorder evidence, String filename) throws Exception {
        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        evidence.writeBytes(filename, bytes);
        socket.send(new DatagramPacket(bytes, bytes.length, InetAddress.getByName(HOST), port));
    }

    private static String rawResponse(RawSip request, int status, String reason,
            String toTag, String contact, String contentType, String body) {
        String to = request.header("to");
        if (toTag != null && to != null && !to.toLowerCase().contains(";tag=")) to += ";tag=" + toTag;
        String payload = body == null ? "" : body;
        byte[] payloadBytes = payload.getBytes(StandardCharsets.UTF_8);
        StringBuilder response = new StringBuilder();
        response.append("SIP/2.0 ").append(status).append(' ').append(reason).append("\r\n");
        appendHeader(response, "Via", request.header("via"));
        appendHeader(response, "From", request.header("from"));
        appendHeader(response, "To", to);
        appendHeader(response, "Call-ID", request.header("call-id"));
        appendHeader(response, "CSeq", request.header("cseq"));
        if (contact != null) appendHeader(response, "Contact", contact);
        if (contentType != null) appendHeader(response, "Content-Type", contentType);
        response.append("Content-Length: ").append(payloadBytes.length).append("\r\n\r\n");
        response.append(payload);
        return response.toString();
    }

    private static void appendHeader(StringBuilder builder, String name, String value) {
        if (value != null) builder.append(name).append(": ").append(value).append("\r\n");
    }
    private static boolean is2xx(int status) { return status >= 200 && status < 300; }
    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }
    private static void require(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }

    private record RawPacket(String raw, RawSip message, int port) { }

    private static final class RawSip {
        private final String startLine;
        private final Map<String, String> headers;
        private final String body;
        private RawSip(String startLine, Map<String, String> headers, String body) {
            this.startLine = startLine; this.headers = headers; this.body = body;
        }
        static RawSip parse(String raw) {
            String[] parts = raw.split("\\r\\n\\r\\n", 2);
            String[] lines = parts[0].split("\\r\\n");
            Map<String, String> headers = new LinkedHashMap<>();
            for (int i = 1; i < lines.length; i++) {
                int colon = lines[i].indexOf(':');
                if (colon > 0) headers.putIfAbsent(lines[i].substring(0, colon).trim().toLowerCase(),
                        lines[i].substring(colon + 1).trim());
            }
            return new RawSip(lines[0], headers, parts.length == 2 ? parts[1] : "");
        }
        String method() {
            if (startLine.startsWith("SIP/2.0 ")) return null;
            int space = startLine.indexOf(' ');
            return space > 0 ? startLine.substring(0, space) : startLine;
        }
        String header(String name) { return headers.get(name.toLowerCase()); }
        String body() { return body; }
    }
}
