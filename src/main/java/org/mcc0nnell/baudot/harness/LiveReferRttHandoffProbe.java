package org.mcc0nnell.baudot.harness;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;
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
import javax.sip.address.URI;
import javax.sip.header.CSeqHeader;
import javax.sip.header.CallIdHeader;
import javax.sip.header.ContactHeader;
import javax.sip.header.ContentTypeHeader;
import javax.sip.header.EventHeader;
import javax.sip.header.ExpiresHeader;
import javax.sip.header.FromHeader;
import javax.sip.header.HeaderFactory;
import javax.sip.header.MaxForwardsHeader;
import javax.sip.header.ReferToHeader;
import javax.sip.header.SubscriptionStateHeader;
import javax.sip.header.ToHeader;
import javax.sip.header.ViaHeader;
import javax.sip.message.MessageFactory;
import javax.sip.message.Request;
import javax.sip.message.Response;

/**
 * Replacement-leg RTT readiness gate for BAUDOT-INTEROP-004.
 *
 * <p>Two live transfer arms use the same JAIN SIP REFER/NOTIFY/replacement-
 * dialog mechanics with synthetic provider identities. The control target sends
 * Baudot's canonical primary T.140 RTP packet after replacement ACK. The
 * signaling-only target deliberately sends no RTT packet. In both arms REFER,
 * NOTIFY, and replacement-dialog signaling succeed. The old leg is released in
 * the control arm only after the canonical packet is observed; it remains up in
 * the signaling-only arm.</p>
 *
 * <p>Java preserves the signaling and UDP facts and performs only an exact-byte
 * match against the existing canonical packet before allowing control teardown.
 * A Python reference validator independently parses the preserved packet and
 * derives firstT140CharacterObserved/rttReady.</p>
 */
public final class LiveReferRttHandoffProbe {
    private static final String SCENARIO = "BAUDOT-INTEROP-004";
    private static final String CORRELATION = "jain-live-refer-rtt-v1";
    private static final String HOST = "127.0.0.1";
    private static final Duration SIP_TIMEOUT = Duration.ofSeconds(5);
    private static final Duration RTT_WINDOW = Duration.ofMillis(900);
    private static final int T140_PT = 98;

    private LiveReferRttHandoffProbe() {
    }

    public static void main(String[] args) {
        int exit = 2;
        try {
            Path root = Path.of(env("BAUDOT_EVIDENCE_DIR", "target/evidence"));
            CaseResult control = runCase(root, new CaseConfig("control", 5140, true));
            CaseResult signalingOnly = runCase(root, new CaseConfig("signaling-only", 5160, false));

            boolean pass = control.signalingComplete()
                    && control.canonicalRttObserved()
                    && control.oldByeObserved()
                    && control.oldByeAfterRttObservation()
                    && signalingOnly.signalingComplete()
                    && !signalingOnly.rttDatagramObserved()
                    && !signalingOnly.oldByeObserved();
            exit = pass ? 0 : 3;
        } catch (Throwable failure) {
            failure.printStackTrace(System.err);
        }
        System.exit(exit);
    }

