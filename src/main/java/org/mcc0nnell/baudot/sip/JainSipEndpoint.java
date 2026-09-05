package org.mcc0nnell.baudot.sip;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
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
 * Thin JAIN SIP adapter used by the first executable signaling slice.
 * It deliberately exposes no media or T.140 semantics.
 */
public final class JainSipEndpoint implements SipListener, AutoCloseable {
    private static final String HOST = "127.0.0.1";

    private final String name;
    private final String user;
    private final int port;
    private final SipTrace trace;
    private final String inviteAnswerSdp;
    private final SipStack stack;
    private final SipProvider provider;
    private final AddressFactory addressFactory;
    private final HeaderFactory headerFactory;
    private final MessageFactory messageFactory;
    private final CountDownLatch completed = new CountDownLatch(1);
    private final AtomicBoolean inviteAccepted = new AtomicBoolean();
    private final AtomicReference<Throwable> failure = new AtomicReference<>();

    public JainSipEndpoint(String name, String user, int port, SipTrace trace) throws Exception {
        this(name, user, port, trace, null);
    }

    public JainSipEndpoint(String name, String user, int port, SipTrace trace, String inviteAnswerSdp)
            throws Exception {
        this.name = name;
        this.user = user;
        this.port = port;
        this.trace = trace;
        this.inviteAnswerSdp = inviteAnswerSdp;

        SipFactory factory = SipFactory.getInstance();
        factory.setPathName("gov.nist");

        Properties properties = new Properties();
        properties.setProperty("javax.sip.STACK_NAME", "baudot-" + name + "-" + port);
        properties.setProperty("javax.sip.AUTOMATIC_DIALOG_SUPPORT", "on");
        properties.setProperty("gov.nist.javax.sip.TRACE_LEVEL", "0");
        properties.setProperty("gov.nist.javax.sip.REENTRANT_LISTENER", "true");

        this.stack = factory.createSipStack(properties);
        this.addressFactory = factory.createAddressFactory();
        this.headerFactory = factory.createHeaderFactory();
        this.messageFactory = factory.createMessageFactory();

        ListeningPoint listeningPoint = stack.createListeningPoint(HOST, port, ListeningPoint.UDP);
        this.provider = stack.createSipProvider(listeningPoint);
        provider.addSipListener(this);
        stack.start();
    }

    public void invite(String peerUser, int peerPort) throws Exception {
        invite(peerUser, peerPort, null);
    }

    public void invite(String peerUser, int peerPort, String sdpOffer) throws Exception {
        SipURI requestUri = addressFactory.createSipURI(peerUser, HOST);
        requestUri.setPort(peerPort);

        CallIdHeader callId = provider.getNewCallId();
        CSeqHeader cseq = headerFactory.createCSeqHeader(1L, Request.INVITE);

        Address fromAddress = addressFactory.createAddress("sip:" + user + "@" + HOST + ":" + port);
        FromHeader from = headerFactory.createFromHeader(fromAddress, name + "-from");
        Address toAddress = addressFactory.createAddress("sip:" + peerUser + "@" + HOST + ":" + peerPort);
        ToHeader to = headerFactory.createToHeader(toAddress, null);

        ArrayList<ViaHeader> via = new ArrayList<>();
        via.add(headerFactory.createViaHeader(HOST, port, ListeningPoint.UDP, null));
        MaxForwardsHeader maxForwards = headerFactory.createMaxForwardsHeader(70);

        Request request = messageFactory.createRequest(
                requestUri, Request.INVITE, callId, cseq, from, to, via, maxForwards);
        request.addHeader(contactHeader());
        if (sdpOffer != null) {
            request.setContent(sdpOffer.getBytes(StandardCharsets.UTF_8), sdpContentType());
        }

        ClientTransaction transaction = provider.getNewClientTransaction(request);
        trace.sent(name, Request.INVITE);
        transaction.sendRequest();
    }

    public boolean awaitCompletion(Duration timeout) throws InterruptedException {
        boolean done = completed.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        Throwable problem = failure.get();
        if (problem != null) {
            throw new AssertionError("SIP endpoint failed", problem);
        }
        return done;
    }

