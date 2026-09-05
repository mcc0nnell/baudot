package org.mcc0nnell.baudot.harness;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

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
 * Native-media positive BAUDOT-INTEROP-004 handoff gate.
 *
 * <p>JAIN SIP owns the original dialog, REFER/NOTIFY, and replacement INVITE.
 * PJSIP/PJMEDIA 2.17 owns the replacement UAS and native text transmission.
 * A separate Baudot Python reference process owns the offered m=text UDP port
 * and may publish an atomic readiness token only after independently accepting
 * the implementation-generated RTP/T.140 bytes.</p>
 *
 * <p>This Java harness never parses the token or the media. It treats exact
 * token presence as opaque authority evidence and releases the original leg
 * only after that token is observed.</p>
 */
public final class PjsipReferNativeHandoffProbe {
    private static final String SCENARIO = "BAUDOT-INTEROP-004";
    private static final String CORRELATION = "jain-to-pjsip-native-handoff-v1";
    private static final String ROLE = "jain-to-pjsip-native-handoff";
    private static final String HOST = "127.0.0.1";
    private static final int DEFAULT_PROVIDER_A_PORT = 5310;
    private static final int DEFAULT_REFERRER_PORT = 5311;
    private static final int DEFAULT_TARGET_PORT = 5312;
    private static final int DEFAULT_MEDIA_PORT = 5313;
    private static final int T140_PT = 98;
    private static final Duration SIP_TIMEOUT = Duration.ofSeconds(8);
    private static final Duration READINESS_TIMEOUT = Duration.ofSeconds(8);

    private PjsipReferNativeHandoffProbe() {
    }

    public static void main(String[] args) {
        int exit = 2;
        try {
            int providerPort = envInt("BAUDOT_JAIN_TRANSFER_PORT", DEFAULT_PROVIDER_A_PORT);
            int referrerPort = envInt("BAUDOT_JAIN_REFERRER_PORT", DEFAULT_REFERRER_PORT);
            String targetHost = env("BAUDOT_PJSIP_SIP_HOST", HOST);
            int targetPort = envInt("BAUDOT_PJSIP_UAS_PORT", DEFAULT_TARGET_PORT);
            int mediaPort = envInt("BAUDOT_PJSIP_HANDOFF_MEDIA_PORT", DEFAULT_MEDIA_PORT);
            Path root = Path.of(env("BAUDOT_EVIDENCE_DIR", "target/evidence-external"));
            Path readyFile = Path.of(env(
                    "BAUDOT_RTT_READY_FILE",
                    root.resolve(SCENARIO).resolve(CORRELATION)
                            .resolve("readiness/rtt-ready.json").toString()));
            boolean pass = run(
                    root, readyFile, providerPort, referrerPort,
                    targetHost, targetPort, mediaPort);
            exit = pass ? 0 : 3;
        } catch (Throwable failure) {
            failure.printStackTrace(System.err);
        }
        System.exit(exit);
    }

    private static boolean run(
            Path root,
            Path readyFile,
            int providerPort,
            int referrerPort,
            String targetHost,
            int targetPort,
            int mediaPort) throws Exception {
        try (EvidenceRecorder evidence = new EvidenceRecorder(root, SCENARIO, CORRELATION, ROLE);
             ReadinessToken readiness = new ReadinessToken(evidence, readyFile);
             TransferProvider providerA = new TransferProvider(
                     evidence, readiness, providerPort, targetHost, targetPort, mediaPort);
             DatagramSocket referrer = new DatagramSocket(new InetSocketAddress(
                     InetAddress.getByName(HOST), referrerPort))) {

            referrer.setSoTimeout((int) SIP_TIMEOUT.toMillis());
            providerA.start();

            sendRaw(referrer, providerPort, initialInvite(providerPort, referrerPort), evidence,
                    "original-invite.request.sip");
            RawPacket initialFinal = receiveFinalResponse(
                    referrer, 1, Request.INVITE, evidence, "original-invite");
            require(initialFinal.message().statusCode() == Response.OK,
                    "original dialog did not receive 200");
            sendRaw(referrer, providerPort, originalAck(providerPort, referrerPort), evidence,
                    "original-ack.request.sip");
            require(providerA.awaitInitialAck(SIP_TIMEOUT), "original ACK missing");

            sendRaw(referrer, providerPort,
                    referRequest(providerPort, referrerPort, targetHost, targetPort), evidence,
                    "refer.request.sip");

            boolean referAccepted = false;
            boolean finalNotifyObserved = false;
            boolean terminalSubscriptionObserved = false;
            boolean oldByeObserved = false;
            long oldByeObservedAt = -1L;
            int ordinal = 0;
            long deadline = System.nanoTime() + Duration.ofSeconds(18).toNanos();

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
                    oldByeObservedAt = System.nanoTime();
                    evidence.writeBytes("old-leg-bye-observed.request.sip",
                            packet.raw().getBytes(StandardCharsets.UTF_8));
                    String response = rawResponse(message, Response.OK, "OK", null, null, null, null);
                    sendRaw(referrer, packet.port(), response, evidence,
                            "old-leg-bye-200.response.sip");
                }
            }

