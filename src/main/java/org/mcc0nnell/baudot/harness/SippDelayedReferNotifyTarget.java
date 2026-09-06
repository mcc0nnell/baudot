package org.mcc0nnell.baudot.harness;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
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
import javax.sip.header.CSeqHeader;
import javax.sip.header.CallIdHeader;
import javax.sip.header.ContactHeader;
import javax.sip.header.ContentTypeHeader;
import javax.sip.header.FromHeader;
import javax.sip.header.Header;
import javax.sip.header.HeaderFactory;
import javax.sip.header.MaxForwardsHeader;
import javax.sip.header.ToHeader;
import javax.sip.header.ViaHeader;
import javax.sip.message.MessageFactory;
import javax.sip.message.Request;
import javax.sip.message.Response;

/**
 * JAIN SIP referrer target for SIPP-HOSTILE-002 / BAUDOT-INTEROP-004.
 *
 * The target establishes the original dialog, sends REFER, timestamps the 202,
 * and then waits for SIPp's deliberately delayed terminal NOTIFY. It preserves
 * the old dialog and never promotes replacement or RTT readiness from REFER or
 * NOTIFY signaling alone.
 */
public final class SippDelayedReferNotifyTarget {
    private static final String SCENARIO = "BAUDOT-INTEROP-004";
    private static final String HOSTILE_ID = "SIPP-HOSTILE-002";
    private static final String CORRELATION = "sipp-hostile-002-jain-v1";
    private static final String HOST = "127.0.0.1";
    private static final int LOCAL_PORT = 5093;
    private static final int SIPP_PORT = 5092;
    private static final Duration COMPLETION_TIMEOUT = Duration.ofSeconds(12);
    private static final long MIN_EXPECTED_NOTIFY_DELAY_MILLIS = 900L;

    private SippDelayedReferNotifyTarget() {
    }

    public static void main(String[] args) throws Exception {
        Path evidenceRoot = Path.of(env("BAUDOT_EVIDENCE_DIR", "target/evidence"));
        try (EvidenceRecorder evidence = new EvidenceRecorder(
                evidenceRoot, SCENARIO, CORRELATION, "jain-referrer-target");
             Referrer referrer = new Referrer(evidence)) {

            referrer.start();
            referrer.sendInvite();
            boolean completed = referrer.awaitTerminalNotify(COMPLETION_TIMEOUT);
            long notifyDelayMillis = referrer.notifyDelayMillis();

            boolean targetPass = completed
                    && referrer.dialogEstablished()
                    && referrer.referSent()
                    && referrer.referAccepted()
                    && referrer.terminalNotifyObserved()
                    && referrer.notifyAcknowledged()
                    && referrer.terminalSipfragSuccess()
                    && notifyDelayMillis >= MIN_EXPECTED_NOTIFY_DELAY_MILLIS;

            evidence.result(Map.ofEntries(
                    Map.entry("scenario.id", SCENARIO),
                    Map.entry("hostile.id", HOSTILE_ID),
                    Map.entry("correlation.id", CORRELATION),
                    Map.entry("harness.layer", "jain-referrer-external-sipp-target"),
                    Map.entry("target.dialogEstablished", Boolean.toString(referrer.dialogEstablished())),
                    Map.entry("target.referSent", Boolean.toString(referrer.referSent())),
                    Map.entry("target.referAccepted202", Boolean.toString(referrer.referAccepted())),
                    Map.entry("target.terminalNotifyObserved", Boolean.toString(referrer.terminalNotifyObserved())),
                    Map.entry("target.notifyAcknowledged200", Boolean.toString(referrer.notifyAcknowledged())),
                    Map.entry("target.terminalSipfragSuccess", Boolean.toString(referrer.terminalSipfragSuccess())),
                    Map.entry("target.notifyDelayMillis", Long.toString(notifyDelayMillis)),
                    Map.entry("target.result", targetPass ? "PASS" : "FAIL"),
                    Map.entry("terminal.referVerdictOwnedHere", "false"),
                    Map.entry("replacement.dialog.established", "false"),
                    Map.entry("firstT140CharacterObserved", "false"),
                    Map.entry("rttReady", "false"),
                    Map.entry("oldLegReleased", "false")));

            if (!targetPass) {
                throw new IllegalStateException("delayed REFER/NOTIFY target did not complete expected target-side state");
            }
        }

        // The verdict and evidence are sealed before this point. Terminate the
        // standalone process explicitly so JAIN SIP implementation threads
        // cannot hold the bounded external gate open after success.
        System.exit(0);
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }

