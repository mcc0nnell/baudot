package org.mcc0nnell.baudot.harness;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import javax.sip.ListeningPoint;
import javax.sip.SipFactory;
import javax.sip.address.Address;
import javax.sip.address.AddressFactory;
import javax.sip.address.SipURI;
import javax.sip.header.CSeqHeader;
import javax.sip.header.CallIdHeader;
import javax.sip.header.ContentTypeHeader;
import javax.sip.header.FromHeader;
import javax.sip.header.HeaderFactory;
import javax.sip.header.MaxForwardsHeader;
import javax.sip.header.ToHeader;
import javax.sip.header.ViaHeader;
import javax.sip.message.Message;
import javax.sip.message.MessageFactory;
import javax.sip.message.Request;
import javax.sip.message.Response;

/**
 * First executable gate for BAUDOT-INTEROP-003.
 *
 * This is intentionally a message/correlation proof, not a live media or
 * full-dialog conformance test. It uses JAIN SIP message objects to preserve
 * the identity of overlapping in-dialog INVITEs, exercises 491 glare ordering,
 * binds an externally supplied SDP answer to the intended request, and proves
 * that stale SDP can be detected by hash even when signaling returns 200.
 */
public final class ReinviteCorrelationProbe {
    private static final String SCENARIO = "BAUDOT-INTEROP-003";
    private static final String CORRELATION = "jain-message-correlation-v1";
    private static final String CALL_ID = "baudot-interop-003@127.0.0.1";
    private static final String FROM_TAG = "baudot-caller";
    private static final String TO_TAG = "baudot-callee";

    private ReinviteCorrelationProbe() {
    }

    public static void main(String[] args) throws Exception {
        Path evidenceRoot = Path.of(env("BAUDOT_EVIDENCE_DIR", "target/evidence"));
        Factories factories = Factories.create();

        Exchange first = exchange(factories, 2, 41002, 42002, "z9hG4bK-baudot-2");
        Exchange second = exchange(factories, 3, 41003, 42003, "z9hG4bK-baudot-3");
        Exchange external = exchange(factories, 4, 41004, 43004, "z9hG4bK-baudot-4");
        Exchange stale = exchange(factories, 5, 41005, 42005, "z9hG4bK-baudot-5");

        try (EvidenceRecorder evidence = new EvidenceRecorder(
                evidenceRoot, SCENARIO, CORRELATION, "jain-message-proof")) {
            preserveRequest(evidence, first);
            preserveRequest(evidence, second);
            preserveRequest(evidence, external);
            preserveRequest(evidence, stale);

            // Model glare deterministically: the later overlapping INVITE is
            // classified first as 491, then the earlier pending INVITE completes.
            Response second491 = factories.messages().createResponse(Response.REQUEST_PENDING, second.request());
            Observation glare = observe(second, second491, null);
            preserveResponse(evidence, "reinvite-3-491.response.sip", second491);
            evidence.event("reinvite.response.observed", Map.of(
                    "cseq", "3",
                    "status", Integer.toString(second491.getStatusCode()),
                    "requestBound", Boolean.toString(glare.requestBound())));

            Response first200 = responseWithSdp(factories, first.request(), first.expectedAnswerSdp());
            Observation firstOk = observe(first, first200, first.expectedAnswerHash());
            preserveResponse(evidence, "reinvite-2-200.response.sip", first200);
            evidence.writeBytes("reinvite-2.answer.sdp", body(first200));
            evidence.event("reinvite.response.observed", Map.of(
                    "cseq", "2",
                    "status", Integer.toString(first200.getStatusCode()),
                    "requestBound", Boolean.toString(firstOk.requestBound()),
                    "sdpFresh", Boolean.toString(firstOk.sdpMatchesExpected())));

            // External SDP is allowed only when it remains explicitly bound to
            // the intended transaction and the declared answer hash.
            String externalAnswer = sdp(43004, "sendrecv", "external-answer-4");
            String externalHash = sha256(externalAnswer.getBytes(StandardCharsets.UTF_8));
            Response external200 = responseWithSdp(factories, external.request(), externalAnswer);
            Observation externalOk = observe(external, external200, externalHash);
            preserveResponse(evidence, "reinvite-4-200.response.sip", external200);
            evidence.writeBytes("reinvite-4.external-answer.sdp", body(external200));
            evidence.event("reinvite.external_sdp.observed", Map.of(
                    "cseq", "4",
                    "requestBound", Boolean.toString(externalOk.requestBound()),
                    "declaredAnswerHash", externalHash,
                    "observedAnswerHash", externalOk.observedAnswerHash(),
                    "sdpBound", Boolean.toString(externalOk.sdpMatchesExpected())));

            // Deliberately answer CSeq 5 with the previous CSeq 2 answer. A 200
            // response is therefore not enough to promote freshness/usability.
            Response stale200 = responseWithSdp(factories, stale.request(), first.expectedAnswerSdp());
            Observation staleObserved = observe(stale, stale200, stale.expectedAnswerHash());
            preserveResponse(evidence, "reinvite-5-stale-200.response.sip", stale200);
            evidence.writeBytes("reinvite-5.stale-answer.sdp", body(stale200));
            evidence.event("reinvite.stale_sdp.observed", Map.of(
                    "cseq", "5",
                    "status", Integer.toString(stale200.getStatusCode()),
                    "requestBound", Boolean.toString(staleObserved.requestBound()),
                    "expectedAnswerHash", stale.expectedAnswerHash(),
                    "observedAnswerHash", staleObserved.observedAnswerHash(),
                    "staleDetected", Boolean.toString(!staleObserved.sdpMatchesExpected())));

            boolean pass = glare.requestBound()
                    && second491.getStatusCode() == Response.REQUEST_PENDING
                    && firstOk.requestBound()
                    && firstOk.sdpMatchesExpected()
                    && externalOk.requestBound()
                    && externalOk.sdpMatchesExpected()
                    && staleObserved.requestBound()
                    && !staleObserved.sdpMatchesExpected();

            evidence.result(Map.ofEntries(
                    Map.entry("correlation.id", CORRELATION),
                    Map.entry("glare.response.status", Integer.toString(second491.getStatusCode())),
                    Map.entry("glare.response.bound", Boolean.toString(glare.requestBound())),
                    Map.entry("first.response.bound", Boolean.toString(firstOk.requestBound())),
                    Map.entry("first.sdp.fresh", Boolean.toString(firstOk.sdpMatchesExpected())),
                    Map.entry("external.response.bound", Boolean.toString(externalOk.requestBound())),
                    Map.entry("external.sdp.bound", Boolean.toString(externalOk.sdpMatchesExpected())),
                    Map.entry("harness.layer", "jain-sip-message-correlation"),
                    Map.entry("live.dialog.overlap.proven", "false"),
                    Map.entry("media.readiness.proven", "false"),
                    Map.entry("scenario.id", SCENARIO),
                    Map.entry("scenario.result", pass ? "PASS" : "FAIL"),
                    Map.entry("stale.response.bound", Boolean.toString(staleObserved.requestBound())),
                    Map.entry("stale.sdp.detected", Boolean.toString(!staleObserved.sdpMatchesExpected()))));

            if (!pass) {
                throw new IllegalStateException("BAUDOT-INTEROP-003 message correlation proof failed");
            }
        }
    }

