package org.mcc0nnell.baudot.harness;

import org.mcc0nnell.baudot.tilden.BaudotRoute;
import org.mcc0nnell.baudot.tilden.TildenSelectionAdapter;

import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

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
 * First live Tilden -> Baudot lane.
 *
 * <p>The Tilden selection decides the exact SIP request URI. Baudot then owns signaling evidence
 * and uses the Tilden selection id as the runtime correlation id.</p>
 */
public final class TildenSipCallMain implements SipListener, AutoCloseable {
    private static final String SCENARIO = "TILDEN-HANDOFF-001";

    private final BaudotRoute route;
    private final EvidenceRecorder evidence;
    private final CountDownLatch established = new CountDownLatch(1);
    private final SipStack stack;
    private final SipProvider provider;
    private final AddressFactory addressFactory;
    private final HeaderFactory headerFactory;
    private final MessageFactory messageFactory;
    private final String bindIp;
    private final int bindPort;
    private ClientTransaction inviteTransaction;

    private TildenSipCallMain(BaudotRoute route, EvidenceRecorder evidence) throws Exception {
        this.route = route;
        this.evidence = evidence;
        this.bindIp = env("BAUDOT_TILDEN_CALLER_IP", "127.0.0.1");
        this.bindPort = envInt("BAUDOT_TILDEN_CALLER_PORT", 5087);

        SipFactory factory = SipFactory.getInstance();
        factory.setPathName("gov.nist");

        Properties properties = new Properties();
        properties.setProperty("javax.sip.STACK_NAME", "baudot-tilden-" + safe(route.selectionId()));
        properties.setProperty("gov.nist.javax.sip.TRACE_LEVEL", "0");
        this.stack = factory.createSipStack(properties);
        this.addressFactory = factory.createAddressFactory();
        this.headerFactory = factory.createHeaderFactory();
        this.messageFactory = factory.createMessageFactory();

        ListeningPoint point = stack.createListeningPoint(bindIp, bindPort, ListeningPoint.UDP);
        this.provider = stack.createSipProvider(point);
        this.provider.addSipListener(this);
    }

    public static void main(String[] args) {
        int exit = 2;
        if (args.length != 1) {
            System.err.println("usage: TildenSipCallMain <selection.json>");
            System.exit(64);
        }

        try {
            BaudotRoute route = new TildenSelectionAdapter().read(Path.of(args[0]));
            Path evidenceRoot = Path.of(env("BAUDOT_EVIDENCE_DIR", "target/evidence"));
            Duration timeout = Duration.ofMillis(envInt("BAUDOT_TIMEOUT_MS", 5000));

            try (EvidenceRecorder evidence = new EvidenceRecorder(
                    evidenceRoot, SCENARIO, route.selectionId(), "caller");
                 TildenSipCallMain caller = new TildenSipCallMain(route, evidence)) {

                evidence.event("tilden.selection.accepted", Map.of(
                        "selection.id", route.selectionId(),
                        "target", route.target(),
                        "selected.endpoint", route.selectedEndpoint(),
                        "resolution.digest", route.resolutionDigest(),
                        "request.digest", route.requestDigest()));

                caller.start();
                caller.sendInvite();
                boolean dialogEstablished = caller.await(timeout);

                evidence.result(Map.of(
                        "tilden.selection.id", route.selectionId(),
                        "tilden.selected.endpoint", route.selectedEndpoint(),
                        "tilden.target", route.target(),
                        "signaling.dialog.established", Boolean.toString(dialogEstablished),
                        "runtime.claim", "selected-route-signaling-only"));

                exit = dialogEstablished ? 0 : 3;
            }
        } catch (Exception e) {
            e.printStackTrace(System.err);
            exit = 2;
        }

        System.exit(exit);
    }

    private void start() throws Exception {
        stack.start();
        evidence.event("sip.endpoint.ready", Map.of(
                "bind", bindIp + ":" + bindPort,
                "transport", "udp"));
    }

