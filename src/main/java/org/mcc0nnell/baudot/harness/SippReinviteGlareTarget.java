package org.mcc0nnell.baudot.harness;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
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
import javax.sip.header.CSeqHeader;
import javax.sip.header.ContactHeader;
import javax.sip.header.HeaderFactory;
import javax.sip.header.ToHeader;
import javax.sip.message.MessageFactory;
import javax.sip.message.Request;
import javax.sip.message.Response;

/**
 * External-peer JAIN SIP target for SIPP-HOSTILE-004 / BAUDOT-INTEROP-003.
 *
 * SIPp supplies the peer stimulus. This target establishes one dialog, holds
 * CSeq 2 re-INVITE long enough for CSeq 3 to create overlap pressure, then
 * completes CSeq 2. It records JAIN-side observations but does not decide the
 * terminal glare verdict; a Baudot reducer must join these observations with
 * the preserved SIPp message trace.
 */
public final class SippReinviteGlareTarget {
    private static final String SCENARIO = "BAUDOT-INTEROP-003";
    private static final String CORRELATION = "sipp-hostile-004-jain-v1";
    private static final String HOST = "127.0.0.1";
    private static final int PORT = 5090;
    private static final String TO_TAG = "baudot-sipp-callee";
    private static final Duration COMPLETION_TIMEOUT = Duration.ofSeconds(12);
    private static final long FIRST_REINVITE_HOLD_MILLIS = 800L;

    private SippReinviteGlareTarget() {
    }