    @Override
    public void processRequest(RequestEvent event) {
        Request request = event.getRequest();
        String method = request.getMethod();
        trace.received(name, method);

        try {
            if (Request.ACK.equals(method)) {
                return;
            }

            ServerTransaction transaction = event.getServerTransaction();
            if (transaction == null) {
                transaction = provider.getNewServerTransaction(request);
            }

            if (Request.INVITE.equals(method)) {
                if (request.getRawContent() != null) {
                    trace.sdpOfferReceived(name, SdpDescription.parse(request.getRawContent()));
                }
                sendResponse(transaction, request, Response.TRYING, null);
                sendResponse(transaction, request, Response.RINGING, null);
                sendResponse(transaction, request, Response.OK, inviteAnswerSdp);
            } else if (Request.BYE.equals(method)) {
                sendResponse(transaction, request, Response.OK, null);
            }
        } catch (Exception e) {
            fail(e);
        }
    }

    @Override
    public void processResponse(ResponseEvent event) {
        Response response = event.getResponse();
        CSeqHeader cseq = (CSeqHeader) response.getHeader(CSeqHeader.NAME);
        String method = cseq.getMethod();
        int status = response.getStatusCode();
        trace.received(name, status + " " + method);

        try {
            if (status == Response.OK && Request.INVITE.equals(method)
                    && inviteAccepted.compareAndSet(false, true)) {
                if (response.getRawContent() != null) {
                    trace.sdpAnswerReceived(name, SdpDescription.parse(response.getRawContent()));
                }

                Dialog dialog = event.getDialog();
                if (dialog == null && event.getClientTransaction() != null) {
                    dialog = event.getClientTransaction().getDialog();
                }
                if (dialog == null) {
                    throw new IllegalStateException("200 INVITE response did not establish a dialog");
                }

                Request ack = dialog.createAck(cseq.getSeqNumber());
                trace.sent(name, Request.ACK);
                dialog.sendAck(ack);

                Request bye = dialog.createRequest(Request.BYE);
                ClientTransaction byeTransaction = provider.getNewClientTransaction(bye);
                trace.sent(name, Request.BYE);
                dialog.sendRequest(byeTransaction);
            } else if (status == Response.OK && Request.BYE.equals(method)) {
                completed.countDown();
            }
        } catch (Exception e) {
            fail(e);
        }
    }

    private void sendResponse(ServerTransaction transaction, Request request, int status, String sdpBody)
            throws Exception {
        Response response = messageFactory.createResponse(status, request);
        if (status >= Response.RINGING) {
            ToHeader to = (ToHeader) response.getHeader(ToHeader.NAME);
            if (to.getTag() == null) {
                to.setTag(name + "-to");
            }
        }
        if (status == Response.OK && Request.INVITE.equals(request.getMethod())) {
            response.addHeader(contactHeader());
            if (sdpBody != null) {
                response.setContent(sdpBody.getBytes(StandardCharsets.UTF_8), sdpContentType());
            }
        }
        trace.sent(name, status + " " + request.getMethod());
        transaction.sendResponse(response);
    }

    private ContactHeader contactHeader() throws Exception {
        Address contactAddress = addressFactory.createAddress("sip:" + user + "@" + HOST + ":" + port);
        return headerFactory.createContactHeader(contactAddress);
    }

    private ContentTypeHeader sdpContentType() throws Exception {
        return headerFactory.createContentTypeHeader("application", "sdp");
    }

    private void fail(Throwable problem) {
        failure.compareAndSet(null, problem);
        completed.countDown();
    }

    @Override
    public void processTimeout(TimeoutEvent timeoutEvent) {
        fail(new IllegalStateException("SIP transaction timed out: " + timeoutEvent));
    }

    @Override
    public void processIOException(IOExceptionEvent exceptionEvent) {
        fail(new IllegalStateException("SIP I/O failure: " + exceptionEvent));
    }

    @Override
    public void processTransactionTerminated(TransactionTerminatedEvent event) {
        // Transaction lifetime is observable through protocol events for this slice.
    }

    @Override
    public void processDialogTerminated(DialogTerminatedEvent event) {
        // Dialog teardown is proven by the BYE/200 exchange in this slice.
    }

    @Override
    public void close() {
        try {
            provider.removeSipListener(this);
        } catch (Exception ignored) {
            // Best-effort cleanup for a local test endpoint.
        }
        stack.stop();
    }
}
