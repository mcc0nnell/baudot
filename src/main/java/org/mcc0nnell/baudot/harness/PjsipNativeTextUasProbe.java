package org.mcc0nnell.baudot.harness;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
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
 * Qualifies PJSIP 2.17 as an incoming native T.140 endpoint.
 *
 * <p>JAIN SIP owns only controlled call signaling. A separate Python process
 * owns the offered m=text UDP port and may publish an atomic readiness token
 * only after Baudot's RFC 4103/T.140 reference accepts native PJSIP wire data.
 * This class treats that token as opaque authority evidence and releases the
 * dialog only after the token exists.</p>
 */
public final class PjsipNativeTextUasProbe implements SipListener, AutoCloseable {
    private static final String HOST = "127.0.0.1";
    private static final String SCENARIO = "PJSIP-NATIVE-T140-UAS";
    private static final String CORRELATION = "pjsip-2.17-native-text-uas-v1";
    private static final Duration SIP_TIMEOUT = Duration.ofSeconds(8);
    private static final Duration READINESS_TIMEOUT = Duration.ofSeconds(8);

    private final int localPort;
    private final int targetPort;
    private final int mediaPort;
    private final Path readyFile;
    private final EvidenceRecorder evidence;
    private final SipStack stack;
    private final SipProvider provider;
    private final AddressFactory addresses;
    private final HeaderFactory headers;
    private final MessageFactory messages;
    private final CountDownLatch confirmed = new CountDownLatch(1);
    private final CountDownLatch byeResponse = new CountDownLatch(1);
    private final AtomicBoolean t140AnswerObserved = new AtomicBoolean();
    private final AtomicBoolean ackSent = new AtomicBoolean();
    private final AtomicBoolean readinessTokenObserved = new AtomicBoolean();
    private final AtomicBoolean byeSent = new AtomicBoolean();
    private final AtomicLong readinessObservedAt = new AtomicLong(-1L);
    private final AtomicLong byeSentAt = new AtomicLong(-1L);

    private volatile Dialog dialog;

    private PjsipNativeTextUasProbe(
            int localPort,
            int targetPort,
            int mediaPort,
            Path readyFile,
            EvidenceRecorder evidence) throws Exception {
        this.localPort = localPort;
        this.targetPort = targetPort;
        this.mediaPort = mediaPort;
        this.readyFile = readyFile;
        this.evidence = evidence;

        SipFactory factory = SipFactory.getInstance();
        factory.setPathName("gov.nist");
        Properties properties = new Properties();
        properties.setProperty("javax.sip.STACK_NAME", "baudot-pjsip-native-t140-uas-caller");
        properties.setProperty("gov.nist.javax.sip.TRACE_LEVEL", "0");
        this.stack = factory.createSipStack(properties);
        this.addresses = factory.createAddressFactory();
        this.headers = factory.createHeaderFactory();
        this.messages = factory.createMessageFactory();
        ListeningPoint point = stack.createListeningPoint(HOST, localPort, ListeningPoint.UDP);
        this.provider = stack.createSipProvider(point);
        this.provider.addSipListener(this);
    }