    public static void main(String[] args) throws Exception {
        Path evidenceRoot = Path.of(env("BAUDOT_EVIDENCE_DIR", "target/evidence"));
        try (EvidenceRecorder evidence = new EvidenceRecorder(
                evidenceRoot, SCENARIO, CORRELATION, "sipp-glare-target");
             Target target = new Target(evidence)) {
            target.start();
            boolean completed = target.awaitCompletion(COMPLETION_TIMEOUT);
            boolean targetPass = completed
                    && target.initialInviteAnswered()
                    && target.initialAckReceived()
                    && target.firstReinviteHeld()
                    && target.firstReinviteAnswered()
                    && target.firstReinviteAckReceived();

            evidence.result(Map.ofEntries(
                    Map.entry("scenario.id", SCENARIO),
                    Map.entry("hostile.id", "SIPP-HOSTILE-004"),
                    Map.entry("correlation.id", CORRELATION),
                    Map.entry("harness.layer", "jain-sip-external-sipp-target"),
                    Map.entry("target.initialInvite200Sent", Boolean.toString(target.initialInviteAnswered())),
                    Map.entry("target.initialAckObserved", Boolean.toString(target.initialAckReceived())),
                    Map.entry("target.firstReinviteHeld", Boolean.toString(target.firstReinviteHeld())),
                    Map.entry("target.firstReinvite200Sent", Boolean.toString(target.firstReinviteAnswered())),
                    Map.entry("target.firstReinviteAckObserved", Boolean.toString(target.firstReinviteAckReceived())),
                    Map.entry("target.glareReinviteDeliveredToApplication", Boolean.toString(target.glareDeliveredToApplication())),
                    Map.entry("target.application491Sent", Boolean.toString(target.application491Sent())),
                    Map.entry("target.result", targetPass ? "PASS" : "FAIL"),
                    Map.entry("terminal.glareVerdictOwnedHere", "false"),
                    Map.entry("media.readiness.proven", "false"),
                    Map.entry("rttReady", "false")));

            if (!targetPass) {
                throw new IllegalStateException("SIPp glare JAIN target did not complete expected target-side state");
            }
        }
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
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

    private static final class Target implements SipListener, AutoCloseable {
        private final EvidenceRecorder evidence;
        private final CountDownLatch completion = new CountDownLatch(1);
        private final AtomicBoolean initial200Sent = new AtomicBoolean();
        private final AtomicBoolean initialAck = new AtomicBoolean();
        private final AtomicBoolean firstHeld = new AtomicBoolean();
        private final AtomicBoolean first200Sent = new AtomicBoolean();
        private final AtomicBoolean firstAck = new AtomicBoolean();
        private final AtomicBoolean glareDelivered = new AtomicBoolean();
        private final AtomicBoolean app491Sent = new AtomicBoolean();
        private final AtomicBoolean delayedCompletionStarted = new AtomicBoolean();
        private final AtomicInteger requestOrdinal = new AtomicInteger();

        private final SipStack stack;
        private final SipProvider provider;
        private final AddressFactory addresses;
        private final HeaderFactory headers;
        private final MessageFactory messages;

        private volatile ServerTransaction pendingFirstTransaction;
        private volatile Request pendingFirstRequest;

        Target(EvidenceRecorder evidence) throws Exception {
            this.evidence = evidence;
            SipFactory factory = SipFactory.getInstance();
            factory.setPathName("gov.nist");

            Properties properties = new Properties();
            properties.setProperty("javax.sip.STACK_NAME", "baudot-sipp-reinvite-glare-target");
            properties.setProperty("gov.nist.javax.sip.TRACE_LEVEL", "0");
            this.stack = factory.createSipStack(properties);
            this.addresses = factory.createAddressFactory();
            this.headers = factory.createHeaderFactory();
            this.messages = factory.createMessageFactory();

            ListeningPoint point = stack.createListeningPoint(HOST, PORT, ListeningPoint.UDP);
            this.provider = stack.createSipProvider(point);
            this.provider.addSipListener(this);
        }

        void start() throws Exception {
            stack.start();
            evidence.event("sipp.target.ready", Map.of(
                    "bind", HOST + ":" + PORT,
                    "transport", "udp",
                    "firstReinviteHoldMillis", Long.toString(FIRST_REINVITE_HOLD_MILLIS)));
        }

        boolean awaitCompletion(Duration timeout) throws InterruptedException {
            return completion.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        boolean initialInviteAnswered() {
            return initial200Sent.get();
        }

        boolean initialAckReceived() {
            return initialAck.get();
        }

        boolean firstReinviteHeld() {
            return firstHeld.get();
        }

        boolean firstReinviteAnswered() {
            return first200Sent.get();
        }

        boolean firstReinviteAckReceived() {
            return firstAck.get();
        }

        boolean glareDeliveredToApplication() {
            return glareDelivered.get();
        }

        boolean application491Sent() {
            return app491Sent.get();
        }

        @Override
        public void processRequest(RequestEvent event) {
            Request request = event.getRequest();
            CSeqHeader cseq = (CSeqHeader) request.getHeader(CSeqHeader.NAME);
            long sequence = cseq == null ? -1L : cseq.getSeqNumber();
            int ordinal = requestOrdinal.incrementAndGet();

            try {
                evidence.writeBytes(
                        String.format("request-%03d-%s-cseq-%d.sip", ordinal, request.getMethod().toLowerCase(), sequence),
                        request.toString().getBytes(StandardCharsets.UTF_8));
                evidence.event("sipp.target.request", Map.of(
                        "method", request.getMethod(),
                        "cseq", Long.toString(sequence),
                        "dialog", event.getDialog() == null ? "none" : String.valueOf(event.getDialog().getDialogId())));

                if (Request.ACK.equals(request.getMethod())) {
                    if (sequence == 1L) {
                        initialAck.set(true);
                    } else if (sequence == 2L) {
                        firstAck.set(true);
                        completion.countDown();
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

                if (sequence == 1L) {
                    Response ok = messages.createResponse(Response.OK, request);
                    ToHeader to = (ToHeader) ok.getHeader(ToHeader.NAME);
                    if (to.getTag() == null) {
                        to.setTag(TO_TAG);
                    }
                    addContact(ok);
                    ok.setContent(
                            sdp(42001, "sipp-glare-answer-initial"),
                            headers.createContentTypeHeader("application", "sdp"));
                    evidence.writeBytes("response-initial-200.sip", ok.toString().getBytes(StandardCharsets.UTF_8));
                    transaction.sendResponse(ok);
                    initial200Sent.set(true);
                    return;
                }

                if (sequence == 2L) {
                    pendingFirstTransaction = transaction;
                    pendingFirstRequest = request;
                    firstHeld.set(true);
                    evidence.event("sipp.target.reinvite.held", Map.of(
                            "cseq", "2",
                            "state", String.valueOf(transaction.getState())));
                    startDelayedFirstCompletion();
                    return;
                }

                if (sequence == 3L) {
                    glareDelivered.set(true);
                    Response pending = messages.createResponse(Response.REQUEST_PENDING, request);
                    evidence.writeBytes("response-glare-491.sip", pending.toString().getBytes(StandardCharsets.UTF_8));
                    transaction.sendResponse(pending);
                    app491Sent.set(true);
                    evidence.event("sipp.target.glare.application491", Map.of(
                            "cseq", "3",
                            "status", "491"));
                }
            } catch (Exception e) {
                evidence.event("sipp.target.error", Map.of(
                        "method", request.getMethod(),
                        "cseq", Long.toString(sequence),
                        "error", e.toString()));
            }
        }

        private void startDelayedFirstCompletion() {
            if (!delayedCompletionStarted.compareAndSet(false, true)) {
                return;
            }
            Thread thread = new Thread(() -> {
                try {
                    Thread.sleep(FIRST_REINVITE_HOLD_MILLIS);
                    completeFirstReinvite();
                } catch (Exception e) {
                    evidence.event("sipp.target.delayedCompletion.error", Map.of("error", e.toString()));
                }
            }, "baudot-sipp-reinvite-completion");
            thread.setDaemon(true);
            thread.start();
        }

        private synchronized void completeFirstReinvite() throws Exception {
            if (first200Sent.get()) {
                return;
            }
            if (pendingFirstTransaction == null || pendingFirstRequest == null) {
                throw new IllegalStateException("no pending CSeq 2 re-INVITE to complete");
            }
            Response ok = messages.createResponse(Response.OK, pendingFirstRequest);
            addContact(ok);
            ok.setContent(
                    sdp(42002, "sipp-glare-answer-reinvite-2"),
                    headers.createContentTypeHeader("application", "sdp"));
            evidence.writeBytes("response-reinvite-2-200.sip", ok.toString().getBytes(StandardCharsets.UTF_8));
            pendingFirstTransaction.sendResponse(ok);
            first200Sent.set(true);
            evidence.event("sipp.target.reinvite.completed", Map.of(
                    "cseq", "2",
                    "status", "200"));
        }

        private void addContact(Response response) throws Exception {
            SipURI contactUri = addresses.createSipURI("callee", HOST);
            contactUri.setPort(PORT);
            contactUri.setTransportParam(ListeningPoint.UDP);
            Address contactAddress = addresses.createAddress(contactUri);
            ContactHeader contact = headers.createContactHeader(contactAddress);
            response.addHeader(contact);
        }

        @Override
        public void processResponse(ResponseEvent event) {
            // UAS-only target.
        }

        @Override
        public void processTimeout(TimeoutEvent event) {
            evidence.event("sipp.target.timeout", Map.of(
                    "server", Boolean.toString(event.isServerTransaction())));
        }

        @Override
        public void processIOException(IOExceptionEvent event) {
            evidence.event("sipp.target.ioError", Map.of(
                    "host", String.valueOf(event.getHost()),
                    "port", Integer.toString(event.getPort()),
                    "transport", String.valueOf(event.getTransport())));
        }

        @Override
        public void processTransactionTerminated(TransactionTerminatedEvent event) {
            evidence.event("sipp.target.transactionTerminated", Map.of(
                    "server", Boolean.toString(event.isServerTransaction())));
        }

        @Override
        public void processDialogTerminated(DialogTerminatedEvent event) {
            evidence.event("sipp.target.dialogTerminated", Map.of(
                    "dialog", String.valueOf(event.getDialog().getDialogId())));
        }

        @Override
        public void close() {
            try {
                provider.removeSipListener(this);
            } catch (Exception ignored) {
                // Best-effort teardown.
            }
            try {
                stack.stop();
            } catch (Exception ignored) {
                // Best-effort teardown.
            }
        }
    }
}