    private static CaseResult runCase(Path root, CaseConfig config) throws Exception {
        AtomicReference<Throwable> targetFailure = new AtomicReference<>();
        AtomicBoolean targetInviteObserved = new AtomicBoolean();
        AtomicBoolean targetAckObserved = new AtomicBoolean();

        try (EvidenceRecorder evidence = new EvidenceRecorder(root, SCENARIO, CORRELATION, config.id());
             MediaReceiver media = new MediaReceiver(config, evidence);
             TransferProvider providerA = new TransferProvider(config, evidence, media);
             DatagramSocket referrer = new DatagramSocket(new InetSocketAddress(
                     InetAddress.getByName(HOST), config.referrerPort()));
             DatagramSocket providerB = new DatagramSocket(new InetSocketAddress(
                     InetAddress.getByName(HOST), config.providerBPort()))) {

            referrer.setSoTimeout((int) SIP_TIMEOUT.toMillis());
            providerB.setSoTimeout((int) SIP_TIMEOUT.toMillis());
            media.start();
            providerA.start();

            Thread targetThread = new Thread(() -> {
                try {
                    runProviderB(config, providerB, evidence, targetInviteObserved, targetAckObserved);
                } catch (Throwable failure) {
                    targetFailure.set(failure);
                }
            }, "baudot-refer-rtt-" + config.id() + "-provider-b");
            targetThread.setDaemon(true);
            targetThread.start();

            sendRaw(referrer, config.providerAPort(), initialInvite(config), evidence,
                    "original-invite.request.sip");
            RawPacket initialFinal = receiveFinalResponse(
                    referrer, 1, Request.INVITE, evidence, "original-invite");
            require(initialFinal.message().statusCode() == Response.OK,
                    config.id() + ": original dialog did not receive 200");
            sendRaw(referrer, config.providerAPort(), originalAck(config), evidence,
                    "original-ack.request.sip");
            require(providerA.awaitInitialAck(SIP_TIMEOUT), config.id() + ": original ACK missing");

            sendRaw(referrer, config.providerAPort(), referRequest(config), evidence,
                    "refer.request.sip");

            boolean referAccepted = false;
            boolean finalNotifyObserved = false;
            boolean oldByeObserved = false;
            int ordinal = 0;
            long deadline = System.nanoTime() + Duration.ofSeconds(15).toNanos();

            while (System.nanoTime() < deadline
                    && (!finalNotifyObserved || (config.emitRtt() && !oldByeObserved))) {
                RawPacket packet = receiveRaw(referrer);
                RawSip message = packet.message();
                ordinal++;
                evidence.writeBytes(
                        "referrer-wire-" + ordinal + ".sip",
                        packet.raw().getBytes(StandardCharsets.UTF_8));

                if (message.isResponse()) {
                    if (message.cseqNumber() == 2
                            && Request.REFER.equals(message.cseqMethod())
                            && is2xx(message.statusCode())) {
                        referAccepted = true;
                    }
                    continue;
                }

                if (Request.NOTIFY.equals(message.method())) {
                    int sipfragStatus = message.sipfragStatus();
                    if (sipfragStatus >= 200) {
                        finalNotifyObserved = true;
                    }
                    String response = rawResponse(
                            message, Response.OK, "OK", null,
                            "<sip:referrer@" + HOST + ":" + config.referrerPort() + ">",
                            null, null);
                    sendRaw(referrer, packet.port(), response, evidence,
                            "notify-" + ordinal + "-200.response.sip");
                    continue;
                }

                if (Request.BYE.equals(message.method())) {
                    oldByeObserved = true;
                    String response = rawResponse(message, Response.OK, "OK", null, null, null, null);
                    sendRaw(referrer, packet.port(), response, evidence, "old-leg-bye-200.response.sip");
                }
            }

            require(referAccepted, config.id() + ": REFER was not accepted");
            require(finalNotifyObserved, config.id() + ": terminal NOTIFY missing");
            require(providerA.awaitReplacementEstablished(SIP_TIMEOUT),
                    config.id() + ": replacement dialog did not establish");
            require(providerA.awaitFinalNotifyAck(SIP_TIMEOUT),
                    config.id() + ": final NOTIFY was not acknowledged");

            if (config.emitRtt()) {
                require(providerA.awaitOldByeResponse(SIP_TIMEOUT),
                        config.id() + ": control old-leg BYE did not complete");
                require(oldByeObserved, config.id() + ": control old-leg BYE not observed by referrer");
            } else {
                require(!providerA.oldByeSent(),
                        config.id() + ": signaling-only arm tore down old leg without RTT readiness");
                require(!oldByeObserved,
                        config.id() + ": signaling-only referrer observed unexpected old-leg BYE");
            }

            targetThread.join(SIP_TIMEOUT.toMillis());
            if (targetFailure.get() != null) {
                throw new IllegalStateException(config.id() + ": provider-b failed", targetFailure.get());
            }

            boolean signalingComplete = referAccepted
                    && finalNotifyObserved
                    && providerA.replacementEstablished()
                    && providerA.targetCorrelated()
                    && targetInviteObserved.get()
                    && targetAckObserved.get();

            evidence.result(Map.ofEntries(
                    Map.entry("arm.id", config.id()),
                    Map.entry("correlation.id", CORRELATION),
                    Map.entry("provider.source", "provider-a"),
                    Map.entry("provider.target", "provider-b"),
                    Map.entry("refer.accepted", Boolean.toString(referAccepted)),
                    Map.entry("notify.final.observed", Boolean.toString(finalNotifyObserved)),
                    Map.entry("replacement.dialog.established", Boolean.toString(providerA.replacementEstablished())),
                    Map.entry("replacement.target.correlated", Boolean.toString(providerA.targetCorrelated())),
                    Map.entry("rtt.negotiated", "true"),
                    Map.entry("rtt.datagram.observed", Boolean.toString(media.datagramObserved())),
                    Map.entry("rtt.canonicalBytesMatched", Boolean.toString(media.canonicalMatched())),
                    Map.entry("oldLeg.bye.observed", Boolean.toString(oldByeObserved)),
                    Map.entry("oldLeg.bye.sent", Boolean.toString(providerA.oldByeSent())),
                    Map.entry("oldLeg.bye.afterRttObservation",
                            Boolean.toString(providerA.oldByeAfterRttObservation())),
                    Map.entry("signaling.transfer.complete", Boolean.toString(signalingComplete)),
                    Map.entry("firstT140CharacterObserved", "UNCLASSIFIED_BY_JAVA"),
                    Map.entry("rttReady", "UNCLASSIFIED_BY_JAVA"),
                    Map.entry("scenario.id", SCENARIO)));

            return new CaseResult(
                    signalingComplete,
                    media.datagramObserved(),
                    media.canonicalMatched(),
                    oldByeObserved,
                    providerA.oldByeAfterRttObservation());
        }
    }