    public static void main(String[] args) throws Exception {
        int localPort = envInt("BAUDOT_JAIN_UAC_PORT", 5301);
        int targetPort = envInt("BAUDOT_PJSIP_UAS_PORT", 5302);
        int mediaPort = envInt("BAUDOT_PJSIP_UAS_MEDIA_PORT", 5303);
        Path root = Path.of(env("BAUDOT_EVIDENCE_ROOT", "target/evidence-external"));
        Path readyFile = Path.of(env(
                "BAUDOT_RTT_READY_FILE",
                root.resolve(SCENARIO).resolve(CORRELATION).resolve("readiness/rtt-ready.json").toString()));

        try (EvidenceRecorder evidence = new EvidenceRecorder(root, SCENARIO, CORRELATION, "jain-caller");
             PjsipNativeTextUasProbe probe =
                     new PjsipNativeTextUasProbe(localPort, targetPort, mediaPort, readyFile, evidence)) {
            probe.start();
            probe.sendInvite();
            require(probe.confirmed.await(SIP_TIMEOUT.toMillis(), TimeUnit.MILLISECONDS),
                    "PJSIP UAS dialog did not confirm");
            require(probe.awaitReadinessToken(READINESS_TIMEOUT),
                    "independent RTT readiness token was not published");
            probe.sendBye();
            require(probe.byeResponse.await(SIP_TIMEOUT.toMillis(), TimeUnit.MILLISECONDS),
                    "PJSIP UAS did not acknowledge remote release");

            boolean releaseAfterReadiness = probe.readinessObservedAt.get() > 0
                    && probe.byeSentAt.get() > probe.readinessObservedAt.get();
            boolean pass = probe.t140AnswerObserved.get()
                    && probe.ackSent.get()
                    && probe.readinessTokenObserved.get()
                    && probe.byeSent.get()
                    && releaseAfterReadiness;

            evidence.result(Map.ofEntries(
                    Map.entry("scenario.id", SCENARIO),
                    Map.entry("correlation.id", CORRELATION),
                    Map.entry("caller.implementation", "JAIN-SIP"),
                    Map.entry("callee.implementation", "pjsip/pjproject-2.17"),
                    Map.entry("sip.dialog.confirmed", Boolean.toString(probe.dialog != null)),
                    Map.entry("sip.t140.answerObserved", Boolean.toString(probe.t140AnswerObserved.get())),
                    Map.entry("sip.ack.sent", Boolean.toString(probe.ackSent.get())),
                    Map.entry("rtt.readinessToken.observed", Boolean.toString(probe.readinessTokenObserved.get())),
                    Map.entry("rttReady", "EXTERNAL_BAUDOT_REFERENCE_TOKEN"),
                    Map.entry("call.bye.sent", Boolean.toString(probe.byeSent.get())),
                    Map.entry("call.bye.afterReadiness", Boolean.toString(releaseAfterReadiness)),
                    Map.entry("scenario.result", pass ? "OBSERVED" : "INCOMPLETE"),
                    Map.entry("claimBoundary",
                            "incoming PJSIP native text endpoint qualification; no SIP/RTP/RFC4103/T140/VRS conformance claim")));
            require(pass, "incoming PJSIP native text qualification was incomplete");
        }

        System.exit(0);
    }

    private void start() throws Exception {
        stack.start();
        evidence.event("pjsip.uas.caller_ready", Map.of(
                "sipBind", HOST + ":" + localPort,
                "target", HOST + ":" + targetPort,
                "offeredMedia", HOST + ":" + mediaPort));
    }

    private void sendInvite() throws Exception {
        SipURI requestUri = sipUri("pjsip-target", HOST, targetPort);
        Address fromAddress = addresses.createAddress(sipUri("baudot", HOST, localPort));
        Address toAddress = addresses.createAddress(requestUri);
        FromHeader from = headers.createFromHeader(fromAddress, "baudot-pjsip-uas");
        ToHeader to = headers.createToHeader(toAddress, null);
        List<ViaHeader> vias = new ArrayList<>();
        ViaHeader via = headers.createViaHeader(HOST, localPort, ListeningPoint.UDP, null);
        via.setRPort();
        vias.add(via);
        CallIdHeader callId = provider.getNewCallId();
        CSeqHeader cseq = headers.createCSeqHeader(1L, Request.INVITE);
        MaxForwardsHeader maxForwards = headers.createMaxForwardsHeader(70);

        Request invite = messages.createRequest(
                requestUri, Request.INVITE, callId, cseq, from, to, vias, maxForwards);
        ContactHeader contact = headers.createContactHeader(fromAddress);
        invite.addHeader(contact);
        ContentTypeHeader contentType = headers.createContentTypeHeader("application", "sdp");
        invite.setContent(sdpOffer(), contentType);
        evidence.writeBytes("invite.request.sip", invite.toString().getBytes(StandardCharsets.UTF_8));
        evidence.writeBytes("offer.sdp", sdpOffer().getBytes(StandardCharsets.UTF_8));

        ClientTransaction transaction = provider.getNewClientTransaction(invite);
        transaction.sendRequest();
        evidence.event("pjsip.uas.invite_sent", Map.of("callId", callId.getCallId()));
    }

    private boolean awaitReadinessToken(Duration timeout) throws Exception {
        long deadline = System.nanoTime() + timeout.toNanos();
        while (System.nanoTime() < deadline) {
            if (Files.isRegularFile(readyFile)) {
                byte[] token = Files.readAllBytes(readyFile);
                evidence.writeBytes("rtt-ready.token.json", token);
                readinessObservedAt.set(System.nanoTime());
                readinessTokenObserved.set(true);
                evidence.event("pjsip.uas.readiness_token_observed", Map.of(
                        "bytes", Integer.toString(token.length),
                        "authority", "external-baudot-reference",
                        "classification", "opaque-token-presence"));
                return true;
            }
            Thread.sleep(25L);
        }
        evidence.event("pjsip.uas.readiness_token_timeout", Map.of(
                "timeoutMs", Long.toString(timeout.toMillis())));
        return false;
    }

