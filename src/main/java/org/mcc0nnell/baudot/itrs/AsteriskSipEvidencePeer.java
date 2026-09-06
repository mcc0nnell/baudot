package org.mcc0nnell.baudot.itrs;

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
import javax.sip.header.CSeqHeader;
import javax.sip.header.CallIdHeader;
import javax.sip.header.ContactHeader;
import javax.sip.header.ContentTypeHeader;
import javax.sip.header.FromHeader;
import javax.sip.header.HeaderFactory;
import javax.sip.header.RouteHeader;
import javax.sip.header.ToHeader;
import javax.sip.message.MessageFactory;
import javax.sip.message.Request;
import javax.sip.message.Response;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Loopback JAIN-SIP peer for the controlled Asterisk runtime lab.
 *
 * <p>The peer verifies that Asterisk preserves the CTE-derived logical Request-URI while
 * using a separate loopback Route/outbound-proxy hop. It completes a signaling-only
 * INVITE / 200 / ACK / BYE / 200 exchange and writes deterministic JSON evidence.</p>
 */
public final class AsteriskSipEvidencePeer implements SipListener, AutoCloseable {
    private static final String LOOPBACK = "127.0.0.1";

    private final int port;
    private final String expectedRequestUri;
    private final Path evidencePath;
    private final CountDownLatch completed = new CountDownLatch(1);
    private final AtomicBoolean inviteReceived = new AtomicBoolean();
    private final AtomicBoolean ackReceived = new AtomicBoolean();
    private final AtomicBoolean byeSent = new AtomicBoolean();
    private final AtomicBoolean byeOkReceived = new AtomicBoolean();

    private final SipStack stack;
    private final SipProvider provider;
    private final AddressFactory addressFactory;
    private final HeaderFactory headerFactory;
    private final MessageFactory messageFactory;

    private volatile String requestUri;
    private volatile String routeHeader;
    private volatile String fromHeader;
    private volatile String toHeader;
    private volatile String callId;
    private volatile Throwable error;

    private AsteriskSipEvidencePeer(int port, String expectedRequestUri, Path evidencePath) throws Exception {
        this.port = port;
        this.expectedRequestUri = expectedRequestUri;
        this.evidencePath = evidencePath;

        SipFactory factory = SipFactory.getInstance();
        factory.setPathName("gov.nist");
        this.addressFactory = factory.createAddressFactory();
        this.headerFactory = factory.createHeaderFactory();
        this.messageFactory = factory.createMessageFactory();

        Properties properties = new Properties();
        properties.setProperty("javax.sip.STACK_NAME",
                "baudot-asterisk-peer-" + port + "-" + UUID.randomUUID().toString().replace("-", ""));
        properties.setProperty("gov.nist.javax.sip.TRACE_LEVEL", "0");
        this.stack = factory.createSipStack(properties);
        ListeningPoint point = stack.createListeningPoint(LOOPBACK, port, ListeningPoint.UDP);
        this.provider = stack.createSipProvider(point);
        this.provider.addSipListener(this);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println("usage: AsteriskSipEvidencePeer <port> <expected-request-uri> <evidence-json>");
            System.exit(64);
        }
        int port = Integer.parseInt(args[0]);
        String expected = args[1];
        Path evidence = Path.of(args[2]);