            require(referAccepted, "REFER was not accepted");
            require(finalNotifyObserved, "terminal NOTIFY missing");
            require(terminalSubscriptionObserved,
                    "terminal NOTIFY missing terminated Subscription-State");
            require(providerA.awaitReplacementEstablished(SIP_TIMEOUT),
                    "replacement dialog did not establish");
            require(providerA.awaitFinalNotifyAck(SIP_TIMEOUT),
                    "terminal NOTIFY was not acknowledged");
            require(readiness.await(READINESS_TIMEOUT),
                    "independent RTT readiness token was not published");

            referrer.setSoTimeout((int) SIP_TIMEOUT.toMillis());
            long byeDeadline = System.nanoTime() + SIP_TIMEOUT.toNanos();
            while (!oldByeObserved && System.nanoTime() < byeDeadline) {
                RawPacket packet = receiveRaw(referrer);
                RawSip message = packet.message();
                ordinal++;
                evidence.writeBytes(
                        "referrer-post-readiness-" + ordinal + ".sip",
                        packet.raw().getBytes(StandardCharsets.UTF_8));
                if (Request.BYE.equals(message.method())) {
                    oldByeObserved = true;
                    oldByeObservedAt = System.nanoTime();
                    evidence.writeBytes("old-leg-bye-observed.request.sip",
                            packet.raw().getBytes(StandardCharsets.UTF_8));
                    String response = rawResponse(message, Response.OK, "OK", null, null, null, null);
                    sendRaw(referrer, packet.port(), response, evidence,
                            "old-leg-bye-200.response.sip");
                } else if (Request.NOTIFY.equals(message.method())) {
                    String response = rawResponse(message, Response.OK, "OK", null, null, null, null);
                    sendRaw(referrer, packet.port(), response, evidence,
                            "post-readiness-notify-200.response.sip");
                }
            }

            require(oldByeObserved,
                    "original leg was not released after independent RTT readiness");
            require(providerA.awaitOldByeResponse(SIP_TIMEOUT),
                    "old-leg BYE did not receive 2xx");

            boolean byeAfterReadiness = readiness.observedAtNanos() > 0
                    && oldByeObservedAt > readiness.observedAtNanos();
            boolean pass = providerA.replacementEstablished()
                    && providerA.targetCorrelated()
                    && providerA.rttNegotiated()
                    && readiness.observed()
                    && providerA.oldByeSent()
                    && oldByeObserved
                    && byeAfterReadiness;

