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
 * First cross-implementation BAUDOT-INTEROP-004 gate.
 *
 * <p>JAIN SIP owns the original dialog, REFER transaction, implicit NOTIFY
 * subscription and replacement INVITE.  The replacement target is an external,
 * independently admitted Elixip UAS.  Elixip answers with text/t140 SDP but the
 * Baudot-owned signaling-only scenario deliberately emits no T.140 packet.</p>
 *
 * <p>The gate passes only when signaling succeeds, the bounded RTT observation
 * window completes without a datagram, and the original leg is preserved.  It
 * therefore proves the negative half of Baudot's accessibility-handoff
 * invariant across two implementations without treating either implementation's
 * self-reported success as the terminal verdict.</p>
 */
public final class ElixipReferSignalingOnlyProbe {
    private static final String SCENARIO = "BAUDOT-INTEROP-004";
    private static final String CORRELATION = "jain-to-elixip-signaling-only-v1";
    private static final String HOST = "127.0.0.1";
    private static final int PROVIDER_A_PORT = 5260;
    private static final int REFERRER_PORT = 5261;
    private static final int MEDIA_PORT = 42610;
    private static final int T140_PT = 98;
    private static final Duration SIP_TIMEOUT = Duration.ofSeconds(5);
    private static final Duration RTT_WINDOW = Duration.ofMillis(1500);

    private ElixipReferSignalingOnlyProbe() {
    }

    public static void main(String[] args) {
        int exit = 2;
        try {
            String targetHost = env("BAUDOT_ELIXIP_SIP_HOST", HOST);
            int targetPort = Integer.parseInt(env("BAUDOT_ELIXIP_SIP_PORT", "5262"));
            Path root = Path.of(env("BAUDOT_EVIDENCE_DIR", "target/evidence-external"));
            boolean pass = run(root, targetHost, targetPort);
            exit = pass ? 0 : 3;
        } catch (Throwable failure) {
            failure.printStackTrace(System.err);
        }
        System.exit(exit);
    }

