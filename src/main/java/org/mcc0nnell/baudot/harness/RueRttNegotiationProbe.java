package org.mcc0nnell.baudot.harness;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;
import java.util.UUID;
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
 * Controlled live SDP-negotiation probe for the RFC 9248 RUE RTT test lane.
 *
 * <p>This probe intentionally sends no RTT media. Its job is only to create
 * real JAIN SIP offer/answer dialogs for manipulated capability/policy arms
 * and preserve the raw SDP observed on each side. A separate Python reducer
 * owns the negotiation/readiness classification.</p>
 */
public final class RueRttNegotiationProbe {
    private static final String HOST = "127.0.0.1";
    private static final Duration TIMEOUT = Duration.ofSeconds(5);
    private static final int T140_PAYLOAD_TYPE = 98;

    private RueRttNegotiationProbe() {
    }

    record Arm(String id, boolean localRttEnabled, boolean remoteOffersT140) {
        boolean answerAcceptsT140() {
            return localRttEnabled && remoteOffersT140;
        }
    }

    private static final List<Arm> ARMS = List.of(
            new Arm("local-enabled-remote-absent", true, false),
            new Arm("remote-offered-local-disabled", false, true),
            new Arm("both-enabled-negotiated-no-media-yet", true, true));

    public static void main(String[] args) throws Exception {
        Path root = Path.of(env(
                "BAUDOT_RUE_RTT_NEGOTIATION_EVIDENCE",
                "target/evidence/RUE-RTT-NEGOTIATION-LIVE"));
        Files.createDirectories(root);
        int basePort = Integer.parseInt(env("BAUDOT_RUE_RTT_NEGOTIATION_BASE_PORT", "5270"));
        boolean allPassed = true;

        for (int index = 0; index < ARMS.size(); index++) {
            Arm arm = ARMS.get(index);
            int callerPort = basePort + index * 10;
            int ruePort = callerPort + 1;
            Path evidenceDir = root.resolve(arm.id());
            Files.createDirectories(evidenceDir);

            boolean dialogEstablished;
            boolean ackObserved;
            String error;

            try (Endpoint caller = Endpoint.caller(arm, callerPort, ruePort, evidenceDir);
                 Endpoint rue = Endpoint.rue(arm, ruePort, callerPort, evidenceDir)) {
                rue.start();
                caller.start();
                caller.sendInvite();
                dialogEstablished = caller.awaitDialog(TIMEOUT);
                ackObserved = rue.awaitAck(TIMEOUT);
                error = firstError(caller.error(), rue.error());
            }

            Properties result = new Properties();
            result.setProperty("schema", "baudot.rue-rtt-live-observation@1");
            result.setProperty("arm", arm.id());
            result.setProperty("localRttEnabled", Boolean.toString(arm.localRttEnabled()));
            result.setProperty("configuredRemoteOffersT140", Boolean.toString(arm.remoteOffersT140()));
            result.setProperty("configuredAnswerAcceptsT140", Boolean.toString(arm.answerAcceptsT140()));
            result.setProperty("dialogEstablished", Boolean.toString(dialogEstablished));
            result.setProperty("ackObserved", Boolean.toString(ackObserved));
            result.setProperty("rttMediaAttempted", "false");
            result.setProperty("claim", "controlled-live-sdp-negotiation-only");
            result.setProperty("javaVerdictAuthority", "false");
            if (error != null) {
                result.setProperty("error", error);
            }
            try (var output = Files.newOutputStream(evidenceDir.resolve("observation.properties"))) {
                result.store(output, "Baudot live RUE RTT negotiation observation");
            }

            boolean passed = dialogEstablished && ackObserved && error == null;
            allPassed &= passed;
            System.out.printf(
                    "%s: dialog=%s ack=%s mediaAttempted=false %s%n",
                    arm.id(), dialogEstablished, ackObserved, passed ? "PASS" : "FAIL");
            Thread.sleep(100L);
        }

        if (!allPassed) {
            throw new IllegalStateException("one or more live RUE RTT negotiation arms failed signaling");
        }
        System.out.println("RUE RTT live SIP offer/answer capture: PASS");
    }

    private static String firstError(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return null;
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }

    private static String offerSdp(Arm arm) {
        String base = "v=0\r\n"
                + "o=baudot-remote 0 0 IN IP4 203.0.113.30\r\n"
                + "s=Baudot synthetic remote offer\r\n"
                + "c=IN IP4 203.0.113.30\r\n"
                + "t=0 0\r\n"
                + "m=audio 49170 RTP/AVP 0\r\n"
                + "a=rtpmap:0 PCMU/8000\r\n";
        if (!arm.remoteOffersT140()) {
            return base;
        }
        return base
                + "m=text 49172 RTP/AVP " + T140_PAYLOAD_TYPE + "\r\n"
                + "a=rtpmap:" + T140_PAYLOAD_TYPE + " t140/1000\r\n";
    }