    private static Exchange exchange(Factories factories, long cseq, int offerPort, int answerPort, String branch)
            throws Exception {
        String offerSdp = sdp(offerPort, "sendrecv", "offer-" + cseq);
        String expectedAnswerSdp = sdp(answerPort, "sendrecv", "answer-" + cseq);
        Request request = request(factories, cseq, branch, offerSdp);
        return new Exchange(
                cseq,
                request,
                correlationKey(request),
                offerSdp,
                sha256(offerSdp.getBytes(StandardCharsets.UTF_8)),
                expectedAnswerSdp,
                sha256(expectedAnswerSdp.getBytes(StandardCharsets.UTF_8)));
    }

    private static Request request(Factories factories, long cseq, String branch, String offerSdp) throws Exception {
        SipURI requestUri = factories.addresses().createSipURI("callee", "127.0.0.1");
        requestUri.setPort(5080);
        requestUri.setTransportParam(ListeningPoint.UDP);

        SipURI fromUri = factories.addresses().createSipURI("caller", "127.0.0.1");
        fromUri.setPort(5070);
        Address fromAddress = factories.addresses().createAddress(fromUri);
        FromHeader from = factories.headers().createFromHeader(fromAddress, FROM_TAG);

        SipURI toUri = factories.addresses().createSipURI("callee", "127.0.0.1");
        toUri.setPort(5080);
        Address toAddress = factories.addresses().createAddress(toUri);
        ToHeader to = factories.headers().createToHeader(toAddress, TO_TAG);

        List<ViaHeader> vias = new ArrayList<>();
        vias.add(factories.headers().createViaHeader("127.0.0.1", 5070, ListeningPoint.UDP, branch));

        CallIdHeader callId = factories.headers().createCallIdHeader(CALL_ID);
        CSeqHeader sequence = factories.headers().createCSeqHeader(cseq, Request.INVITE);
        MaxForwardsHeader maxForwards = factories.headers().createMaxForwardsHeader(70);

        Request request = factories.messages().createRequest(
                requestUri, Request.INVITE, callId, sequence, from, to, vias, maxForwards);
        ContentTypeHeader contentType = factories.headers().createContentTypeHeader("application", "sdp");
        request.setContent(offerSdp, contentType);
        return request;
    }