    private static boolean run(Path root, String targetHost, int targetPort) throws Exception {
        try (EvidenceRecorder evidence = new EvidenceRecorder(
                     root, SCENARIO, CORRELATION, "jain-to-elixip-signaling-only");
             MediaReceiver media = new MediaReceiver(evidence);
             TransferProvider providerA = new TransferProvider(
                     evidence, media, targetHost, targetPort);
             DatagramSocket referrer = new DatagramSocket(new InetSocketAddress(
                     InetAddress.getByName(HOST), REFERRER_PORT))) {

            referrer.setSoTimeout((int) SIP_TIMEOUT.toMillis());
            providerA.start();

            sendRaw(referrer, PROVIDER_A_PORT, initialInvite(), evidence,
                    "original-invite.request.sip");
            RawPacket initialFinal = receiveFinalResponse(
                    referrer, 1, Request.INVITE, evidence, "original-invite");
            require(initialFinal.message().statusCode() == Response.OK,
                    "original dialog did not receive 200");
            sendRaw(referrer, PROVIDER_A_PORT, originalAck(), evidence,
                    "original-ack.request.sip");
            require(providerA.awaitInitialAck(SIP_TIMEOUT), "original ACK missing");

            sendRaw(referrer, PROVIDER_A_PORT, referRequest(targetHost, targetPort), evidence,
                    "refer.request.sip");

            boolean referAccepted = false;
            boolean finalNotifyObserved = false;
            boolean terminalSubscriptionObserved = false;
            boolean oldByeObserved = false;
            int ordinal = 0;
            long deadline = System.nanoTime() + Duration.ofSeconds(15).toNanos();

            while (System.nanoTime() < deadline && !finalNotifyObserved) {
                RawPacket packet = receiveRaw(referrer);
                RawSip message = packet.message();
                ordinal++;
                evidence.writeBytes(
                        "referrer-wire-" + ordinal + ".sip",
                        packet.raw().getBytes(StandardCharsets.UTF_8));

                if (message.isResponse()) {
                    if (message.cseqNumber() == 2
                            && Request.REFER.equals(message.cseqMethod())
                            && is2xx(message.statusCode())) {
                        referAccepted = true;
                    }
                    continue;
                }

                if (Request.NOTIFY.equals(message.method())) {
                    int sipfragStatus = message.sipfragStatus();
                    if (sipfragStatus >= 200) {
                        finalNotifyObserved = true;
                        String subscription = message.header("subscription-state");
                        terminalSubscriptionObserved = subscription != null
                                && subscription.toLowerCase().startsWith("terminated");
                    }
                    String response = rawResponse(message, Response.OK, "OK", null, null, null, null);
                    sendRaw(referrer, packet.port(), response, evidence,
                            "notify-" + ordinal + "-200.response.sip");
                    continue;
                }

                if (Request.BYE.equals(message.method())) {
                    oldByeObserved = true;
                    String response = rawResponse(message, Response.OK, "OK", null, null, null, null);
                    sendRaw(referrer, packet.port(), response, evidence,
                            "unexpected-old-leg-bye-200.response.sip");
                }
            }

            require(referAccepted, "REFER was not accepted");
            require(finalNotifyObserved, "terminal NOTIFY missing");
            require(terminalSubscriptionObserved, "terminal NOTIFY missing terminated Subscription-State");
            require(providerA.awaitReplacementEstablished(SIP_TIMEOUT),
                    "replacement dialog did not establish");
            require(providerA.awaitFinalNotifyAck(SIP_TIMEOUT),
                    "terminal NOTIFY was not acknowledged");
            require(media.await(Duration.ofSeconds(3)),
                    "bounded RTT observation window did not complete");

            // Keep observing the original leg briefly after the no-packet window.
            referrer.setSoTimeout(250);
            long quietDeadline = System.nanoTime() + Duration.ofMillis(600).toNanos();
            while (System.nanoTime() < quietDeadline) {
                try {
                    RawPacket packet = receiveRaw(referrer);
                    RawSip message = packet.message();
                    ordinal++;
                    evidence.writeBytes(
                            "referrer-post-window-" + ordinal + ".sip",
                            packet.raw().getBytes(StandardCharsets.UTF_8));
                    if (Request.BYE.equals(message.method())) {
                        oldByeObserved = true;
                        String response = rawResponse(message, Response.OK, "OK", null, null, null, null);
                        sendRaw(referrer, packet.port(), response, evidence,
                                "unexpected-old-leg-post-window-bye-200.response.sip");
                    } else if (Request.NOTIFY.equals(message.method())) {
                        String response = rawResponse(message, Response.OK, "OK", null, null, null, null);
                        sendRaw(referrer, packet.port(), response, evidence,
                                "post-window-notify-200.response.sip");
                    }
                } catch (SocketTimeoutException expected) {
                    // Continue until the entire post-window observation period is quiet.
                }
            }

            boolean pass = providerA.replacementEstablished()
                    && providerA.targetCorrelated()
                    && providerA.rttNegotiated()
                    && media.observationCompleted()
                    && !media.datagramObserved()
                    && !providerA.oldByeSent()
                    && !oldByeObserved;

            evidence.result(Map.ofEntries(
                    Map.entry("scenario.id", SCENARIO),
                    Map.entry("correlation.id", CORRELATION),
                    Map.entry("arm.id", "signaling-only"),
                    Map.entry("provider.source", "provider-a"),
                    Map.entry("provider.sourceImplementation", "JAIN-SIP"),
                    Map.entry("provider.target", "provider-b"),
                    Map.entry("provider.targetImplementation", "Elixip"),
                    Map.entry("refer.accepted", Boolean.toString(referAccepted)),
                    Map.entry("notify.final.observed", Boolean.toString(finalNotifyObserved)),
                    Map.entry("notify.final.subscriptionTerminated", Boolean.toString(terminalSubscriptionObserved)),
                    Map.entry("replacement.dialog.established", Boolean.toString(providerA.replacementEstablished())),
                    Map.entry("replacement.target.correlated", Boolean.toString(providerA.targetCorrelated())),
                    Map.entry("rtt.negotiated", Boolean.toString(providerA.rttNegotiated())),
                    Map.entry("rtt.observationWindow.complete", Boolean.toString(media.observationCompleted())),
                    Map.entry("rtt.datagram.observed", Boolean.toString(media.datagramObserved())),
                    Map.entry("oldLeg.bye.sent", Boolean.toString(providerA.oldByeSent())),
                    Map.entry("oldLeg.bye.observed", Boolean.toString(oldByeObserved)),
                    Map.entry("rttReady", "false"),
                    Map.entry("scenarioResult", pass ? "PASS" : "FAIL"),
                    Map.entry("claimBoundary",
                            "cross-implementation signaling-only negative arm; no SIP/RFC4103/T140/VRS conformance claim")));
            return pass;
        }
    }