    private static String offerSdp() {
        return "v=0\r\n"
                + "o=baudot 1 1 IN IP4 " + HOST + "\r\n"
                + "s=sipp-delayed-refer-notify\r\n"
                + "c=IN IP4 " + HOST + "\r\n"
                + "t=0 0\r\n"
                + "m=text 42102 RTP/AVP 98\r\n"
                + "a=rtpmap:98 t140/1000\r\n"
                + "a=sendrecv\r\n";
    }

    private static final class Referrer implements SipListener, AutoCloseable {
        private final EvidenceRecorder evidence;
        private final CountDownLatch terminalNotify = new CountDownLatch(1);
        private final AtomicBoolean dialogEstablished = new AtomicBoolean();
        private final AtomicBoolean referSent = new AtomicBoolean();
        private final AtomicBoolean referAccepted = new AtomicBoolean();
        private final AtomicBoolean notifyObserved = new AtomicBoolean();
        private final AtomicBoolean notifyAcknowledged = new AtomicBoolean();
        private final AtomicBoolean sipfragSuccess = new AtomicBoolean();
        private final AtomicLong referAcceptedNanos = new AtomicLong(-1L);
        private final AtomicLong notifyObservedNanos = new AtomicLong(-1L);

        private final SipStack stack;
        private final SipProvider provider;
        private final AddressFactory addresses;
        private final HeaderFactory headers;
        private final MessageFactory messages;
        private ClientTransaction inviteTransaction;
        private volatile Dialog dialog;

        Referrer(EvidenceRecorder evidence) throws Exception {
            this.evidence = evidence;
            SipFactory factory = SipFactory.getInstance();
            factory.setPathName("gov.nist");

            Properties properties = new Properties();
            properties.setProperty("javax.sip.STACK_NAME", "baudot-sipp-delayed-refer-notify-target");
            properties.setProperty("gov.nist.javax.sip.TRACE_LEVEL", "0");
            this.stack = factory.createSipStack(properties);
            this.addresses = factory.createAddressFactory();
            this.headers = factory.createHeaderFactory();
            this.messages = factory.createMessageFactory();

            ListeningPoint point = stack.createListeningPoint(HOST, LOCAL_PORT, ListeningPoint.UDP);
            this.provider = stack.createSipProvider(point);
            this.provider.addSipListener(this);
        }

        void start() throws Exception {
            stack.start();
            evidence.event("sipp.refer.target.ready", Map.of(
                    "bind", HOST + ":" + LOCAL_PORT,
                    "peer", HOST + ":" + SIPP_PORT,
                    "transport", "udp"));
        }

