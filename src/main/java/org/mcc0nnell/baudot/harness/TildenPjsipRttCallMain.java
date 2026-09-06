package org.mcc0nnell.baudot.harness;

import org.mcc0nnell.baudot.tilden.BaudotRoute;
import org.mcc0nnell.baudot.tilden.TildenSelectionAdapter;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.UUID;
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
import javax.sip.address.URI;
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
 * TILDEN-HANDOFF-002: consume a Tilden-selected SIP endpoint and prove native RTT readiness.
 *
 * <p>Tilden owns why the endpoint was selected. Baudot begins at the accepted selection,
 * sends the exact selected URI as the SIP Request-URI, and keeps signaling, T.140 readiness,
 * and release ordering as independent evidence. The external Baudot Python reference gate is
 * the only component allowed to publish rttReady=true.</p>
 */
public final class TildenPjsipRttCallMain implements SipListener, AutoCloseable {
    private static final String SCENARIO = "TILDEN-HANDOFF-002";
    private static final Duration SIP_TIMEOUT = Duration.ofSeconds(8);
    private static final Duration READINESS_TIMEOUT = Duration.ofSeconds(8);

    private final BaudotRoute route;
    private final int localPort;
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

    private TildenPjsipRttCallMain(
            BaudotRoute route,
            int localPort,
            int mediaPort,
            Path readyFile,
            EvidenceRecorder evidence) throws Exception {
        this.route = route;
        this.localPort = localPort;
        this.mediaPort = mediaPort;
        this.readyFile = readyFile;
        this.evidence = evidence;

        SipFactory factory = SipFactory.getInstance();
        factory.setPathName("gov.nist");
        Properties properties = new Properties();
        properties.setProperty("javax.sip.STACK_NAME", "baudot-tilden-rtt-" + safe(route.selectionId()));
        properties.setProperty("gov.nist.javax.sip.TRACE_LEVEL", "0");
        this.stack = factory.createSipStack(properties);
        this.addresses = factory.createAddressFactory();
        this.headers = factory.createHeaderFactory();
        this.messages = factory.createMessageFactory();
        ListeningPoint point = stack.createListeningPoint("127.0.0.1", localPort, ListeningPoint.UDP);
        this.provider = stack.createSipProvider(point);
        this.provider.addSipListener(this);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("usage: TildenPjsipRttCallMain <selection.json>");
            System.exit(64);
        }

        BaudotRoute route = new TildenSelectionAdapter().read(Path.of(args[0]));
        int localPort = envInt("BAUDOT_TILDEN_RTT_CALLER_PORT", 5321);
        int mediaPort = envInt("BAUDOT_TILDEN_RTT_MEDIA_PORT", 5323);
        Path root = Path.of(env("BAUDOT_EVIDENCE_DIR", "target/evidence-external"));
        Path readyFile = Path.of(env(
                "BAUDOT_RTT_READY_FILE",
                root.resolve(SCENARIO).resolve(route.selectionId()).resolve("readiness/rtt-ready.json").toString()));