    private static void runProviderB(
            CaseConfig config,
            DatagramSocket socket,
            EvidenceRecorder evidence,
            AtomicBoolean inviteObserved,
            AtomicBoolean ackObserved) throws Exception {
        int ordinal = 0;
        int offerPort = -1;
        while (!ackObserved.get()) {
            RawPacket packet = receiveRaw(socket);
            RawSip message = packet.message();
            ordinal++;
            evidence.writeBytes(
                    "provider-b-wire-" + ordinal + ".sip",
                    packet.raw().getBytes(StandardCharsets.UTF_8));

            if (Request.INVITE.equals(message.method())) {
                inviteObserved.set(true);
                offerPort = message.textMediaPort();
                require(offerPort == config.providerAMediaPort(),
                        config.id() + ": replacement SDP did not advertise provider-a RTT receiver");
                require(message.body().contains("a=rtpmap:" + T140_PT + " t140/1000"),
                        config.id() + ": replacement offer did not negotiate text/t140");

                String ringing = rawResponse(
                        message, Response.RINGING, "Ringing", config.providerBTag(),
                        "<sip:provider-b@" + HOST + ":" + config.providerBPort() + ">",
                        null, null);
                sendRaw(socket, packet.port(), ringing, evidence, "provider-b-180.response.sip");

                String answer = sdp(config.providerBMediaPort(), "provider-b-answer");
                String ok = rawResponse(
                        message, Response.OK, "OK", config.providerBTag(),
                        "<sip:provider-b@" + HOST + ":" + config.providerBPort() + ">",
                        "application/sdp", answer);
                sendRaw(socket, packet.port(), ok, evidence, "provider-b-200.response.sip");
                continue;
            }

            if (Request.ACK.equals(message.method())) {
                ackObserved.set(true);
                if (config.emitRtt()) {
                    require(offerPort > 0, config.id() + ": missing negotiated RTT target port");
                    byte[] packetBytes = RttSipProbe.normalPrimaryPacket();
                    evidence.writeBytes("rtt-datagram-sent.bin", packetBytes);
                    DatagramPacket rtt = new DatagramPacket(
                            packetBytes,
                            packetBytes.length,
                            InetAddress.getByName(HOST),
                            offerPort);
                    socket.send(rtt);
                    evidence.event("refer.rtt.sent", Map.of(
                            "target", HOST + ":" + offerPort,
                            "bytes", Integer.toString(packetBytes.length),
                            "classification", "canonical-bytes-unparsed"));
                } else {
                    evidence.event("refer.rtt.withheld", Map.of(
                            "reason", "signaling-only controlled arm"));
                }
                return;
            }
        }
    }

    private static String initialInvite(CaseConfig config) {
        return "INVITE sip:provider-a@" + HOST + ":" + config.providerAPort() + " SIP/2.0\r\n"
                + "Via: SIP/2.0/UDP " + HOST + ":" + config.referrerPort()
                + ";branch=z9hG4bK-" + config.id() + "-initial;rport\r\n"
                + "Max-Forwards: 70\r\n"
                + "From: <sip:referrer@" + HOST + ":" + config.referrerPort() + ">;tag=" + config.referrerTag() + "\r\n"
                + "To: <sip:provider-a@" + HOST + ":" + config.providerAPort() + ">\r\n"
                + "Call-ID: " + config.originalCallId() + "\r\n"
                + "CSeq: 1 INVITE\r\n"
                + "Contact: <sip:referrer@" + HOST + ":" + config.referrerPort() + ">\r\n"
                + "Content-Length: 0\r\n\r\n";
    }