        void sendInvite() throws Exception {
            SipURI requestUri = sipUri("provider-a", HOST, SIPP_PORT);
            Address fromAddress = addresses.createAddress(sipUri("referrer", HOST, LOCAL_PORT));
            FromHeader from = headers.createFromHeader(fromAddress, "baudot-jain-referrer");
            Address toAddress = addresses.createAddress(sipUri("provider-a", HOST, SIPP_PORT));
            ToHeader to = headers.createToHeader(toAddress, null);
            List<ViaHeader> vias = new ArrayList<>();
            ViaHeader via = headers.createViaHeader(HOST, LOCAL_PORT, ListeningPoint.UDP, null);
            via.setRPort();
            vias.add(via);
            CallIdHeader callId = provider.getNewCallId();
            CSeqHeader cseq = headers.createCSeqHeader(1L, Request.INVITE);
            MaxForwardsHeader max = headers.createMaxForwardsHeader(70);
            Request invite = messages.createRequest(
                    requestUri, Request.INVITE, callId, cseq, from, to, vias, max);
            invite.addHeader(contact("referrer", LOCAL_PORT));
            ContentTypeHeader contentType = headers.createContentTypeHeader("application", "sdp");
            invite.setContent(offerSdp(), contentType);

            evidence.writeBytes("initial-invite.request.sip", invite.toString().getBytes(StandardCharsets.UTF_8));
            evidence.event("sipp.refer.invite.sent", Map.of("callId", callId.getCallId()));
            inviteTransaction = provider.getNewClientTransaction(invite);
            inviteTransaction.sendRequest();
        }