            evidence.result(Map.ofEntries(
                    Map.entry("scenario.id", SCENARIO),
                    Map.entry("correlation.id", CORRELATION),
                    Map.entry("arm.id", "positive-native-pjsip"),
                    Map.entry("provider.source", "provider-a"),
                    Map.entry("provider.sourceImplementation", "JAIN-SIP"),
                    Map.entry("provider.target", "pjsip-target"),
                    Map.entry("provider.targetImplementation", "pjsip/pjproject-2.17"),
                    Map.entry("refer.accepted", Boolean.toString(referAccepted)),
                    Map.entry("notify.final.observed", Boolean.toString(finalNotifyObserved)),
                    Map.entry("notify.final.subscriptionTerminated",
                            Boolean.toString(terminalSubscriptionObserved)),
                    Map.entry("replacement.dialog.established",
                            Boolean.toString(providerA.replacementEstablished())),
                    Map.entry("replacement.target.correlated",
                            Boolean.toString(providerA.targetCorrelated())),
                    Map.entry("rtt.negotiated", Boolean.toString(providerA.rttNegotiated())),
                    Map.entry("rtt.readinessToken.observed", Boolean.toString(readiness.observed())),
                    Map.entry("firstT140CharacterObserved", "UNCLASSIFIED_BY_JAVA"),
                    Map.entry("rttReady", "EXTERNAL_BAUDOT_REFERENCE_TOKEN"),
                    Map.entry("oldLeg.bye.sent", Boolean.toString(providerA.oldByeSent())),
                    Map.entry("oldLeg.bye.observed", Boolean.toString(oldByeObserved)),
                    Map.entry("oldLeg.bye.afterReadinessToken", Boolean.toString(byeAfterReadiness)),
                    Map.entry("scenarioResult", pass ? "PASS" : "FAIL"),
                    Map.entry("claimBoundary",
                            "JAIN SIP transfer to pinned PJSIP native RTT endpoint with live Baudot reference readiness token; no SIP/RTP/RFC4103/T140/VRS conformance claim")));
            return pass;
        }
    }

    private static final class ReadinessToken implements AutoCloseable {
        private final EvidenceRecorder evidence;
        private final Path readyFile;
        private final AtomicBoolean observed = new AtomicBoolean();
        private final AtomicLong observedAtNanos = new AtomicLong(-1L);

        ReadinessToken(EvidenceRecorder evidence, Path readyFile) {
            this.evidence = evidence;
            this.readyFile = readyFile;
        }

        synchronized boolean await(Duration timeout) throws Exception {
            if (observed.get()) {
                return true;
            }
            long deadline = System.nanoTime() + timeout.toNanos();
            while (System.nanoTime() < deadline) {
                if (Files.isRegularFile(readyFile)) {
                    byte[] token = Files.readAllBytes(readyFile);
                    evidence.writeBytes("rtt-ready.token.json", token);
                    observedAtNanos.set(System.nanoTime());
                    observed.set(true);
                    evidence.event("refer.rtt.readiness_token_observed", Map.of(
                            "bytes", Integer.toString(token.length),
                            "authority", "external-baudot-reference",
                            "classification", "opaque-token-presence"));
                    return true;
                }
                Thread.sleep(25L);
            }
            evidence.event("refer.rtt.readiness_token_timeout", Map.of(
                    "timeoutMs", Long.toString(timeout.toMillis())));
            return false;
        }

        boolean observed() {
            return observed.get();
        }

        long observedAtNanos() {
            return observedAtNanos.get();
        }

        @Override
        public void close() {
        }
    }

    private static final class TransferProvider implements SipListener, AutoCloseable {
        private final EvidenceRecorder evidence;
        private final ReadinessToken readiness;
        private final int providerPort;
        private final String targetHost;
        private final int targetPort;
        private final int mediaPort;
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
        private final AtomicBoolean rttNegotiated = new AtomicBoolean();
        private final AtomicBoolean oldByeSent = new AtomicBoolean();

        private volatile Dialog originalDialog;
        private volatile ClientTransaction finalNotifyTransaction;
        private volatile long referCseq = -1;

        TransferProvider(
                EvidenceRecorder evidence,
                ReadinessToken readiness,
                int providerPort,
                String targetHost,
                int targetPort,
                int mediaPort) throws Exception {
            this.evidence = evidence;
            this.readiness = readiness;
            this.providerPort = providerPort;
            this.targetHost = targetHost;
            this.targetPort = targetPort;
            this.mediaPort = mediaPort;
            SipFactory factory = SipFactory.getInstance();
            factory.setPathName("gov.nist");
            Properties properties = new Properties();
            properties.setProperty("javax.sip.STACK_NAME", "baudot-jain-to-pjsip-refer-native");
            properties.setProperty("gov.nist.javax.sip.TRACE_LEVEL", "0");
            this.stack = factory.createSipStack(properties);
            this.addresses = factory.createAddressFactory();
            this.headers = factory.createHeaderFactory();
            this.messages = factory.createMessageFactory();
            ListeningPoint point = stack.createListeningPoint(
                    HOST, providerPort, ListeningPoint.UDP);
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

        boolean awaitOldByeResponse(Duration timeout) throws InterruptedException {
            return oldByeResponse.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
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
                        to.setTag("baudot-provider-a-pjsip-native");
                    }
                    ok.addHeader(contact("provider-a", providerPort));
                    transaction.sendResponse(ok);
                    originalDialog = transaction.getDialog();
                    return;
                }
                if (Request.REFER.equals(request.getMethod())) {
                    handleRefer(event, request, sequence);
                }
            } catch (Exception failure) {
                evidence.event("pjsip_handoff.provider_request_error", Map.of(
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
                        "pjsip-target".equals(sipUri.getUser())
                                && targetHost.equals(sipUri.getHost())
                                && port == targetPort);
            }

            ServerTransaction transaction = event.getServerTransaction();
            if (transaction == null) {
                transaction = provider.getNewServerTransaction(request);
            }
            Response accepted = messages.createResponse(202, request);
            accepted.addHeader(contact("provider-a", providerPort));
            ExpiresHeader expires = headers.createExpiresHeader(30);
            accepted.addHeader(expires);
            transaction.sendResponse(accepted);

            sendNotify(Response.TRYING, "Trying", false);
            sendReplacementInvite();
        }

        private void sendReplacementInvite() throws Exception {
            SipURI requestUri = addresses.createSipURI("pjsip-target", targetHost);
            requestUri.setPort(targetPort);
            requestUri.setTransportParam(ListeningPoint.UDP);
            SipURI fromUri = addresses.createSipURI("provider-a", HOST);
            fromUri.setPort(providerPort);
            Address fromAddress = addresses.createAddress(fromUri);
            FromHeader from = headers.createFromHeader(fromAddress, "baudot-transfer-pjsip-native");
            ToHeader to = headers.createToHeader(addresses.createAddress(requestUri), null);
            ArrayList<ViaHeader> vias = new ArrayList<>();
            vias.add(headers.createViaHeader(HOST, providerPort, ListeningPoint.UDP, null));
            CallIdHeader callId = provider.getNewCallId();
            CSeqHeader cseq = headers.createCSeqHeader(1L, Request.INVITE);
            MaxForwardsHeader max = headers.createMaxForwardsHeader(70);
            Request invite = messages.createRequest(
                    requestUri, Request.INVITE, callId, cseq, from, to, vias, max);
            invite.addHeader(contact("provider-a", providerPort));
            String offer = sdp(mediaPort, "provider-a-pjsip-native-offer");
            invite.setContent(offer, headers.createContentTypeHeader("application", "sdp"));
            evidence.writeBytes("replacement-invite.request.sip",
                    invite.toString().getBytes(StandardCharsets.UTF_8));
            evidence.writeBytes("replacement-offer.sdp", offer.getBytes(StandardCharsets.UTF_8));
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
            notify.setHeader(contact("provider-a", providerPort));
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

        private synchronized void sendOldBye() throws Exception {
            if (!oldByeSent.compareAndSet(false, true)) {
                return;
            }
            Request bye = originalDialog.createRequest(Request.BYE);
            ClientTransaction transaction = provider.getNewClientTransaction(bye);
            evidence.writeBytes("old-leg-bye-sent.request.sip",
                    bye.toString().getBytes(StandardCharsets.UTF_8));
            originalDialog.sendRequest(transaction);
            evidence.event("old_leg.bye.sent", Map.of(
                    "afterReadinessToken", Boolean.toString(readiness.observed())));
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
                        evidence.writeBytes("replacement-answer.sdp",
                                body.getBytes(StandardCharsets.UTF_8));
                        rttNegotiated.set(
                                body.contains("m=text ") && body.toLowerCase().contains("t140/1000"));
                        require(rttNegotiated.get(),
                                "PJSIP replacement 2xx did not negotiate text/t140");
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
                    if (readiness.await(READINESS_TIMEOUT)) {
                        sendOldBye();
                    } else {
                        evidence.event("old_leg.preserved", Map.of(
                                "reason", "independent replacement RTT readiness token not observed"));
                    }
                    return;
                }
                if (Request.BYE.equals(cseq.getMethod()) && is2xx(response.getStatusCode())) {
                    oldByeResponse.countDown();
                    evidence.event("old_leg.bye.completed", Map.of(
                            "status", Integer.toString(response.getStatusCode())));
                }
            } catch (Exception failure) {
                evidence.event("pjsip_handoff.provider_response_error", Map.of(
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
            evidence.event("pjsip_handoff.timeout", Map.of(
                    "server", Boolean.toString(event.isServerTransaction())));
        }

        @Override
        public void processIOException(IOExceptionEvent event) {
            evidence.event("pjsip_handoff.io_error", Map.of(
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

    private static String initialInvite(int providerPort, int referrerPort) {
        return "INVITE sip:provider-a@" + HOST + ":" + providerPort + " SIP/2.0\r\n"
                + "Via: SIP/2.0/UDP " + HOST + ":" + referrerPort
                + ";branch=z9hG4bK-pjsip-native-initial;rport\r\n"
                + "Max-Forwards: 70\r\n"
                + "From: <sip:referrer@" + HOST + ":" + referrerPort + ">;tag=baudot-referrer-pjsip-native\r\n"
                + "To: <sip:provider-a@" + HOST + ":" + providerPort + ">\r\n"
                + "Call-ID: baudot-pjsip-native-refer@127.0.0.1\r\n"
                + "CSeq: 1 INVITE\r\n"
                + "Contact: <sip:referrer@" + HOST + ":" + referrerPort + ">\r\n"
                + "Content-Length: 0\r\n\r\n";
    }

    private static String originalAck(int providerPort, int referrerPort) {
        return "ACK sip:provider-a@" + HOST + ":" + providerPort + " SIP/2.0\r\n"
                + "Via: SIP/2.0/UDP " + HOST + ":" + referrerPort
                + ";branch=z9hG4bK-pjsip-native-ack;rport\r\n"
                + "Max-Forwards: 70\r\n"
                + "From: <sip:referrer@" + HOST + ":" + referrerPort + ">;tag=baudot-referrer-pjsip-native\r\n"
                + "To: <sip:provider-a@" + HOST + ":" + providerPort + ">;tag=baudot-provider-a-pjsip-native\r\n"
                + "Call-ID: baudot-pjsip-native-refer@127.0.0.1\r\n"
                + "CSeq: 1 ACK\r\n"
                + "Content-Length: 0\r\n\r\n";
    }

    private static String referRequest(
            int providerPort, int referrerPort, String targetHost, int targetPort) {
        return "REFER sip:provider-a@" + HOST + ":" + providerPort + " SIP/2.0\r\n"
                + "Via: SIP/2.0/UDP " + HOST + ":" + referrerPort
                + ";branch=z9hG4bK-pjsip-native-refer;rport\r\n"
                + "Max-Forwards: 70\r\n"
                + "From: <sip:referrer@" + HOST + ":" + referrerPort + ">;tag=baudot-referrer-pjsip-native\r\n"
                + "To: <sip:provider-a@" + HOST + ":" + providerPort + ">;tag=baudot-provider-a-pjsip-native\r\n"
                + "Call-ID: baudot-pjsip-native-refer@127.0.0.1\r\n"
                + "CSeq: 2 REFER\r\n"
                + "Contact: <sip:referrer@" + HOST + ":" + referrerPort + ">\r\n"
                + "Refer-To: <sip:pjsip-target@" + targetHost + ":" + targetPort + ">\r\n"
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

    private static int envInt(String name, int fallback) {
        return Integer.parseInt(env(name, Integer.toString(fallback)));
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
