package org.mcc0nnell.baudot.itrs;

import javax.sip.ClientTransaction;
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

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * End-to-end local proof of the iTRS -> logical SIP URI -> Baudot/JAIN-SIP handoff.
 *
 * <p>The logical Request-URI comes from the deterministic iTRS mock. A separate
 * loose Route header points at the loopback mock VRS peer. This intentionally
 * proves that authoritative routing identity and transport/service discovery
 * are distinct facts.</p>
 */
public final class ItrsSipHandoffProbe implements SipListener, AutoCloseable {
    private static final String NUMBER = "2025550101";
    private static final String EXPECTED_LOGICAL_URI = "sip:2025550101@vrs-a.example.invalid";
    private static final String LOOPBACK = "127.0.0.1";
    private static final int CALLER_PORT = 5091;
    private static final int VRS_PORT = 5092;

    private final CountDownLatch completed = new CountDownLatch(1);
    private final AtomicBoolean inviteReceived = new AtomicBoolean();
    private final AtomicBoolean okReceived = new AtomicBoolean();
    private final AtomicBoolean ackReceived = new AtomicBoolean();
    private final AtomicBoolean logicalUriPreserved = new AtomicBoolean();

    private final SipStack callerStack;
    private final SipStack peerStack;
    private final SipProvider callerProvider;
    private final SipProvider peerProvider;
    private final AddressFactory addressFactory;
    private final HeaderFactory headerFactory;
    private final MessageFactory messageFactory;

    private ItrsSipHandoffProbe() throws Exception {
        SipFactory factory = SipFactory.getInstance();
        factory.setPathName("gov.nist");
        this.addressFactory = factory.createAddressFactory();
        this.headerFactory = factory.createHeaderFactory();
        this.messageFactory = factory.createMessageFactory();

        this.callerStack = factory.createSipStack(stackProperties("baudot-itrs-caller"));
        this.peerStack = factory.createSipStack(stackProperties("baudot-itrs-vrs-peer"));

        ListeningPoint callerPoint = callerStack.createListeningPoint(LOOPBACK, CALLER_PORT, ListeningPoint.UDP);
        ListeningPoint peerPoint = peerStack.createListeningPoint(LOOPBACK, VRS_PORT, ListeningPoint.UDP);
        this.callerProvider = callerStack.createSipProvider(callerPoint);
        this.peerProvider = peerStack.createSipProvider(peerPoint);
        callerProvider.addSipListener(this);
        peerProvider.addSipListener(this);
    }

    public static void main(String[] args) throws Exception {
        String itrsBase = args.length > 0 ? args[0] : "http://127.0.0.1:8799";
        String logicalUri = resolveLogicalSipUri(itrsBase, NUMBER);
        if (!EXPECTED_LOGICAL_URI.equals(logicalUri)) {
            throw new IllegalStateException("Unexpected logical iTRS URI: " + logicalUri);
        }

        System.out.println("RESOLVE PASS number=" + NUMBER + " logicalSipUri=" + logicalUri);

        try (ItrsSipHandoffProbe probe = new ItrsSipHandoffProbe()) {
            probe.start();
            probe.sendInvite(logicalUri);
            boolean finished = probe.completed.await(5, TimeUnit.SECONDS);
            boolean passed = finished
                    && probe.inviteReceived.get()
                    && probe.logicalUriPreserved.get()
                    && probe.okReceived.get()
                    && probe.ackReceived.get();

            System.out.println("INVITE_RECEIVED=" + probe.inviteReceived.get());
            System.out.println("LOGICAL_URI_PRESERVED=" + probe.logicalUriPreserved.get());
            System.out.println("200_OK_RECEIVED=" + probe.okReceived.get());
            System.out.println("ACK_RECEIVED=" + probe.ackReceived.get());
            System.out.println("iTRS -> Baudot -> JAIN-SIP handoff: " + (passed ? "PASS" : "FAIL"));

            if (!passed) {
                System.exit(2);
            }
        }
    }

    private void start() throws Exception {
        peerStack.start();
        callerStack.start();
    }