        boolean awaitTerminalNotify(Duration timeout) throws InterruptedException {
            return terminalNotify.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        boolean dialogEstablished() {
            return dialogEstablished.get();
        }

        boolean referSent() {
            return referSent.get();
        }

        boolean referAccepted() {
            return referAccepted.get();
        }

        boolean terminalNotifyObserved() {
            return notifyObserved.get();
        }

        boolean notifyAcknowledged() {
            return notifyAcknowledged.get();
        }

        boolean terminalSipfragSuccess() {
            return sipfragSuccess.get();
        }

        long notifyDelayMillis() {
            long accepted = referAcceptedNanos.get();
            long notified = notifyObservedNanos.get();
            if (accepted < 0L || notified < accepted) {
                return -1L;
            }
            return TimeUnit.NANOSECONDS.toMillis(notified - accepted);
        }

        @Override
        public void processResponse(ResponseEvent event) {
            Response response = event.getResponse();
            CSeqHeader cseq = (CSeqHeader) response.getHeader(CSeqHeader.NAME);
            if (cseq == null) {
                return;
            }

            try {
                evidence.writeBytes(
                        "response-" + cseq.getSeqNumber() + "-" + cseq.getMethod().toLowerCase()
                                + "-" + response.getStatusCode() + ".sip",
                        response.toString().getBytes(StandardCharsets.UTF_8));

                if (Request.INVITE.equals(cseq.getMethod()) && response.getStatusCode() == Response.OK) {
                    byte[] answer = response.getRawContent();
                    if (answer != null && answer.length > 0) {
                        evidence.writeBytes("initial-answer.sdp", answer);
                    }
                    Dialog established = event.getDialog();
                    if (established == null && inviteTransaction != null) {
                        established = inviteTransaction.getDialog();
                    }
                    if (established == null) {
                        throw new IllegalStateException("initial 200 OK arrived without dialog");
                    }
                    dialog = established;
                    Request ack = dialog.createAck(cseq.getSeqNumber());
                    evidence.writeBytes("initial-ack.request.sip", ack.toString().getBytes(StandardCharsets.UTF_8));
                    dialog.sendAck(ack);
                    dialogEstablished.set(true);
                    evidence.event("sipp.refer.dialog.established", Map.of("status", "200"));
                    sendRefer();
                    return;
                }

                if (Request.REFER.equals(cseq.getMethod()) && response.getStatusCode() == Response.ACCEPTED) {
                    referAcceptedNanos.compareAndSet(-1L, System.nanoTime());
                    referAccepted.set(true);
                    evidence.event("sipp.refer.accepted", Map.of(
                            "status", "202",
                            "replacementReady", "false",
                            "rttReady", "false"));
                }
            } catch (Exception e) {
                evidence.event("sipp.refer.response.error", Map.of("error", e.toString()));
            }
        }

        private void sendRefer() throws Exception {
            if (dialog == null) {
                throw new IllegalStateException("dialog unavailable for REFER");
            }
            Request refer = dialog.createRequest(Request.REFER);
            Header referTo = headers.createHeader("Refer-To", "<sip:replacement@127.0.0.1:5999>");
            refer.addHeader(referTo);
            refer.addHeader(contact("referrer", LOCAL_PORT));
            evidence.writeBytes("refer.request.sip", refer.toString().getBytes(StandardCharsets.UTF_8));
            ClientTransaction transaction = provider.getNewClientTransaction(refer);
            dialog.sendRequest(transaction);
            referSent.set(true);
            evidence.event("sipp.refer.sent", Map.of(
                    "target", "sip:replacement@127.0.0.1:5999",
                    "replacementReady", "false"));
        }

        @Override
        public void processRequest(RequestEvent event) {
            Request request = event.getRequest();
            if (!Request.NOTIFY.equals(request.getMethod())) {
                return;
            }

            try {
                evidence.writeBytes("terminal-notify.request.sip", request.toString().getBytes(StandardCharsets.UTF_8));
                notifyObservedNanos.compareAndSet(-1L, System.nanoTime());
                notifyObserved.set(true);

                Header eventHeader = request.getHeader("Event");
                Header subscription = request.getHeader("Subscription-State");
                byte[] body = request.getRawContent();
                String sipfrag = body == null ? "" : new String(body, StandardCharsets.UTF_8).trim();
                if (body != null) {
                    evidence.writeBytes("terminal-notify.sipfrag", body);
                }

                boolean eventIsRefer = eventHeader != null
                        && eventHeader.toString().toLowerCase().contains("refer");
                boolean terminated = subscription != null
                        && subscription.toString().toLowerCase().contains("terminated");
                boolean bodySuccess = sipfrag.toUpperCase().startsWith("SIP/2.0 200");
                sipfragSuccess.set(eventIsRefer && terminated && bodySuccess);

                evidence.event("sipp.refer.notify.observed", Map.of(
                        "eventRefer", Boolean.toString(eventIsRefer),
                        "subscriptionTerminated", Boolean.toString(terminated),
                        "sipfragSuccess", Boolean.toString(bodySuccess),
                        "delayMillis", Long.toString(notifyDelayMillis()),
                        "replacementReady", "false",
                        "rttReady", "false"));

                ServerTransaction transaction = event.getServerTransaction();
                if (transaction == null) {
                    transaction = provider.getNewServerTransaction(request);
                }
                Response ok = messages.createResponse(Response.OK, request);
                evidence.writeBytes("terminal-notify-200.response.sip", ok.toString().getBytes(StandardCharsets.UTF_8));
                transaction.sendResponse(ok);
                notifyAcknowledged.set(true);
                terminalNotify.countDown();
            } catch (Exception e) {
                evidence.event("sipp.refer.notify.error", Map.of("error", e.toString()));
            }
        }

        private SipURI sipUri(String user, String host, int port) throws Exception {
            SipURI uri = addresses.createSipURI(user, host);
            uri.setPort(port);
            uri.setTransportParam(ListeningPoint.UDP);
            return uri;
        }

        private ContactHeader contact(String user, int port) throws Exception {
            Address address = addresses.createAddress(sipUri(user, HOST, port));
            return headers.createContactHeader(address);
        }

        @Override
        public void processTimeout(TimeoutEvent event) {
            evidence.event("sipp.refer.timeout", Map.of(
                    "server", Boolean.toString(event.isServerTransaction())));
        }

        @Override
        public void processIOException(IOExceptionEvent event) {
            evidence.event("sipp.refer.ioError", Map.of(
                    "host", String.valueOf(event.getHost()),
                    "port", Integer.toString(event.getPort()),
                    "transport", String.valueOf(event.getTransport())));
        }

        @Override
        public void processTransactionTerminated(TransactionTerminatedEvent event) {
            evidence.event("sipp.refer.transactionTerminated", Map.of(
                    "server", Boolean.toString(event.isServerTransaction())));
        }

        @Override
        public void processDialogTerminated(DialogTerminatedEvent event) {
            evidence.event("sipp.refer.dialogTerminated", Map.of(
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