    private static String answerSdp(Arm arm) {
        String base = "v=0\r\n"
                + "o=baudot-rue 0 0 IN IP4 203.0.113.31\r\n"
                + "s=Baudot synthetic RUE answer\r\n"
                + "c=IN IP4 203.0.113.31\r\n"
                + "t=0 0\r\n"
                + "m=audio 49180 RTP/AVP 0\r\n"
                + "a=rtpmap:0 PCMU/8000\r\n";
        if (!arm.remoteOffersT140()) {
            return base;
        }
        int textPort = arm.answerAcceptsT140() ? 49182 : 0;
        return base
                + "m=text " + textPort + " RTP/AVP " + T140_PAYLOAD_TYPE + "\r\n"
                + "a=rtpmap:" + T140_PAYLOAD_TYPE + " t140/1000\r\n";
    }

    private static final class Endpoint implements SipListener, AutoCloseable {
        private final Arm arm;
        private final boolean caller;
        private final int localPort;
        private final int peerPort;
        private final Path evidenceDir;
        private final CountDownLatch dialog = new CountDownLatch(1);
        private final CountDownLatch ack = new CountDownLatch(1);
        private final AtomicBoolean started = new AtomicBoolean();
        private final AtomicReference<String> error = new AtomicReference<>();
        private final SipStack stack;
        private final SipProvider provider;
        private final AddressFactory addressFactory;
        private final HeaderFactory headerFactory;
        private final MessageFactory messageFactory;
        private ClientTransaction inviteTransaction;

        private Endpoint(Arm arm, boolean caller, int localPort, int peerPort, Path evidenceDir)
                throws Exception {
            this.arm = arm;
            this.caller = caller;
            this.localPort = localPort;
            this.peerPort = peerPort;
            this.evidenceDir = evidenceDir;

            SipFactory factory = SipFactory.getInstance();
            factory.setPathName("gov.nist");
            Properties properties = new Properties();
            properties.setProperty(
                    "javax.sip.STACK_NAME",
                    "baudot-rue-rtt-" + arm.id().replace('-', '_') + "-"
                            + (caller ? "caller-" : "rue-")
                            + UUID.randomUUID().toString().replace("-", ""));
            properties.setProperty("gov.nist.javax.sip.TRACE_LEVEL", "0");
            this.stack = factory.createSipStack(properties);
            this.addressFactory = factory.createAddressFactory();
            this.headerFactory = factory.createHeaderFactory();
            this.messageFactory = factory.createMessageFactory();
            ListeningPoint point = stack.createListeningPoint(HOST, localPort, ListeningPoint.UDP);
            this.provider = stack.createSipProvider(point);
            this.provider.addSipListener(this);
        }

        static Endpoint caller(Arm arm, int localPort, int peerPort, Path evidenceDir)
                throws Exception {
            return new Endpoint(arm, true, localPort, peerPort, evidenceDir);
        }

        static Endpoint rue(Arm arm, int localPort, int peerPort, Path evidenceDir)
                throws Exception {
            return new Endpoint(arm, false, localPort, peerPort, evidenceDir);
        }

        void start() throws Exception {
            stack.start();
            started.set(true);
        }

        void sendInvite() throws Exception {
            if (!caller) {
                throw new IllegalStateException("only caller endpoint sends INVITE");
            }
            SipURI requestUri = addressFactory.createSipURI("rue", HOST);
            requestUri.setPort(peerPort);
            requestUri.setTransportParam(ListeningPoint.UDP);

            Address fromAddress = addressFactory.createAddress(sipUri("remote", localPort));
            FromHeader from = headerFactory.createFromHeader(fromAddress, randomTag());
            Address toAddress = addressFactory.createAddress(sipUri("rue", peerPort));
            ToHeader to = headerFactory.createToHeader(toAddress, null);
            List<ViaHeader> vias = new ArrayList<>();
            ViaHeader via = headerFactory.createViaHeader(HOST, localPort, ListeningPoint.UDP, null);
            via.setRPort();
            vias.add(via);
            CallIdHeader callId = provider.getNewCallId();
            CSeqHeader cseq = headerFactory.createCSeqHeader(1L, Request.INVITE);
            MaxForwardsHeader maxForwards = headerFactory.createMaxForwardsHeader(70);
            Request invite = messageFactory.createRequest(
                    requestUri, Request.INVITE, callId, cseq, from, to, vias, maxForwards);
            invite.addHeader(headerFactory.createContactHeader(fromAddress));
            ContentTypeHeader contentType = headerFactory.createContentTypeHeader("application", "sdp");
            invite.setContent(offerSdp(arm), contentType);
            inviteTransaction = provider.getNewClientTransaction(invite);
            inviteTransaction.sendRequest();
        }