    private static String originalAck(CaseConfig config) {
        return "ACK sip:provider-a@" + HOST + ":" + config.providerAPort() + " SIP/2.0\r\n"
                + "Via: SIP/2.0/UDP " + HOST + ":" + config.referrerPort()
                + ";branch=z9hG4bK-" + config.id() + "-ack;rport\r\n"
                + "Max-Forwards: 70\r\n"
                + "From: <sip:referrer@" + HOST + ":" + config.referrerPort() + ">;tag=" + config.referrerTag() + "\r\n"
                + "To: <sip:provider-a@" + HOST + ":" + config.providerAPort() + ">;tag=" + config.providerATag() + "\r\n"
                + "Call-ID: " + config.originalCallId() + "\r\n"
                + "CSeq: 1 ACK\r\n"
                + "Content-Length: 0\r\n\r\n";
    }

    private static String referRequest(CaseConfig config) {
        return "REFER sip:provider-a@" + HOST + ":" + config.providerAPort() + " SIP/2.0\r\n"
                + "Via: SIP/2.0/UDP " + HOST + ":" + config.referrerPort()
                + ";branch=z9hG4bK-" + config.id() + "-refer;rport\r\n"
                + "Max-Forwards: 70\r\n"
                + "From: <sip:referrer@" + HOST + ":" + config.referrerPort() + ">;tag=" + config.referrerTag() + "\r\n"
                + "To: <sip:provider-a@" + HOST + ":" + config.providerAPort() + ">;tag=" + config.providerATag() + "\r\n"
                + "Call-ID: " + config.originalCallId() + "\r\n"
                + "CSeq: 2 REFER\r\n"
                + "Contact: <sip:referrer@" + HOST + ":" + config.referrerPort() + ">\r\n"
                + "Refer-To: <sip:provider-b@" + HOST + ":" + config.providerBPort() + ">\r\n"
                + "Content-Length: 0\r\n\r\n";
    }

    private static String sdp(int port, String sessionName) {
        return "v=0\r\n"
                + "o=baudot 0 0 IN IP4 " + HOST + "\r\n"
                + "s=" + sessionName + "\r\n"
                + "c=IN IP4 " + HOST + "\r\n"
                + "t=0 0\r\n"
                + "m=text " + port + " RTP/AVP " + T140_PT + "\r\n"
                + "a=rtpmap:" + T140_PT + " t140/1000\r\n"
                + "a=sendrecv\r\n";
    }

    private static RawPacket receiveFinalResponse(
            DatagramSocket socket,
            long cseq,
            String method,
            EvidenceRecorder evidence,
            String prefix) throws Exception {
        int ordinal = 0;
        while (true) {
            RawPacket packet = receiveRaw(socket);
            ordinal++;
            evidence.writeBytes(
                    prefix + "-response-" + ordinal + ".sip",
                    packet.raw().getBytes(StandardCharsets.UTF_8));
            RawSip message = packet.message();
            if (message.isResponse()
                    && message.cseqNumber() == cseq
                    && method.equals(message.cseqMethod())
                    && message.statusCode() >= 200) {
                return packet;
            }
        }
    }

    private static RawPacket receiveRaw(DatagramSocket socket) throws Exception {
        byte[] buffer = new byte[16384];
        DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
        socket.receive(packet);
        String raw = new String(packet.getData(), packet.getOffset(), packet.getLength(), StandardCharsets.UTF_8);
        return new RawPacket(raw, RawSip.parse(raw), packet.getPort());
    }

    private static void sendRaw(
            DatagramSocket socket,
            int port,
            String message,
            EvidenceRecorder evidence,
            String filename) throws Exception {
        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        evidence.writeBytes(filename, bytes);
        socket.send(new DatagramPacket(bytes, bytes.length, InetAddress.getByName(HOST), port));
    }

    private static String rawResponse(
            RawSip request,
            int status,
            String reason,
            String toTag,
            String contact,
            String contentType,
            String body) {
        String to = request.header("to");
        if (toTag != null && to != null && !to.toLowerCase().contains(";tag=")) {
            to += ";tag=" + toTag;
        }
        String payload = body == null ? "" : body;
        byte[] payloadBytes = payload.getBytes(StandardCharsets.UTF_8);
        StringBuilder response = new StringBuilder();
        response.append("SIP/2.0 ").append(status).append(' ').append(reason).append("\r\n");
        appendHeader(response, "Via", request.header("via"));
        appendHeader(response, "From", request.header("from"));
        appendHeader(response, "To", to);
        appendHeader(response, "Call-ID", request.header("call-id"));
        appendHeader(response, "CSeq", request.header("cseq"));
        if (contact != null) {
            appendHeader(response, "Contact", contact);
        }
        if (contentType != null) {
            appendHeader(response, "Content-Type", contentType);
        }
        response.append("Content-Length: ").append(payloadBytes.length).append("\r\n\r\n");
        response.append(payload);
        return response.toString();
    }