    private static Response responseWithSdp(Factories factories, Request request, String answerSdp) throws Exception {
        Response response = factories.messages().createResponse(Response.OK, request);
        response.setContent(answerSdp, factories.headers().createContentTypeHeader("application", "sdp"));
        return response;
    }

    private static Observation observe(Exchange expected, Response response, String expectedAnswerHash) throws Exception {
        boolean requestBound = expected.requestKey().equals(correlationKey(response));
        byte[] body = body(response);
        String observedHash = body.length == 0 ? "none" : sha256(body);
        boolean sdpMatches = expectedAnswerHash == null || expectedAnswerHash.equals(observedHash);
        return new Observation(requestBound, observedHash, sdpMatches);
    }

    private static void preserveRequest(EvidenceRecorder evidence, Exchange exchange) throws Exception {
        evidence.writeBytes(
                "reinvite-" + exchange.cseq() + ".request.sip",
                exchange.request().toString().getBytes(StandardCharsets.UTF_8));
        evidence.writeBytes(
                "reinvite-" + exchange.cseq() + ".offer.sdp",
                exchange.offerSdp().getBytes(StandardCharsets.UTF_8));
        evidence.event("reinvite.request.prepared", Map.of(
                "cseq", Long.toString(exchange.cseq()),
                "requestKey", exchange.requestKey(),
                "offerHash", exchange.offerHash(),
                "expectedAnswerHash", exchange.expectedAnswerHash()));
    }

    private static void preserveResponse(EvidenceRecorder evidence, String filename, Response response) throws Exception {
        evidence.writeBytes(filename, response.toString().getBytes(StandardCharsets.UTF_8));
    }

    private static String correlationKey(Message message) {
        CallIdHeader callId = (CallIdHeader) message.getHeader(CallIdHeader.NAME);
        FromHeader from = (FromHeader) message.getHeader(FromHeader.NAME);
        ToHeader to = (ToHeader) message.getHeader(ToHeader.NAME);
        CSeqHeader cseq = (CSeqHeader) message.getHeader(CSeqHeader.NAME);
        ViaHeader via = (ViaHeader) message.getHeader(ViaHeader.NAME);
        return String.join("|",
                callId.getCallId(),
                nullToEmpty(from.getTag()),
                nullToEmpty(to.getTag()),
                Long.toString(cseq.getSeqNumber()),
                cseq.getMethod(),
                nullToEmpty(via.getBranch()));
    }

    private static byte[] body(Message message) {
        byte[] raw = message.getRawContent();
        return raw == null ? new byte[0] : raw;
    }

    private static String sdp(int port, String direction, String session) {
        return "v=0\r\n"
                + "o=baudot 0 0 IN IP4 127.0.0.1\r\n"
                + "s=" + session + "\r\n"
                + "c=IN IP4 127.0.0.1\r\n"
                + "t=0 0\r\n"
                + "m=text " + port + " RTP/AVP 98\r\n"
                + "a=rtpmap:98 t140/1000\r\n"
                + "a=" + direction + "\r\n";
    }

    private static String sha256(byte[] bytes) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] hash = digest.digest(bytes);
        StringBuilder builder = new StringBuilder(hash.length * 2);
        for (byte value : hash) {
            builder.append(String.format("%02x", value));
        }
        return builder.toString();
    }

    private static String nullToEmpty(String value) {
        return value == null ? "" : value;
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }

    private record Exchange(
            long cseq,
            Request request,
            String requestKey,
            String offerSdp,
            String offerHash,
            String expectedAnswerSdp,
            String expectedAnswerHash) {
    }

    private record Observation(boolean requestBound, String observedAnswerHash, boolean sdpMatchesExpected) {
    }

    private record Factories(AddressFactory addresses, HeaderFactory headers, MessageFactory messages) {
        static Factories create() throws Exception {
            SipFactory factory = SipFactory.getInstance();
            factory.setPathName("gov.nist");
            return new Factories(
                    factory.createAddressFactory(),
                    factory.createHeaderFactory(),
                    factory.createMessageFactory());
        }
    }
}