    private void sendInvite(String logicalUri) throws Exception {
        SipURI requestUri = (SipURI) addressFactory.createURI(logicalUri);

        Address fromAddress = addressFactory.createAddress("sip:baudot-caller@" + LOOPBACK + ":" + CALLER_PORT);
        FromHeader from = headerFactory.createFromHeader(fromAddress, randomTag());
        Address toAddress = addressFactory.createAddress(logicalUri);
        ToHeader to = headerFactory.createToHeader(toAddress, null);

        List<ViaHeader> vias = new ArrayList<>();
        ViaHeader via = headerFactory.createViaHeader(LOOPBACK, CALLER_PORT, ListeningPoint.UDP, null);
        via.setRPort();
        vias.add(via);

        CallIdHeader callId = callerProvider.getNewCallId();
        CSeqHeader cseq = headerFactory.createCSeqHeader(1L, Request.INVITE);
        MaxForwardsHeader maxForwards = headerFactory.createMaxForwardsHeader(70);

        Request invite = messageFactory.createRequest(
                requestUri, Request.INVITE, callId, cseq, from, to, vias, maxForwards);
        invite.addHeader(headerFactory.createContactHeader(fromAddress));

        SipURI routeUri = addressFactory.createSipURI(null, LOOPBACK);
        routeUri.setPort(VRS_PORT);
        routeUri.setTransportParam(ListeningPoint.UDP);
        routeUri.setLrParam();
        RouteHeader route = headerFactory.createRouteHeader(addressFactory.createAddress(routeUri));
        invite.addHeader(route);

        ClientTransaction transaction = callerProvider.getNewClientTransaction(invite);
        System.out.println("SIP SEND requestUri=" + requestUri + " route=" + routeUri);
        transaction.sendRequest();
    }

    @Override
    public void processRequest(RequestEvent event) {
        Request request = event.getRequest();
        try {
            if (Request.INVITE.equals(request.getMethod())) {
                inviteReceived.set(true);
                logicalUriPreserved.set(EXPECTED_LOGICAL_URI.equals(request.getRequestURI().toString()));
                System.out.println("VRS PEER INVITE requestUri=" + request.getRequestURI());

                ServerTransaction transaction = event.getServerTransaction();
                if (transaction == null) {
                    transaction = peerProvider.getNewServerTransaction(request);
                }
                Response ok = messageFactory.createResponse(Response.OK, request);
                ToHeader to = (ToHeader) ok.getHeader(ToHeader.NAME);
                if (to.getTag() == null) {
                    to.setTag(randomTag());
                }
                Address contact = addressFactory.createAddress("sip:mock-vrs@" + LOOPBACK + ":" + VRS_PORT);
                ContactHeader contactHeader = headerFactory.createContactHeader(contact);
                ok.addHeader(contactHeader);
                transaction.sendResponse(ok);
                return;
            }

            if (Request.ACK.equals(request.getMethod())) {
                ackReceived.set(true);
                completed.countDown();
                System.out.println("VRS PEER ACK");
            }
        } catch (Exception e) {
            e.printStackTrace(System.err);
            completed.countDown();
        }
    }

    @Override
    public void processResponse(ResponseEvent event) {
        Response response = event.getResponse();
        if (response.getStatusCode() != Response.OK) {
            return;
        }
        try {
            okReceived.set(true);
            CSeqHeader cseq = (CSeqHeader) response.getHeader(CSeqHeader.NAME);
            Request ack = event.getDialog().createAck(cseq.getSeqNumber());
            event.getDialog().sendAck(ack);
            System.out.println("CALLER 200 OK -> ACK");
        } catch (Exception e) {
            e.printStackTrace(System.err);
            completed.countDown();
        }
    }

    @Override public void processTimeout(TimeoutEvent timeoutEvent) { completed.countDown(); }
    @Override public void processIOException(IOExceptionEvent exceptionEvent) { completed.countDown(); }
    @Override public void processTransactionTerminated(TransactionTerminatedEvent event) { }
    @Override public void processDialogTerminated(DialogTerminatedEvent event) { }

    @Override
    public void close() {
        try { callerProvider.removeSipListener(this); } catch (Exception ignored) { }
        try { peerProvider.removeSipListener(this); } catch (Exception ignored) { }
        try { callerStack.stop(); } catch (Exception ignored) { }
        try { peerStack.stop(); } catch (Exception ignored) { }
    }

    private static String resolveLogicalSipUri(String base, String number) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();
        URI uri = URI.create(base + "/itrs/v1/query?number=" + number);
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(2))
                .GET()
                .build();
        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() != 200) {
            throw new IllegalStateException("iTRS mock returned " + response.statusCode() + ": " + response.body());
        }
        return jsonString(response.body(), "logicalSipUri");
    }

    private static String jsonString(String json, String field) {
        String marker = "\"" + field + "\":\"";
        int start = json.indexOf(marker);
        if (start < 0) {
            throw new IllegalArgumentException("Missing JSON field: " + field);
        }
        start += marker.length();
        int end = json.indexOf('"', start);
        if (end < 0) {
            throw new IllegalArgumentException("Unterminated JSON field: " + field);
        }
        return json.substring(start, end);
    }

    private static Properties stackProperties(String name) {
        Properties properties = new Properties();
        properties.setProperty("javax.sip.STACK_NAME", name + "-" + UUID.randomUUID().toString().replace("-", ""));
        properties.setProperty("gov.nist.javax.sip.TRACE_LEVEL", "0");
        return properties;
    }

    private static String randomTag() {
        return UUID.randomUUID().toString().replace("-", "").substring(0, 12);
    }
}