        try (EvidenceRecorder evidence = new EvidenceRecorder(root, SCENARIO, route.selectionId(), "jain-caller");
             TildenPjsipRttCallMain call =
                     new TildenPjsipRttCallMain(route, localPort, mediaPort, readyFile, evidence)) {
            evidence.event("tilden.selection.accepted", Map.of(
                    "selection.id", route.selectionId(),
                    "target", route.target(),
                    "selected.endpoint", route.selectedEndpoint(),
                    "resolution.digest", route.resolutionDigest(),
                    "request.digest", route.requestDigest()));

            call.start();
            call.sendInvite();
            require(call.confirmed.await(SIP_TIMEOUT.toMillis(), TimeUnit.MILLISECONDS),
                    "Tilden-selected PJSIP dialog did not confirm");
            require(call.awaitReadinessToken(READINESS_TIMEOUT),
                    "independent RTT readiness token was not published");
            call.sendBye();
            require(call.byeResponse.await(SIP_TIMEOUT.toMillis(), TimeUnit.MILLISECONDS),
                    "Tilden-selected PJSIP endpoint did not acknowledge release");

            boolean releaseAfterReadiness = call.readinessObservedAt.get() > 0
                    && call.byeSentAt.get() > call.readinessObservedAt.get();
            boolean pass = call.t140AnswerObserved.get()
                    && call.ackSent.get()
                    && call.readinessTokenObserved.get()
                    && call.byeSent.get()
                    && releaseAfterReadiness;

            evidence.result(Map.ofEntries(
                    Map.entry("scenario.id", SCENARIO),
                    Map.entry("tilden.selection.id", route.selectionId()),
                    Map.entry("tilden.selected.endpoint", route.selectedEndpoint()),
                    Map.entry("tilden.target", route.target()),
                    Map.entry("caller.implementation", "JAIN-SIP"),
                    Map.entry("callee.implementation", "pjsip/pjproject-2.17"),
                    Map.entry("signaling.dialog.established", Boolean.toString(call.dialog != null)),
                    Map.entry("sip.t140.answerObserved", Boolean.toString(call.t140AnswerObserved.get())),
                    Map.entry("sip.ack.sent", Boolean.toString(call.ackSent.get())),
                    Map.entry("rtt.readinessToken.observed", Boolean.toString(call.readinessTokenObserved.get())),
                    Map.entry("rttReady", "EXTERNAL_BAUDOT_REFERENCE_TOKEN"),
                    Map.entry("call.bye.sent", Boolean.toString(call.byeSent.get())),
                    Map.entry("call.bye.afterReadiness", Boolean.toString(releaseAfterReadiness)),
                    Map.entry("runtime.claim", "selected-route-native-rtt-ready"),
                    Map.entry("scenario.result", pass ? "OBSERVED" : "INCOMPLETE"),
                    Map.entry("claimBoundary",
                            "Tilden-selected controlled SIP plus native RTT readiness; no SIP/RTP/RFC4103/T140/PJSIP/Tilden/VRS conformance claim")));
            require(pass, "Tilden-selected native RTT observation was incomplete");
        }
    }

    private void start() throws Exception {
        stack.start();
        evidence.event("sip.endpoint.ready", Map.of(
                "bind", "127.0.0.1:" + localPort,
                "transport", "udp",
                "offeredMedia", "127.0.0.1:" + mediaPort));
    }

    private void sendInvite() throws Exception {
        SipURI requestUri = selectedSipUri();
        Address fromAddress = addresses.createAddress(localUri("baudot"));
        Address toAddress = addresses.createAddress(requestUri);
        FromHeader from = headers.createFromHeader(fromAddress, randomTag());
        ToHeader to = headers.createToHeader(toAddress, null);
        List<ViaHeader> vias = new ArrayList<>();
        ViaHeader via = headers.createViaHeader("127.0.0.1", localPort, ListeningPoint.UDP, null);
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
        evidence.event("sip.invite.sent", Map.of(
                "callId", callId.getCallId(),
                "requestUri", requestUri.toString(),
                "selection.id", route.selectionId()));

        ClientTransaction transaction = provider.getNewClientTransaction(invite);
        transaction.sendRequest();
    }

    private boolean awaitReadinessToken(Duration timeout) throws Exception {
        long deadline = System.nanoTime() + timeout.toNanos();
        while (System.nanoTime() < deadline) {
            if (Files.isRegularFile(readyFile)) {
                byte[] token = Files.readAllBytes(readyFile);
                evidence.writeBytes("rtt-ready.token.json", token);
                readinessObservedAt.set(System.nanoTime());
                readinessTokenObserved.set(true);
                evidence.event("rtt.readiness_token.observed", Map.of(
                        "bytes", Integer.toString(token.length),
                        "authority", "external-baudot-reference",
                        "classification", "opaque-token-presence",
                        "selection.id", route.selectionId()));
                return true;
            }
            Thread.sleep(25L);
        }
        evidence.event("rtt.readiness_token.timeout", Map.of(
                "timeoutMs", Long.toString(timeout.toMillis()),
                "selection.id", route.selectionId()));
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
        evidence.event("sip.bye.sent", Map.of(
                "afterReadiness", Boolean.toString(byeSentAt.get() > readinessObservedAt.get()),
                "selection.id", route.selectionId()));
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
                evidence.event("sip.dialog.established", Map.of(
                        "t140AnswerObserved", Boolean.toString(t140),
                        "selected.endpoint", route.selectedEndpoint(),
                        "selection.id", route.selectionId()));
                return;
            }

            if (Request.BYE.equals(cseq.getMethod()) && response.getStatusCode() >= 200
                    && response.getStatusCode() < 300) {
                evidence.writeBytes("bye-200.response.sip",
                        response.toString().getBytes(StandardCharsets.UTF_8));
                byeResponse.countDown();
                evidence.event("sip.bye.acknowledged", Map.of(
                        "status", Integer.toString(response.getStatusCode()),
                        "selection.id", route.selectionId()));
            }
        } catch (Exception failure) {
            evidence.event("sip.response.error", Map.of("error", failure.toString()));
        }
    }

    @Override
    public void processRequest(RequestEvent event) {
        evidence.event("sip.unexpected.request", Map.of("method", event.getRequest().getMethod()));
    }

    @Override
    public void processTimeout(TimeoutEvent event) {
        evidence.event("sip.timeout", Map.of("server", Boolean.toString(event.isServerTransaction())));
    }

    @Override
    public void processIOException(IOExceptionEvent event) {
        evidence.event("sip.io_error", Map.of(
                "host", String.valueOf(event.getHost()),
                "port", Integer.toString(event.getPort()),
                "transport", String.valueOf(event.getTransport())));
    }

    @Override
    public void processTransactionTerminated(TransactionTerminatedEvent event) {
    }

    @Override
    public void processDialogTerminated(DialogTerminatedEvent event) {
        evidence.event("sip.dialog.terminated", Map.of(
                "dialog", String.valueOf(event.getDialog().getDialogId())));
    }

    @Override
    public void close() {
        try {
            stack.stop();
        } catch (Exception failure) {
            evidence.event("sip.stop.error", Map.of("error", failure.toString()));
        }
    }

    private SipURI selectedSipUri() throws Exception {
        URI parsed = addresses.createURI(route.selectedEndpoint());
        if (!(parsed instanceof SipURI requestUri)) {
            throw new IllegalArgumentException("selectedEndpoint is not a SIP URI: " + route.selectedEndpoint());
        }
        if (requestUri.isSecure()) {
            throw new IllegalArgumentException("sips selectedEndpoint is not supported by TILDEN-HANDOFF-002");
        }
        String transport = requestUri.getTransportParam();
        if (transport != null && !ListeningPoint.UDP.equalsIgnoreCase(transport)) {
            throw new IllegalArgumentException(
                    "TILDEN-HANDOFF-002 supports UDP SIP endpoints only; got transport=" + transport);
        }
        return requestUri;
    }

    private String localUri(String user) throws Exception {
        SipURI uri = addresses.createSipURI(user, "127.0.0.1");
        uri.setPort(localPort);
        uri.setTransportParam(ListeningPoint.UDP);
        return uri.toString();
    }

    private String sdpOffer() {
        return String.join("\r\n",
                "v=0",
                "o=baudot 3 3 IN IP4 127.0.0.1",
                "s=Baudot Tilden-selected native RTT handoff",
                "c=IN IP4 127.0.0.1",
                "t=0 0",
                "m=text " + mediaPort + " RTP/AVP 98",
                "a=rtpmap:98 t140/1000",
                "a=sendrecv",
                "");
    }

    private static String randomTag() {
        return UUID.randomUUID().toString().replace("-", "").substring(0, 12);
    }

    private static String safe(String value) {
        String safe = value.replaceAll("[^A-Za-z0-9]", "");
        return safe.isBlank() ? "selection" : safe;
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