    private static final class MediaReceiver implements AutoCloseable {
        private final EvidenceRecorder evidence;
        private final DatagramSocket socket;
        private final CountDownLatch finished = new CountDownLatch(1);
        private final AtomicBoolean started = new AtomicBoolean();
        private final AtomicBoolean observed = new AtomicBoolean();
        private final AtomicBoolean completed = new AtomicBoolean();
        private final AtomicReference<Throwable> failure = new AtomicReference<>();

        MediaReceiver(EvidenceRecorder evidence) throws Exception {
            this.evidence = evidence;
            this.socket = new DatagramSocket(new InetSocketAddress(
                    InetAddress.getByName(HOST), MEDIA_PORT));
            this.socket.setSoTimeout((int) RTT_WINDOW.toMillis());
        }

        void start() {
            if (!started.compareAndSet(false, true)) {
                return;
            }
            Thread thread = new Thread(() -> {
                try {
                    byte[] buffer = new byte[2048];
                    DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                    socket.receive(packet);
                    observed.set(true);
                    byte[] content = new byte[packet.getLength()];
                    System.arraycopy(packet.getData(), packet.getOffset(), content, 0, packet.getLength());
                    evidence.writeBytes("unexpected-rtt-datagram.bin", content);
                    evidence.event("refer.rtt.unexpected", Map.of(
                            "bytes", Integer.toString(content.length)));
                } catch (SocketTimeoutException expected) {
                    evidence.event("refer.rtt.observation_timeout", Map.of(
                            "windowMs", Long.toString(RTT_WINDOW.toMillis()),
                            "classification", "bounded-no-packet-observation"));
                } catch (Throwable throwable) {
                    failure.set(throwable);
                } finally {
                    completed.set(true);
                    finished.countDown();
                }
            }, "baudot-elixip-signaling-only-rtt-window");
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

        boolean observationCompleted() {
            return completed.get();
        }

        boolean datagramObserved() {
            return observed.get();
        }

        @Override
        public void close() {
            socket.close();
        }
    }

    private static final class TransferProvider implements SipListener, AutoCloseable {
        private final EvidenceRecorder evidence;
        private final MediaReceiver media;
        private final String targetHost;
        private final int targetPort;
        private final SipStack stack;
        private final SipProvider provider;
        private final AddressFactory addresses;
        private final HeaderFactory headers;
        private final MessageFactory messages;
        private final CountDownLatch initialAck = new CountDownLatch(1);
        private final CountDownLatch replacementEstablished = new CountDownLatch(1);
        private final CountDownLatch finalNotifyAck = new CountDownLatch(1);
        private final AtomicBoolean targetCorrelated = new AtomicBoolean();
        private final AtomicBoolean rttNegotiated = new AtomicBoolean();
        private final AtomicBoolean oldByeSent = new AtomicBoolean();

        private volatile Dialog originalDialog;
        private volatile ClientTransaction finalNotifyTransaction;
        private volatile long referCseq = -1;

        TransferProvider(
                EvidenceRecorder evidence,
                MediaReceiver media,
                String targetHost,
                int targetPort) throws Exception {
            this.evidence = evidence;
            this.media = media;
            this.targetHost = targetHost;
            this.targetPort = targetPort;
            SipFactory factory = SipFactory.getInstance();
            factory.setPathName("gov.nist");
            Properties properties = new Properties();
            properties.setProperty("javax.sip.STACK_NAME", "baudot-jain-to-elixip-refer-negative");
            properties.setProperty("gov.nist.javax.sip.TRACE_LEVEL", "0");
            this.stack = factory.createSipStack(properties);
            this.addresses = factory.createAddressFactory();
            this.headers = factory.createHeaderFactory();
            this.messages = factory.createMessageFactory();
            ListeningPoint point = stack.createListeningPoint(
                    HOST, PROVIDER_A_PORT, ListeningPoint.UDP);
            this.provider = stack.createSipProvider(point);
            this.provider.addSipListener(this);
        }