    private void sendInvite() throws Exception {
        URI parsed = addressFactory.createURI(route.selectedEndpoint());
        if (!(parsed instanceof SipURI requestUri)) {
            throw new IllegalArgumentException("selectedEndpoint is not a SIP URI: " + route.selectedEndpoint());
        }

        String transport = requestUri.getTransportParam();
        if (requestUri.isSecure()) {
            throw new IllegalArgumentException("sips selectedEndpoint is not supported by TILDEN-HANDOFF-001");
        }
        if (transport != null && !ListeningPoint.UDP.equalsIgnoreCase(transport)) {
            throw new IllegalArgumentException(
                    "TILDEN-HANDOFF-001 supports UDP SIP endpoints only; got transport=" + transport);
        }

        Address fromAddress = addressFactory.createAddress(localUri("baudot"));
        FromHeader from = headerFactory.createFromHeader(fromAddress, randomTag());
        ToHeader to = headerFactory.createToHeader(addressFactory.createAddress(requestUri), null);

        List<ViaHeader> vias = new ArrayList<>();
        ViaHeader via = headerFactory.createViaHeader(bindIp, bindPort, ListeningPoint.UDP, null);
        via.setRPort();
        vias.add(via);

        CallIdHeader callId = provider.getNewCallId();
        CSeqHeader cseq = headerFactory.createCSeqHeader(1L, Request.INVITE);
        MaxForwardsHeader maxForwards = headerFactory.createMaxForwardsHeader(70);

        Request invite = messageFactory.createRequest(
                requestUri, Request.INVITE, callId, cseq, from, to, vias, maxForwards);
        invite.addHeader(headerFactory.createContactHeader(fromAddress));

        ContentTypeHeader contentType = headerFactory.createContentTypeHeader("application", "sdp");
        invite.setContent(inactiveSdp(bindIp), contentType);

        inviteTransaction = provider.getNewClientTransaction(invite);
        evidence.event("sip.invite.sent", Map.of(
                "callId", callId.getCallId(),
                "requestUri", requestUri.toString(),
                "selection.id", route.selectionId()));
        inviteTransaction.sendRequest();
    }

    private boolean await(Duration timeout) throws InterruptedException {
        return established.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    @Override
    public void processResponse(ResponseEvent event) {
        Response response = event.getResponse();
        CSeqHeader cseq = (CSeqHeader) response.getHeader(CSeqHeader.NAME);
        if (cseq == null || !Request.INVITE.equals(cseq.getMethod())) {
            return;
        }
        evidence.event("sip.response.received", Map.of(
                "status", Integer.toString(response.getStatusCode()),
                "selection.id", route.selectionId()));
        if (response.getStatusCode() != Response.OK) {
            return;
        }

        try {
            Dialog dialog = event.getDialog();
            if (dialog == null && inviteTransaction != null) {
                dialog = inviteTransaction.getDialog();
            }
            if (dialog == null) {
                throw new IllegalStateException("200 OK arrived without a SIP dialog");
            }
            Request ack = dialog.createAck(cseq.getSeqNumber());
            dialog.sendAck(ack);
            established.countDown();
            evidence.event("sip.dialog.established", Map.of(
                    "selection.id", route.selectionId(),
                    "selected.endpoint", route.selectedEndpoint()));
        } catch (Exception e) {
            evidence.event("sip.response.error", Map.of("error", e.toString()));
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
        evidence.event("sip.transaction.terminated", Map.of(
                "server", Boolean.toString(event.isServerTransaction())));
    }

    @Override
    public void processDialogTerminated(DialogTerminatedEvent event) {
        evidence.event("sip.dialog.terminated", Map.of(
                "dialog", String.valueOf(event.getDialog().getDialogId())));
    }

    private String localUri(String user) throws Exception {
        SipURI uri = addressFactory.createSipURI(user, bindIp);
        uri.setPort(bindPort);
        uri.setTransportParam(ListeningPoint.UDP);
        return uri.toString();
    }

    private static String inactiveSdp(String ip) {
        return "v=0\r\n"
                + "o=baudot 0 0 IN IP4 " + ip + "\r\n"
                + "s=Tilden selected route probe\r\n"
                + "c=IN IP4 " + ip + "\r\n"
                + "t=0 0\r\n"
                + "m=audio 9 RTP/AVP 0\r\n"
                + "a=inactive\r\n";
    }

    private static String randomTag() {
        return UUID.randomUUID().toString().replace("-", "").substring(0, 12);
    }

    private static String safe(String value) {
        String safe = value.replaceAll("[^A-Za-z0-9]", "");
        return safe.isBlank() ? "selection" : safe;
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }

    private static int envInt(String name, int fallback) {
        return Integer.parseInt(env(name, Integer.toString(fallback)));
    }

    @Override
    public void close() {
        try {
            stack.stop();
        } catch (Exception e) {
            evidence.event("sip.stop.error", Map.of("error", e.toString()));
        }
    }
}