        try (AsteriskSipEvidencePeer peer = new AsteriskSipEvidencePeer(port, expected, evidence)) {
            peer.stack.start();
            System.out.printf("Asterisk JAIN-SIP evidence peer listening on %s:%d expected=%s%n",
                    LOOPBACK, port, expected);
            boolean finished = peer.completed.await(15, TimeUnit.SECONDS);
            boolean passed = finished
                    && peer.error == null
                    && peer.inviteReceived.get()
                    && peer.ackReceived.get()
                    && peer.byeSent.get()
                    && peer.byeOkReceived.get()
                    && expected.equals(peer.requestUri);
            peer.writeEvidence(passed);
            System.out.printf("Asterisk -> JAIN-SIP signaling peer: %s requestUri=%s%n",
                    passed ? "PASS" : "FAIL", peer.requestUri);
            if (!passed) {
                System.exit(2);
            }
        }
    }

    @Override
    public void processRequest(RequestEvent event) {
        Request request = event.getRequest();
        try {
            if (Request.INVITE.equals(request.getMethod())) {
                inviteReceived.set(true);
                requestUri = request.getRequestURI().toString();
                routeHeader = headerValue(request, RouteHeader.NAME);
                fromHeader = headerValue(request, FromHeader.NAME);
                toHeader = headerValue(request, ToHeader.NAME);
                callId = headerValue(request, CallIdHeader.NAME);

                ServerTransaction transaction = event.getServerTransaction();
                if (transaction == null) {
                    transaction = provider.getNewServerTransaction(request);
                }

                Response ok = messageFactory.createResponse(Response.OK, request);
                ToHeader to = (ToHeader) ok.getHeader(ToHeader.NAME);
                if (to.getTag() == null) {
                    to.setTag(randomTag());
                }
                Address contactAddress = addressFactory.createAddress(
                        "sip:baudot-evidence@" + LOOPBACK + ":" + port);
                ContactHeader contact = headerFactory.createContactHeader(contactAddress);
                ok.addHeader(contact);

                String sdp = "v=0\r\n"
                        + "o=baudot 1 1 IN IP4 127.0.0.1\r\n"
                        + "s=Baudot signaling-only peer\r\n"
                        + "c=IN IP4 127.0.0.1\r\n"
                        + "t=0 0\r\n"
                        + "m=audio 40000 RTP/AVP 0\r\n"
                        + "a=rtpmap:0 PCMU/8000\r\n"
                        + "a=sendrecv\r\n";
                ContentTypeHeader contentType = headerFactory.createContentTypeHeader("application", "sdp");
                ok.setContent(sdp, contentType);
                transaction.sendResponse(ok);
                return;
            }

            if (Request.ACK.equals(request.getMethod())) {
                ackReceived.set(true);
                Dialog dialog = event.getDialog();
                if (dialog == null) {
                    throw new IllegalStateException("ACK arrived without dialog");
                }
                Request bye = dialog.createRequest(Request.BYE);
                ClientTransaction clientTransaction = provider.getNewClientTransaction(bye);
                dialog.sendRequest(clientTransaction);
                byeSent.set(true);
                return;
            }

            if (Request.BYE.equals(request.getMethod())) {
                ServerTransaction transaction = event.getServerTransaction();
                if (transaction == null) {
                    transaction = provider.getNewServerTransaction(request);
                }
                transaction.sendResponse(messageFactory.createResponse(Response.OK, request));
                completed.countDown();
            }
        } catch (Exception e) {
            fail(e);
        }
    }

    @Override
    public void processResponse(ResponseEvent event) {
        Response response = event.getResponse();
        try {
            CSeqHeader cseq = (CSeqHeader) response.getHeader(CSeqHeader.NAME);
            if (cseq != null && Request.BYE.equals(cseq.getMethod())
                    && response.getStatusCode() >= 200 && response.getStatusCode() < 300) {
                byeOkReceived.set(true);
                completed.countDown();
            }
        } catch (Exception e) {
            fail(e);
        }
    }

    @Override public void processTimeout(TimeoutEvent event) { fail(new IllegalStateException("SIP timeout")); }
    @Override public void processIOException(IOExceptionEvent event) { fail(new IllegalStateException("SIP I/O error")); }
    @Override public void processTransactionTerminated(TransactionTerminatedEvent event) { }
    @Override public void processDialogTerminated(DialogTerminatedEvent event) { }

    private void fail(Throwable throwable) {
        error = throwable;
        throwable.printStackTrace(System.err);
        completed.countDown();
    }

    private void writeEvidence(boolean passed) throws Exception {
        Path parent = evidencePath.getParent();
        if (parent != null) Files.createDirectories(parent);
        String json = "{"
                + "\"schema\":\"baudot.asterisk-sip-evidence@1\","
                + "\"passed\":" + passed + ","
                + "\"expectedRequestUri\":" + jsonString(expectedRequestUri) + ","
                + "\"requestUri\":" + jsonString(requestUri) + ","
                + "\"inviteReceived\":" + inviteReceived.get() + ","
                + "\"ackReceived\":" + ackReceived.get() + ","
                + "\"byeSent\":" + byeSent.get() + ","
                + "\"byeOkReceived\":" + byeOkReceived.get() + ","
                + "\"routeHeader\":" + jsonString(routeHeader) + ","
                + "\"fromHeader\":" + jsonString(fromHeader) + ","
                + "\"toHeader\":" + jsonString(toHeader) + ","
                + "\"callId\":" + jsonString(callId) + ","
                + "\"error\":" + jsonString(error == null ? null : error.toString())
                + "}\n";
        Files.writeString(evidencePath, json, StandardCharsets.UTF_8);
    }

    private static String headerValue(Request request, String name) {
        Object header = request.getHeader(name);
        return header == null ? null : header.toString().trim();
    }

    private static String jsonString(String value) {
        if (value == null) return "null";
        return "\"" + value.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\r", "\\r")
                .replace("\n", "\\n") + "\"";
    }

    private static String randomTag() {
        return UUID.randomUUID().toString().replace("-", "").substring(0, 12);
    }

    @Override
    public void close() {
        try { provider.removeSipListener(this); } catch (Exception ignored) { }
        try { stack.stop(); } catch (Exception ignored) { }
    }
}