    private void sendBye() throws Exception {
        require(dialog != null, "cannot release missing dialog");
        Request bye = dialog.createRequest(Request.BYE);
        evidence.writeBytes("bye.request.sip", bye.toString().getBytes(StandardCharsets.UTF_8));
        ClientTransaction transaction = provider.getNewClientTransaction(bye);
        byeSentAt.set(System.nanoTime());
        byeSent.set(true);
        dialog.sendRequest(transaction);
        evidence.event("pjsip.uas.bye_sent", Map.of(
                "afterReadiness", Boolean.toString(byeSentAt.get() > readinessObservedAt.get())));
    }

    @Override
    public void processResponse(ResponseEvent event) {
        Response response = event.getResponse();
        CSeqHeader cseq = (CSeqHeader) response.getHeader(CSeqHeader.NAME);
        if (cseq == null) {
            return;
        }
        try {
            if (Request.INVITE.equals(cseq.getMethod()) && response.getStatusCode() >= 200
                    && response.getStatusCode() < 300) {
                evidence.writeBytes("invite-200.response.sip",
                        response.toString().getBytes(StandardCharsets.UTF_8));
                String body = response.getRawContent() == null
                        ? ""
                        : new String(response.getRawContent(), StandardCharsets.UTF_8);
                evidence.writeBytes("answer.sdp", body.getBytes(StandardCharsets.UTF_8));
                String lower = body.toLowerCase();
                boolean t140 = lower.contains("m=text ") && lower.contains("t140/1000");
                t140AnswerObserved.set(t140);

                Dialog responseDialog = event.getDialog();
                if (responseDialog == null && event.getClientTransaction() != null) {
                    responseDialog = event.getClientTransaction().getDialog();
                }
                require(responseDialog != null, "200 OK arrived without dialog");
                this.dialog = responseDialog;
                Request ack = responseDialog.createAck(cseq.getSeqNumber());
                evidence.writeBytes("ack.request.sip", ack.toString().getBytes(StandardCharsets.UTF_8));
                responseDialog.sendAck(ack);
                ackSent.set(true);
                confirmed.countDown();
                evidence.event("pjsip.uas.dialog_confirmed", Map.of(
                        "t140AnswerObserved", Boolean.toString(t140)));
                return;
            }

            if (Request.BYE.equals(cseq.getMethod()) && response.getStatusCode() >= 200
                    && response.getStatusCode() < 300) {
                evidence.writeBytes("bye-200.response.sip",
                        response.toString().getBytes(StandardCharsets.UTF_8));
                byeResponse.countDown();
                evidence.event("pjsip.uas.bye_acknowledged", Map.of(
                        "status", Integer.toString(response.getStatusCode())));
            }
        } catch (Exception failure) {
            evidence.event("pjsip.uas.response_error", Map.of("error", failure.toString()));
        }
    }

    @Override
    public void processRequest(RequestEvent event) {
        evidence.event("pjsip.uas.unexpected_request", Map.of(
                "method", event.getRequest().getMethod()));
    }

    @Override
    public void processTimeout(TimeoutEvent event) {
        evidence.event("pjsip.uas.sip_timeout", Map.of(
                "server", Boolean.toString(event.isServerTransaction())));
    }

    @Override
    public void processIOException(IOExceptionEvent event) {
        evidence.event("pjsip.uas.io_error", Map.of(
                "host", String.valueOf(event.getHost()),
                "port", Integer.toString(event.getPort()),
                "transport", String.valueOf(event.getTransport())));
    }

    @Override
    public void processTransactionTerminated(TransactionTerminatedEvent event) {
    }

    @Override
    public void processDialogTerminated(DialogTerminatedEvent event) {
        evidence.event("pjsip.uas.dialog_terminated", Map.of(
                "dialog", String.valueOf(event.getDialog().getDialogId())));
    }

    @Override
    public void close() {
        try {
            stack.stop();
        } catch (Exception failure) {
            evidence.event("pjsip.uas.stop_error", Map.of("error", failure.toString()));
        }
    }

    private String sdpOffer() {
        return String.join("\r\n",
                "v=0",
                "o=baudot 2 2 IN IP4 " + HOST,
                "s=Baudot PJSIP incoming native T.140 qualification",
                "c=IN IP4 " + HOST,
                "t=0 0",
                "m=text " + mediaPort + " RTP/AVP 98",
                "a=rtpmap:98 t140/1000",
                "a=sendrecv",
                "");
    }

    private SipURI sipUri(String user, String host, int port) throws Exception {
        SipURI uri = addresses.createSipURI(user, host);
        uri.setPort(port);
        uri.setTransportParam(ListeningPoint.UDP);
        return uri;
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
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