        boolean awaitDialog(Duration timeout) throws InterruptedException {
            return dialog.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        boolean awaitAck(Duration timeout) throws InterruptedException {
            return ack.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        String error() {
            return error.get();
        }

        @Override
        public void processRequest(RequestEvent event) {
            if (caller) {
                return;
            }
            Request request = event.getRequest();
            if (Request.ACK.equals(request.getMethod())) {
                ack.countDown();
                return;
            }
            if (!Request.INVITE.equals(request.getMethod())) {
                return;
            }
            try {
                byte[] rawOffer = request.getRawContent();
                if (rawOffer == null || rawOffer.length == 0) {
                    throw new IllegalStateException("live RTT negotiation INVITE missing SDP offer");
                }
                Files.write(evidenceDir.resolve("offer-observed.sdp"), rawOffer);

                ServerTransaction transaction = event.getServerTransaction();
                if (transaction == null) {
                    transaction = provider.getNewServerTransaction(request);
                }
                Response ok = messageFactory.createResponse(Response.OK, request);
                ToHeader to = (ToHeader) ok.getHeader(ToHeader.NAME);
                if (to.getTag() == null) {
                    to.setTag(randomTag());
                }
                Address contactAddress = addressFactory.createAddress(sipUri("rue", localPort));
                ContactHeader contact = headerFactory.createContactHeader(contactAddress);
                ok.addHeader(contact);
                ok.setContent(
                        answerSdp(arm),
                        headerFactory.createContentTypeHeader("application", "sdp"));
                transaction.sendResponse(ok);
            } catch (Exception e) {
                error.compareAndSet(null, "request: " + e);
            }
        }

        @Override
        public void processResponse(ResponseEvent event) {
            if (!caller) {
                return;
            }
            Response response = event.getResponse();
            CSeqHeader cseq = (CSeqHeader) response.getHeader(CSeqHeader.NAME);
            if (response.getStatusCode() != Response.OK
                    || cseq == null
                    || !Request.INVITE.equals(cseq.getMethod())) {
                return;
            }
            try {
                byte[] rawAnswer = response.getRawContent();
                if (rawAnswer == null || rawAnswer.length == 0) {
                    throw new IllegalStateException("live RTT negotiation 200 OK missing SDP answer");
                }
                Files.write(evidenceDir.resolve("answer-observed.sdp"), rawAnswer);

                Dialog sipDialog = event.getDialog();
                if (sipDialog == null && inviteTransaction != null) {
                    sipDialog = inviteTransaction.getDialog();
                }
                if (sipDialog == null) {
                    throw new IllegalStateException("live RTT negotiation 200 OK has no dialog");
                }
                Request ackRequest = sipDialog.createAck(cseq.getSeqNumber());
                sipDialog.sendAck(ackRequest);
                dialog.countDown();
            } catch (Exception e) {
                error.compareAndSet(null, "response: " + e);
            }
        }

        @Override
        public void processTimeout(TimeoutEvent event) {
            error.compareAndSet(null, "timeout: server=" + event.isServerTransaction());
        }

        @Override
        public void processIOException(IOExceptionEvent event) {
            error.compareAndSet(
                    null,
                    "io: " + event.getHost() + ":" + event.getPort() + "/" + event.getTransport());
        }

        @Override
        public void processTransactionTerminated(TransactionTerminatedEvent event) {
            // Lifecycle evidence is not a verdict input for this bounded probe.
        }

        @Override
        public void processDialogTerminated(DialogTerminatedEvent event) {
            // Lifecycle evidence is not a verdict input for this bounded probe.
        }

        private String sipUri(String user, int port) throws Exception {
            SipURI uri = addressFactory.createSipURI(user, HOST);
            uri.setPort(port);
            uri.setTransportParam(ListeningPoint.UDP);
            return uri.toString();
        }

        @Override
        public void close() {
            if (!started.get()) {
                return;
            }
            try {
                provider.removeSipListener(this);
            } catch (Exception ignored) {
                // Best effort during controlled shutdown.
            }
            try {
                stack.stop();
            } catch (Exception ignored) {
                // Best effort during controlled shutdown.
            }
        }
    }

    private static String randomTag() {
        return UUID.randomUUID().toString().replace("-", "").substring(0, 12);
    }
}