    private static void appendHeader(StringBuilder builder, String name, String value) {
        if (value != null) {
            builder.append(name).append(": ").append(value).append("\r\n");
        }
    }

    private static boolean is2xx(int status) {
        return status >= 200 && status < 300;
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    private record CaseConfig(String id, int providerAPort, boolean emitRtt) {
        int referrerPort() {
            return providerAPort + 1;
        }

        int providerBPort() {
            return providerAPort + 2;
        }

        int providerAMediaPort() {
            return providerAPort + 3;
        }

        int providerBMediaPort() {
            return providerAPort + 4;
        }

        String referrerTag() {
            return "baudot-referrer-" + id;
        }

        String providerATag() {
            return "baudot-provider-a-" + id;
        }

        String providerBTag() {
            return "baudot-provider-b-" + id;
        }

        String originalCallId() {
            return "baudot-refer-rtt-" + id + "@127.0.0.1";
        }
    }

    private record CaseResult(
            boolean signalingComplete,
            boolean rttDatagramObserved,
            boolean canonicalRttObserved,
            boolean oldByeObserved,
            boolean oldByeAfterRttObservation) {
    }

    private record RawPacket(String raw, RawSip message, int port) {
    }

    private static final class RawSip {
        private final String startLine;
        private final Map<String, String> headers;
        private final String body;

        private RawSip(String startLine, Map<String, String> headers, String body) {
            this.startLine = startLine;
            this.headers = headers;
            this.body = body;
        }

        static RawSip parse(String raw) {
            String[] parts = raw.split("\\r\\n\\r\\n", 2);
            String[] lines = parts[0].split("\\r\\n");
            Map<String, String> headers = new LinkedHashMap<>();
            for (int i = 1; i < lines.length; i++) {
                int colon = lines[i].indexOf(':');
                if (colon > 0) {
                    headers.putIfAbsent(
                            lines[i].substring(0, colon).trim().toLowerCase(),
                            lines[i].substring(colon + 1).trim());
                }
            }
            return new RawSip(lines[0], headers, parts.length == 2 ? parts[1] : "");
        }

        boolean isResponse() {
            return startLine.startsWith("SIP/2.0 ");
        }

        String method() {
            if (isResponse()) {
                return null;
            }
            int space = startLine.indexOf(' ');
            return space > 0 ? startLine.substring(0, space) : startLine;
        }

        int statusCode() {
            if (!isResponse()) {
                return -1;
            }
            return Integer.parseInt(startLine.split(" ", 3)[1]);
        }

        String header(String name) {
            return headers.get(name.toLowerCase());
        }

        String body() {
            return body;
        }

        long cseqNumber() {
            String value = header("cseq");
            if (value == null) {
                return -1;
            }
            return Long.parseLong(value.split("\\s+", 2)[0]);
        }

        String cseqMethod() {
            String value = header("cseq");
            if (value == null) {
                return null;
            }
            String[] tokens = value.split("\\s+", 2);
            return tokens.length == 2 ? tokens[1] : null;
        }

        int sipfragStatus() {
            String trimmed = body.trim();
            if (!trimmed.startsWith("SIP/2.0 ")) {
                return -1;
            }
            return Integer.parseInt(trimmed.split("\\s+", 3)[1]);
        }

        int textMediaPort() {
            for (String line : body.split("\\r\\n")) {
                if (line.startsWith("m=text ")) {
                    String[] tokens = line.split("\\s+");
                    return tokens.length >= 2 ? Integer.parseInt(tokens[1]) : -1;
                }
            }
            return -1;
        }
    }

    private static final class MediaReceiver implements AutoCloseable {
        private final CaseConfig config;
        private final EvidenceRecorder evidence;
        private final DatagramSocket socket;
        private final CountDownLatch finished = new CountDownLatch(1);
        private final AtomicBoolean observed = new AtomicBoolean();
        private final AtomicBoolean canonical = new AtomicBoolean();
        private final AtomicReference<Throwable> failure = new AtomicReference<>();
        private volatile Thread thread;

        MediaReceiver(CaseConfig config, EvidenceRecorder evidence) throws Exception {
            this.config = config;
            this.evidence = evidence;
            this.socket = new DatagramSocket(new InetSocketAddress(
                    InetAddress.getByName(HOST), config.providerAMediaPort()));
            this.socket.setSoTimeout((int) RTT_WINDOW.toMillis());
        }

        void start() {
            thread = new Thread(() -> {
                try {
                    byte[] buffer = new byte[2048];
                    DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                    socket.receive(packet);
                    byte[] content = Arrays.copyOfRange(
                            packet.getData(), packet.getOffset(), packet.getOffset() + packet.getLength());
                    observed.set(true);
                    canonical.set(Arrays.equals(content, RttSipProbe.normalPrimaryPacket()));
                    evidence.writeBytes("rtt-datagram-received.bin", content);
                    evidence.event("refer.rtt.observed", Map.of(
                            "bytes", Integer.toString(content.length),
                            "canonicalBytesMatched", Boolean.toString(canonical.get()),
                            "classification", "byte-match-only"));
                } catch (SocketTimeoutException expected) {
                    evidence.event("refer.rtt.observation_timeout", Map.of(
                            "windowMs", Long.toString(RTT_WINDOW.toMillis())));
                } catch (Throwable throwable) {
                    failure.set(throwable);
                } finally {
                    finished.countDown();
                }
            }, "baudot-refer-rtt-receiver-" + config.id());
            thread.setDaemon(true);
            thread.start();
        }

        boolean await(Duration timeout) throws Exception {
            boolean complete = finished.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
            if (failure.get() != null) {
                throw new IllegalStateException(config.id() + ": RTT receiver failed", failure.get());
            }
            return complete;
        }

        boolean datagramObserved() {
            return observed.get();
        }

        boolean canonicalMatched() {
            return canonical.get();
        }

        @Override
        public void close() {
            socket.close();
        }
    }

    private static final class TransferProvider implements SipListener, AutoCloseable {
        private final CaseConfig config;
        private final EvidenceRecorder evidence;
        private final MediaReceiver media;
        private final SipStack stack;
        private final SipProvider provider;
        private final AddressFactory addresses;
        private final HeaderFactory headers;
        private final MessageFactory messages;
        private final CountDownLatch initialAck = new CountDownLatch(1);
        private final CountDownLatch replacementEstablished = new CountDownLatch(1);
        private final CountDownLatch finalNotifyAck = new CountDownLatch(1);
        private final CountDownLatch oldByeResponse = new CountDownLatch(1);
        private final AtomicBoolean targetCorrelated = new AtomicBoolean();
        private final AtomicBoolean oldByeAfterRtt = new AtomicBoolean();
        private final AtomicBoolean oldByeSent = new AtomicBoolean();

        private volatile Dialog originalDialog;
        private volatile Dialog replacementDialog;
        private volatile ClientTransaction finalNotifyTransaction;
        private volatile long referCseq = -1;

        TransferProvider(CaseConfig config, EvidenceRecorder evidence, MediaReceiver media) throws Exception {
            this.config = config;
            this.evidence = evidence;
            this.media = media;
            SipFactory factory = SipFactory.getInstance();
            factory.setPathName("gov.nist");
            Properties properties = new Properties();
            properties.setProperty("javax.sip.STACK_NAME", "baudot-refer-rtt-" + config.id());
            properties.setProperty("gov.nist.javax.sip.TRACE_LEVEL", "0");
            this.stack = factory.createSipStack(properties);
            this.addresses = factory.createAddressFactory();
            this.headers = factory.createHeaderFactory();
            this.messages = factory.createMessageFactory();
            ListeningPoint point = stack.createListeningPoint(
                    HOST, config.providerAPort(), ListeningPoint.UDP);
            this.provider = stack.createSipProvider(point);
            this.provider.addSipListener(this);
        }

        void start() throws Exception {
            stack.start();
        }

        boolean awaitInitialAck(Duration timeout) throws InterruptedException {
            return initialAck.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        boolean awaitReplacementEstablished(Duration timeout) throws InterruptedException {
            return replacementEstablished.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        boolean awaitFinalNotifyAck(Duration timeout) throws InterruptedException {
            return finalNotifyAck.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        boolean awaitOldByeResponse(Duration timeout) throws InterruptedException {
            return oldByeResponse.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
        }

        boolean replacementEstablished() {
            return replacementEstablished.getCount() == 0;
        }

        boolean targetCorrelated() {
            return targetCorrelated.get();
        }

        boolean oldByeSent() {
            return oldByeSent.get();
        }

        boolean oldByeAfterRttObservation() {
            return oldByeAfterRtt.get();
        }

        @Override
        public void processRequest(RequestEvent event) {
            Request request = event.getRequest();
            try {
                CSeqHeader cseq = (CSeqHeader) request.getHeader(CSeqHeader.NAME);
                long sequence = cseq == null ? -1 : cseq.getSeqNumber();
                if (Request.ACK.equals(request.getMethod())) {
                    if (sequence == 1) {
                        initialAck.countDown();
                    }
                    return;
                }
                if (Request.INVITE.equals(request.getMethod())) {
                    ServerTransaction transaction = event.getServerTransaction();
                    if (transaction == null) {
                        transaction = provider.getNewServerTransaction(request);
                    }
                    Response ok = messages.createResponse(Response.OK, request);
                    ToHeader to = (ToHeader) ok.getHeader(ToHeader.NAME);
                    if (to.getTag() == null) {
                        to.setTag(config.providerATag());
                    }
                    ok.addHeader(contact("provider-a", config.providerAPort()));
                    transaction.sendResponse(ok);
                    originalDialog = transaction.getDialog();
                    return;
                }
                if (Request.REFER.equals(request.getMethod())) {
                    handleRefer(event, request, sequence);
                }
            } catch (Exception failure) {
                evidence.event("refer.rtt.provider_request_error", Map.of(
                        "method", request.getMethod(),
                        "error", failure.toString()));
            }
        }

        private void handleRefer(RequestEvent event, Request request, long sequence) throws Exception {
            ReferToHeader referTo = (ReferToHeader) request.getHeader(ReferToHeader.NAME);
            require(referTo != null, config.id() + ": REFER missing Refer-To");
            referCseq = sequence;
            originalDialog = event.getDialog() == null ? originalDialog : event.getDialog();

            URI uri = referTo.getAddress().getURI();
            if (uri instanceof SipURI sipUri) {
                int port = sipUri.getPort() == -1 ? 5060 : sipUri.getPort();
                targetCorrelated.set(
                        "provider-b".equals(sipUri.getUser())
                                && HOST.equals(sipUri.getHost())
                                && port == config.providerBPort());
            }

            ServerTransaction transaction = event.getServerTransaction();
            if (transaction == null) {
                transaction = provider.getNewServerTransaction(request);
            }
            Response accepted = messages.createResponse(202, request);
            accepted.addHeader(contact("provider-a", config.providerAPort()));
            ExpiresHeader expires = headers.createExpiresHeader(30);
            accepted.addHeader(expires);
            transaction.sendResponse(accepted);

            sendNotify(Response.TRYING, "Trying", false);
            sendReplacementInvite();
        }

        private void sendReplacementInvite() throws Exception {
            SipURI requestUri = addresses.createSipURI("provider-b", HOST);
            requestUri.setPort(config.providerBPort());
            requestUri.setTransportParam(ListeningPoint.UDP);
            SipURI fromUri = addresses.createSipURI("provider-a", HOST);
            fromUri.setPort(config.providerAPort());
            Address fromAddress = addresses.createAddress(fromUri);
            FromHeader from = headers.createFromHeader(fromAddress, "baudot-transfer-" + config.id());
            ToHeader to = headers.createToHeader(addresses.createAddress(requestUri), null);
            ArrayList<ViaHeader> vias = new ArrayList<>();
            vias.add(headers.createViaHeader(HOST, config.providerAPort(), ListeningPoint.UDP, null));
            CallIdHeader callId = provider.getNewCallId();
            CSeqHeader cseq = headers.createCSeqHeader(1L, Request.INVITE);
            MaxForwardsHeader max = headers.createMaxForwardsHeader(70);
            Request invite = messages.createRequest(
                    requestUri, Request.INVITE, callId, cseq, from, to, vias, max);
            invite.addHeader(contact("provider-a", config.providerAPort()));
            invite.setContent(
                    sdp(config.providerAMediaPort(), "provider-a-offer-" + config.id()),
                    headers.createContentTypeHeader("application", "sdp"));
            evidence.writeBytes("replacement-invite.request.sip",
                    invite.toString().getBytes(StandardCharsets.UTF_8));
            provider.getNewClientTransaction(invite).sendRequest();
        }

        private void sendNotify(int status, String reason, boolean terminal) throws Exception {
            Request notify = originalDialog.createRequest(Request.NOTIFY);
            EventHeader referEvent = headers.createEventHeader("refer");
            referEvent.setEventId(Long.toString(referCseq));
            notify.setHeader(referEvent);
            String state = terminal
                    ? SubscriptionStateHeader.TERMINATED
                    : status > 100 ? SubscriptionStateHeader.ACTIVE : SubscriptionStateHeader.PENDING;
            SubscriptionStateHeader subscription = headers.createSubscriptionStateHeader(state);
            if (terminal) {
                subscription.setReasonCode("noresource");
            }
            notify.setHeader(subscription);
            notify.setHeader(contact("provider-a", config.providerAPort()));
            ContentTypeHeader contentType = headers.createContentTypeHeader("message", "sipfrag");
            contentType.setParameter("version", "2.0");
            notify.setContent("SIP/2.0 " + status + " " + reason + "\r\n", contentType);
            ClientTransaction transaction = provider.getNewClientTransaction(notify);
            if (terminal) {
                finalNotifyTransaction = transaction;
            }
            evidence.writeBytes("notify-" + status + ".request.sip",
                    notify.toString().getBytes(StandardCharsets.UTF_8));
            originalDialog.sendRequest(transaction);
        }

        private void sendOldByeIfReady() throws Exception {
            if (!config.emitRtt()) {
                evidence.event("old_leg.preserved", Map.of(
                        "reason", "replacement RTT readiness not observed"));
                return;
            }
            boolean complete = media.await(Duration.ofSeconds(2));
            boolean readyEnoughForJavaGate = complete && media.canonicalMatched();
            if (!readyEnoughForJavaGate) {
                evidence.event("old_leg.preserved", Map.of(
                        "reason", "canonical RTT bytes not observed"));
                return;
            }
            oldByeAfterRtt.set(true);
            oldByeSent.set(true);
            Request bye = originalDialog.createRequest(Request.BYE);
            originalDialog.sendRequest(provider.getNewClientTransaction(bye));
        }

        @Override
        public void processResponse(ResponseEvent event) {
            Response response = event.getResponse();
            try {
                CSeqHeader cseq = (CSeqHeader) response.getHeader(CSeqHeader.NAME);
                if (cseq == null) {
                    return;
                }
                if (Request.INVITE.equals(cseq.getMethod())) {
                    int status = response.getStatusCode();
                    if (status > 100 && status < 200) {
                        sendNotify(status, response.getReasonPhrase(), false);
                    } else if (is2xx(status)) {
                        replacementDialog = event.getDialog() != null
                                ? event.getDialog()
                                : event.getClientTransaction().getDialog();
                        require(replacementDialog != null, config.id() + ": missing replacement dialog");
                        Request ack = replacementDialog.createAck(cseq.getSeqNumber());
                        replacementDialog.sendAck(ack);
                        replacementEstablished.countDown();
                        sendNotify(status, response.getReasonPhrase(), true);
                    }
                    return;
                }
                if (Request.NOTIFY.equals(cseq.getMethod())
                        && finalNotifyTransaction != null
                        && event.getClientTransaction() == finalNotifyTransaction
                        && is2xx(response.getStatusCode())) {
                    finalNotifyAck.countDown();
                    sendOldByeIfReady();
                    return;
                }
                if (Request.BYE.equals(cseq.getMethod()) && is2xx(response.getStatusCode())) {
                    oldByeResponse.countDown();
                }
            } catch (Exception failure) {
                evidence.event("refer.rtt.provider_response_error", Map.of(
                        "status", Integer.toString(response.getStatusCode()),
                        "error", failure.toString()));
            }
        }

        private ContactHeader contact(String user, int port) throws Exception {
            SipURI uri = addresses.createSipURI(user, HOST);
            uri.setPort(port);
            uri.setTransportParam(ListeningPoint.UDP);
            return headers.createContactHeader(addresses.createAddress(uri));
        }

        @Override
        public void processTimeout(TimeoutEvent event) {
            evidence.event("refer.rtt.timeout", Map.of(
                    "server", Boolean.toString(event.isServerTransaction())));
        }

        @Override
        public void processIOException(IOExceptionEvent event) {
            evidence.event("refer.rtt.io_error", Map.of(
                    "host", String.valueOf(event.getHost()),
                    "port", Integer.toString(event.getPort())));
        }

        @Override
        public void processTransactionTerminated(TransactionTerminatedEvent event) {
        }

        @Override
        public void processDialogTerminated(DialogTerminatedEvent event) {
        }

        @Override
        public void close() {
            try {
                stack.stop();
            } catch (Exception ignored) {
            }
        }
    }
}