        void start() throws Exception {
            stack.start();
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

        boolean replacementEstablished() {
            return replacementEstablished.getCount() == 0;
        }

        boolean targetCorrelated() {
            return targetCorrelated.get();
        }

        boolean rttNegotiated() {
            return rttNegotiated.get();
        }

        boolean oldByeSent() {
            return oldByeSent.get();
        }

        @Override
        public void processRequest(RequestEvent event) {
            Request request = event.getRequest();
            try {
                CSeqHeader cseq = (CSeqHeader) request.getHeader(CSeqHeader.NAME);
                long sequence = cseq == null ? -1 : cseq.getSeqNumber();
                if (Request.ACK.equals(request.getMethod())) {
                    if (sequence == 1) {
                        initialAck.countDown();
                    }
                    return;
                }
                if (Request.INVITE.equals(request.getMethod())) {
                    ServerTransaction transaction = event.getServerTransaction();
                    if (transaction == null) {
                        transaction = provider.getNewServerTransaction(request);
                    }
                    Response ok = messages.createResponse(Response.OK, request);
                    ToHeader to = (ToHeader) ok.getHeader(ToHeader.NAME);
                    if (to.getTag() == null) {
                        to.setTag("baudot-provider-a-crossstack");
                    }
                    ok.addHeader(contact("provider-a", PROVIDER_A_PORT));
                    transaction.sendResponse(ok);
                    originalDialog = transaction.getDialog();
                    return;
                }
                if (Request.REFER.equals(request.getMethod())) {
                    handleRefer(event, request, sequence);
                }
            } catch (Exception failure) {
                evidence.event("crossstack.provider_request_error", Map.of(
                        "method", request.getMethod(),
                        "error", failure.toString()));
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
                targetCorrelated.set(
                        "provider-b".equals(sipUri.getUser())
                                && targetHost.equals(sipUri.getHost())
                                && port == targetPort);
            }

            ServerTransaction transaction = event.getServerTransaction();
            if (transaction == null) {
                transaction = provider.getNewServerTransaction(request);
            }
            Response accepted = messages.createResponse(202, request);
            accepted.addHeader(contact("provider-a", PROVIDER_A_PORT));
            ExpiresHeader expires = headers.createExpiresHeader(30);
            accepted.addHeader(expires);
            transaction.sendResponse(accepted);

            sendNotify(Response.TRYING, "Trying", false);
            sendReplacementInvite();
        }

        private void sendReplacementInvite() throws Exception {
            SipURI requestUri = addresses.createSipURI("provider-b", targetHost);
            requestUri.setPort(targetPort);
            requestUri.setTransportParam(ListeningPoint.UDP);
            SipURI fromUri = addresses.createSipURI("provider-a", HOST);
            fromUri.setPort(PROVIDER_A_PORT);
            Address fromAddress = addresses.createAddress(fromUri);
            FromHeader from = headers.createFromHeader(fromAddress, "baudot-transfer-crossstack");
            ToHeader to = headers.createToHeader(addresses.createAddress(requestUri), null);
            ArrayList<ViaHeader> vias = new ArrayList<>();
            vias.add(headers.createViaHeader(HOST, PROVIDER_A_PORT, ListeningPoint.UDP, null));
            CallIdHeader callId = provider.getNewCallId();
            CSeqHeader cseq = headers.createCSeqHeader(1L, Request.INVITE);
            MaxForwardsHeader max = headers.createMaxForwardsHeader(70);
            Request invite = messages.createRequest(
                    requestUri, Request.INVITE, callId, cseq, from, to, vias, max);
            invite.addHeader(contact("provider-a", PROVIDER_A_PORT));
            invite.setContent(
                    sdp(MEDIA_PORT, "provider-a-crossstack-offer"),
                    headers.createContentTypeHeader("application", "sdp"));
            evidence.writeBytes("replacement-invite.request.sip",
                    invite.toString().getBytes(StandardCharsets.UTF_8));
            media.start();
            provider.getNewClientTransaction(invite).sendRequest();
        }

        private void sendNotify(int status, String reason, boolean terminal) throws Exception {
            Request notify = originalDialog.createRequest(Request.NOTIFY);
            EventHeader referEvent = headers.createEventHeader("refer");
            referEvent.setEventId(Long.toString(referCseq));
            notify.setHeader(referEvent);
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
        }

        @Override
        public void processResponse(ResponseEvent event) {
            Response response = event.getResponse();
            try {
                CSeqHeader cseq = (CSeqHeader) response.getHeader(CSeqHeader.NAME);
                if (cseq == null) {
                    return;
                }
                if (Request.INVITE.equals(cseq.getMethod())) {
                    evidence.writeBytes(
                            "replacement-response-" + response.getStatusCode() + ".sip",
                            response.toString().getBytes(StandardCharsets.UTF_8));
                    int status = response.getStatusCode();
                    if (status > 100 && status < 200) {
                        sendNotify(status, response.getReasonPhrase(), false);
                    } else if (is2xx(status)) {
                        String body = response.getRawContent() == null
                                ? ""
                                : new String(response.getRawContent(), StandardCharsets.UTF_8);
                        rttNegotiated.set(
                                body.contains("m=text ") && body.contains("t140/1000"));
                        require(rttNegotiated.get(),
                                "Elixip replacement 2xx did not negotiate text/t140");
                        Dialog replacementDialog = event.getDialog() != null
                                ? event.getDialog()
                                : event.getClientTransaction().getDialog();
                        require(replacementDialog != null, "missing replacement dialog");
                        Request ack = replacementDialog.createAck(cseq.getSeqNumber());
                        evidence.writeBytes("replacement-ack.request.sip",
                                ack.toString().getBytes(StandardCharsets.UTF_8));
                        replacementDialog.sendAck(ack);
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
                    boolean complete = media.await(Duration.ofSeconds(3));
                    if (!complete || media.datagramObserved()) {
                        evidence.event("old_leg.preserved", Map.of(
                                "reason", "unexpected-or-incomplete RTT observation"));
                    } else {
                        evidence.event("old_leg.preserved", Map.of(
                                "reason", "replacement signaling succeeded but no T.140 arrived"));
                    }
                }
            } catch (Exception failure) {
                evidence.event("crossstack.provider_response_error", Map.of(
                        "status", Integer.toString(response.getStatusCode()),
                        "error", failure.toString()));
            }
        }

        private ContactHeader contact(String user, int port) throws Exception {
            SipURI uri = addresses.createSipURI(user, HOST);
            uri.setPort(port);
            uri.setTransportParam(ListeningPoint.UDP);
            return headers.createContactHeader(addresses.createAddress(uri));
        }

        @Override
        public void processTimeout(TimeoutEvent event) {
            evidence.event("crossstack.timeout", Map.of(
                    "server", Boolean.toString(event.isServerTransaction())));
        }

        @Override
        public void processIOException(IOExceptionEvent event) {
            evidence.event("crossstack.io_error", Map.of(
                    "host", String.valueOf(event.getHost()),
                    "port", Integer.toString(event.getPort())));
        }

        @Override
        public void processTransactionTerminated(TransactionTerminatedEvent event) {
        }

        @Override
        public void processDialogTerminated(DialogTerminatedEvent event) {
        }

        @Override
        public void close() {
            try {
                stack.stop();
            } catch (Exception ignored) {
            }
        }
    }

    private static String initialInvite() {
        return "INVITE sip:provider-a@" + HOST + ":" + PROVIDER_A_PORT + " SIP/2.0\r\n"
                + "Via: SIP/2.0/UDP " + HOST + ":" + REFERRER_PORT
                + ";branch=z9hG4bK-crossstack-initial;rport\r\n"
                + "Max-Forwards: 70\r\n"
                + "From: <sip:referrer@" + HOST + ":" + REFERRER_PORT + ">;tag=baudot-referrer-crossstack\r\n"
                + "To: <sip:provider-a@" + HOST + ":" + PROVIDER_A_PORT + ">\r\n"
                + "Call-ID: baudot-crossstack-refer@127.0.0.1\r\n"
                + "CSeq: 1 INVITE\r\n"
                + "Contact: <sip:referrer@" + HOST + ":" + REFERRER_PORT + ">\r\n"
                + "Content-Length: 0\r\n\r\n";
    }

    private static String originalAck() {
        return "ACK sip:provider-a@" + HOST + ":" + PROVIDER_A_PORT + " SIP/2.0\r\n"
                + "Via: SIP/2.0/UDP " + HOST + ":" + REFERRER_PORT
                + ";branch=z9hG4bK-crossstack-ack;rport\r\n"
                + "Max-Forwards: 70\r\n"
                + "From: <sip:referrer@" + HOST + ":" + REFERRER_PORT + ">;tag=baudot-referrer-crossstack\r\n"
                + "To: <sip:provider-a@" + HOST + ":" + PROVIDER_A_PORT + ">;tag=baudot-provider-a-crossstack\r\n"
                + "Call-ID: baudot-crossstack-refer@127.0.0.1\r\n"
                + "CSeq: 1 ACK\r\n"
                + "Content-Length: 0\r\n\r\n";
    }

    private static String referRequest(String targetHost, int targetPort) {
        return "REFER sip:provider-a@" + HOST + ":" + PROVIDER_A_PORT + " SIP/2.0\r\n"
                + "Via: SIP/2.0/UDP " + HOST + ":" + REFERRER_PORT
                + ";branch=z9hG4bK-crossstack-refer;rport\r\n"
                + "Max-Forwards: 70\r\n"
                + "From: <sip:referrer@" + HOST + ":" + REFERRER_PORT + ">;tag=baudot-referrer-crossstack\r\n"
                + "To: <sip:provider-a@" + HOST + ":" + PROVIDER_A_PORT + ">;tag=baudot-provider-a-crossstack\r\n"
                + "Call-ID: baudot-crossstack-refer@127.0.0.1\r\n"
                + "CSeq: 2 REFER\r\n"
                + "Contact: <sip:referrer@" + HOST + ":" + REFERRER_PORT + ">\r\n"
                + "Refer-To: <sip:provider-b@" + targetHost + ":" + targetPort + ">\r\n"
                + "Content-Length: 0\r\n\r\n";
    }

    private static String sdp(int port, String sessionName) {
        return "v=0\r\n"
                + "o=baudot 0 0 IN IP4 " + HOST + "\r\n"
                + "s=" + sessionName + "\r\n"
                + "c=IN IP4 " + HOST + "\r\n"
                + "t=0 0\r\n"
                + "m=text " + port + " RTP/AVP " + T140_PT + "\r\n"
                + "a=rtpmap:" + T140_PT + " t140/1000\r\n"
                + "a=sendrecv\r\n";
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
        return new RawPacket(raw, RawSip.parse(raw), packet.getPort());
    }

    private static void sendRaw(
            DatagramSocket socket,
            int port,
            String message,
            EvidenceRecorder evidence,
            String filename) throws Exception {
        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        evidence.writeBytes(filename, bytes);
        socket.send(new DatagramPacket(bytes, bytes.length, InetAddress.getByName(HOST), port));
    }

    private static String rawResponse(
            RawSip request,
            int status,
            String reason,
            String toTag,
            String contact,
            String contentType,
            String body) {
        String to = request.header("to");
        if (toTag != null && to != null && !to.toLowerCase().contains(";tag=")) {
            to += ";tag=" + toTag;
        }
        String payload = body == null ? "" : body;
        byte[] payloadBytes = payload.getBytes(StandardCharsets.UTF_8);
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
        if (contentType != null) {
            appendHeader(response, "Content-Type", contentType);
        }
        response.append("Content-Length: ").append(payloadBytes.length).append("\r\n\r\n");
        response.append(payload);
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

    private record RawPacket(String raw, RawSip message, int port) {
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
            return Integer.parseInt(startLine.split(" ", 3)[1]);
        }

        String header(String name) {
            return headers.get(name.toLowerCase());
        }

        long cseqNumber() {
            String value = header("cseq");
            if (value == null) {
                return -1;
            }
            return Long.parseLong(value.split("\\s+", 2)[0]);
        }

        String cseqMethod() {
            String value = header("cseq");
            if (value == null) {
                return null;
            }
            String[] tokens = value.split("\\s+", 2);
            return tokens.length == 2 ? tokens[1] : null;
        }

        int sipfragStatus() {
            String trimmed = body.trim();
            if (!trimmed.startsWith("SIP/2.0 ")) {
                return -1;
            }
            return Integer.parseInt(trimmed.split("\\s+", 3)[1]);
        }
    }
}
