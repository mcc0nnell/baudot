package org.mcc0nnell.baudot.harness;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.cert.X509Certificate;
import java.time.Duration;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLServerSocketFactory;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManagerFactory;

/**
 * Controlled RFC 5626 outbound-flow behavior proof.
 *
 * <p>The probe establishes an outbound registration on one loopback TLS
 * connection, observes a CRLF keepalive/pong, deliberately closes that flow,
 * re-registers the same AOR/+sip.instance/reg-id tuple on a replacement flow,
 * and proves that an inbound SIP request can traverse the replacement
 * connection. It proves only this bounded behavior, not RFC 5626 conformance.</p>
 */
public final class RueOutboundFlowProbe {
    private static final String SCENARIO = "RUE-REG-001";
    private static final String CORRELATION = "outbound-flow-recovery-v1";
    private static final Duration TIMEOUT = Duration.ofSeconds(8);

    private static final String DOMAIN = "provider-a.example";
    private static final String NUMBER = "+12025550101";
    private static final String AOR = "sip:" + NUMBER + "@" + DOMAIN;
    private static final String REGISTER_URI = "sip:" + DOMAIN;
    private static final String USERNAME = "rue-001";
    private static final String PASSWORD = "baudot-secret";
    private static final String REALM = DOMAIN;
    private static final String INSTANCE =
            "<urn:uuid:00000000-0000-4000-8000-000000000001>";
    private static final String REG_ID = "1";
    private static final String CALL_ID = "baudot-rue-outbound-001@127.0.0.1";
    private static final String FLOW_TIMER = "5";

    private RueOutboundFlowProbe() {
    }

    public static void main(String[] args) {
        int exit;
        try {
            exit = run();
        } catch (Throwable failure) {
            failure.printStackTrace(System.err);
            exit = 2;
        }
        System.exit(exit);
    }

    private static int run() throws Exception {
        Path evidenceRoot = Path.of(env("BAUDOT_EVIDENCE_DIR", "target/evidence"));
        Path keyStorePath = Path.of(requiredEnv("BAUDOT_RUE_REG_KEYSTORE"));
        char[] storePassword = requiredEnv("BAUDOT_RUE_REG_KEYSTORE_PASSWORD").toCharArray();
        String host = env("BAUDOT_RUE_REG_HOST", "127.0.0.1");
        int port = Integer.parseInt(env("BAUDOT_RUE_REG_PORT", "5161"));

        SSLContext context = sslContext(keyStorePath, storePassword);
        AtomicReference<Throwable> serverFailure = new AtomicReference<>();
        AtomicBoolean firstBindingAccepted = new AtomicBoolean();
        AtomicBoolean outboundRequireObserved = new AtomicBoolean();
        AtomicBoolean keepalivePingObserved = new AtomicBoolean();
        AtomicBoolean keepalivePongObserved = new AtomicBoolean();
        AtomicBoolean firstFlowLossDetected = new AtomicBoolean();
        AtomicBoolean replacementSameBindingKey = new AtomicBoolean();
        AtomicBoolean replacementBindingAccepted = new AtomicBoolean();
        AtomicBoolean inboundRequestOnReplacementFlow = new AtomicBoolean();
        AtomicBoolean inboundResponseOnReplacementFlow = new AtomicBoolean();
        CountDownLatch listening = new CountDownLatch(1);
        CountDownLatch firstFlowClosed = new CountDownLatch(1);

        try (EvidenceRecorder evidence = new EvidenceRecorder(
                evidenceRoot, SCENARIO, CORRELATION, "outbound-flow-proof")) {

            Thread server = new Thread(() -> {
                try {
                    runServer(
                            context,
                            host,
                            port,
                            evidence,
                            listening,
                            firstFlowClosed,
                            firstBindingAccepted,
                            keepalivePingObserved,
                            replacementSameBindingKey,
                            replacementBindingAccepted,
                            inboundResponseOnReplacementFlow);
                } catch (Throwable failure) {
                    serverFailure.set(failure);
                    listening.countDown();
                    firstFlowClosed.countDown();
                }
            }, "baudot-rue-outbound-provider");
            server.setDaemon(true);
            server.start();

            require(listening.await(TIMEOUT.toMillis(), TimeUnit.MILLISECONDS),
                    "synthetic provider TLS listener did not start");
            if (serverFailure.get() != null) {
                throw new IllegalStateException("synthetic provider failed before outbound flow", serverFailure.get());
            }

            SSLSocketFactory clientFactory = context.getSocketFactory();

            try (SSLSocket first = (SSLSocket) clientFactory.createSocket(host, port)) {
                first.setSoTimeout((int) TIMEOUT.toMillis());
                first.startHandshake();
                require(certificateContainsDnsName(
                                (X509Certificate) first.getSession().getPeerCertificates()[0], DOMAIN),
                        "flow-1 certificate is not bound to provider domain");

                SipChannel channel = new SipChannel(first);
                RegistrationResult registered = register(channel, 1, "flow-1");
                outboundRequireObserved.set(registered.requireOutbound());
                require(registered.accepted(), "flow-1 registration was not accepted");
                require(registered.requireOutbound(), "flow-1 200 did not contain Require: outbound");
                require(FLOW_TIMER.equals(registered.flowTimer()), "flow-1 Flow-Timer drift");

                channel.writeRaw("\r\n\r\n".getBytes(StandardCharsets.US_ASCII));
                byte[] pong = channel.readExact(2);
                keepalivePongObserved.set(pong[0] == '\r' && pong[1] == '\n');
                require(keepalivePongObserved.get(), "flow-1 CRLF pong missing");
                evidence.event("outbound.keepalive.client", Map.of(
                        "pingSent", "true",
                        "pongObserved", "true",
                        "flow", "flow-1"));

                require(firstFlowClosed.await(TIMEOUT.toMillis(), TimeUnit.MILLISECONDS),
                        "provider did not close flow-1 for controlled failure");
                int eof = channel.readOne();
                firstFlowLossDetected.set(eof == -1);
                require(firstFlowLossDetected.get(), "client did not detect flow-1 EOF");
                evidence.event("outbound.flow.failure", Map.of(
                        "flow", "flow-1",
                        "detectedByClient", "true",
                        "kind", "controlled-tls-eof"));
            }

            try (SSLSocket replacement = (SSLSocket) clientFactory.createSocket(host, port)) {
                replacement.setSoTimeout((int) TIMEOUT.toMillis());
                replacement.startHandshake();
                require(certificateContainsDnsName(
                                (X509Certificate) replacement.getSession().getPeerCertificates()[0], DOMAIN),
                        "flow-2 certificate is not bound to provider domain");

                SipChannel channel = new SipChannel(replacement);
                RegistrationResult registered = register(channel, 3, "flow-2");
                require(registered.accepted(), "replacement registration was not accepted");
                require(registered.requireOutbound(), "flow-2 200 did not contain Require: outbound");

                String inbound = channel.readSipMessage();
                inboundRequestOnReplacementFlow.set(
                        inbound.startsWith("OPTIONS " + AOR + " SIP/2.0"));
                require(inboundRequestOnReplacementFlow.get(),
                        "replacement flow did not receive provider-originated OPTIONS");
                String response = options200(inbound);
                channel.writeSipMessage(response);
                evidence.writeBytes(
                        "replacement-flow-inbound-options.request.sip",
                        inbound.getBytes(StandardCharsets.UTF_8));
                evidence.writeBytes(
                        "replacement-flow-inbound-options-200.response.sip",
                        response.getBytes(StandardCharsets.UTF_8));
            }

            server.join(TIMEOUT.toMillis());
            if (serverFailure.get() != null) {
                throw new IllegalStateException("synthetic outbound-flow provider failed", serverFailure.get());
            }

            boolean pass = firstBindingAccepted.get()
                    && outboundRequireObserved.get()
                    && keepalivePingObserved.get()
                    && keepalivePongObserved.get()
                    && firstFlowLossDetected.get()
                    && replacementSameBindingKey.get()
                    && replacementBindingAccepted.get()
                    && inboundRequestOnReplacementFlow.get()
                    && inboundResponseOnReplacementFlow.get();

            evidence.result(Map.ofEntries(
                    Map.entry("scenario.id", SCENARIO),
                    Map.entry("correlation.id", CORRELATION),
                    Map.entry("provider.domain", DOMAIN),
                    Map.entry("registered.number", NUMBER),
                    Map.entry("binding.aor", AOR),
                    Map.entry("binding.sip.instance", INSTANCE),
                    Map.entry("binding.reg.id", REG_ID),
                    Map.entry("flow1.registration.accepted", Boolean.toString(firstBindingAccepted.get())),
                    Map.entry("flow1.require.outbound.observed", Boolean.toString(outboundRequireObserved.get())),
                    Map.entry("flow1.crlf.ping.observed", Boolean.toString(keepalivePingObserved.get())),
                    Map.entry("flow1.crlf.pong.observed", Boolean.toString(keepalivePongObserved.get())),
                    Map.entry("flow1.failure.detected", Boolean.toString(firstFlowLossDetected.get())),
                    Map.entry("flow2.same.binding.key", Boolean.toString(replacementSameBindingKey.get())),
                    Map.entry("flow2.registration.accepted", Boolean.toString(replacementBindingAccepted.get())),
                    Map.entry("flow2.inbound.request.observed", Boolean.toString(inboundRequestOnReplacementFlow.get())),
                    Map.entry("flow2.inbound.response.observed", Boolean.toString(inboundResponseOnReplacementFlow.get())),
                    Map.entry("rfc5626.outbound.flow.proven", Boolean.toString(pass)),
                    Map.entry("rfc5626.conformance.claimed", "false"),
                    Map.entry("live.provider.probed", "false"),
                    Map.entry("media.readiness.proven", "false"),
                    Map.entry("rtt.readiness.proven", "false"),
                    Map.entry("video.readiness.proven", "false"),
                    Map.entry("transport.claim", "ephemeral-self-signed-loopback-tls-only"),
                    Map.entry("claim", "controlled-rfc5626-outbound-flow-recovery-behavior-only"),
                    Map.entry("scenario.result", pass ? "PASS" : "FAIL")));

            return pass ? 0 : 3;
        }
    }

    private static void runServer(
            SSLContext context,
            String host,
            int port,
            EvidenceRecorder evidence,
            CountDownLatch listening,
            CountDownLatch firstFlowClosed,
            AtomicBoolean firstBindingAccepted,
            AtomicBoolean keepalivePingObserved,
            AtomicBoolean replacementSameBindingKey,
            AtomicBoolean replacementBindingAccepted,
            AtomicBoolean inboundResponseOnReplacementFlow) throws Exception {

        SSLServerSocketFactory factory = context.getServerSocketFactory();
        try (SSLServerSocket server = (SSLServerSocket) factory.createServerSocket(
                port, 2, java.net.InetAddress.getByName(host))) {
            server.setSoTimeout((int) TIMEOUT.toMillis());
            listening.countDown();

            String firstBindingKey;
            try (SSLSocket first = (SSLSocket) server.accept()) {
                first.setSoTimeout((int) TIMEOUT.toMillis());
                first.startHandshake();
                SipChannel channel = new SipChannel(first);
                ServerRegistration firstRegistration =
                        acceptRegistration(channel, evidence, 1, "flow-1");
                firstBindingKey = firstRegistration.bindingKey();
                firstBindingAccepted.set(true);

                byte[] ping = channel.readExact(4);
                keepalivePingObserved.set(
                        ping[0] == '\r' && ping[1] == '\n'
                                && ping[2] == '\r' && ping[3] == '\n');
                require(keepalivePingObserved.get(), "flow-1 CRLF keepalive ping missing");
                channel.writeRaw("\r\n".getBytes(StandardCharsets.US_ASCII));
                evidence.event("outbound.keepalive.provider", Map.of(
                        "pingObserved", "true",
                        "pongSent", "true",
                        "flow", "flow-1"));
            } finally {
                firstFlowClosed.countDown();
            }

            try (SSLSocket replacement = (SSLSocket) server.accept()) {
                replacement.setSoTimeout((int) TIMEOUT.toMillis());
                replacement.startHandshake();
                SipChannel channel = new SipChannel(replacement);
                ServerRegistration secondRegistration =
                        acceptRegistration(channel, evidence, 3, "flow-2");
                replacementSameBindingKey.set(
                        firstBindingKey.equals(secondRegistration.bindingKey()));
                require(replacementSameBindingKey.get(),
                        "replacement registration changed AOR/+sip.instance/reg-id binding key");
                replacementBindingAccepted.set(true);

                String options = optionsRequest();
                channel.writeSipMessage(options);
                String response = channel.readSipMessage();
                inboundResponseOnReplacementFlow.set(
                        response.startsWith("SIP/2.0 200")
                                && headerValue(response, "Call-ID").equals(
                                        headerValue(options, "Call-ID")));
                require(inboundResponseOnReplacementFlow.get(),
                        "provider did not receive correlated 200 over replacement flow");
                evidence.event("outbound.replacement.route", Map.of(
                        "sameBindingKey", "true",
                        "inboundRequestSent", "true",
                        "inboundResponseObserved", "true",
                        "flow", "flow-2"));
            }
        }
    }

    private static RegistrationResult register(
            SipChannel channel,
            int initialCseq,
            String flowName) throws Exception {
        String nonce = "baudot-outbound-nonce-" + flowName;
        String cnonce = "baudot-outbound-cnonce-" + flowName;
        String first = registerRequest(initialCseq, null);
        channel.writeSipMessage(first);
        String challenge = channel.readSipMessage();
        require(challenge.startsWith("SIP/2.0 401"), flowName + " initial REGISTER was not challenged");
        require(challenge.contains("nonce=\"" + nonce + "\""), flowName + " nonce drift");

        String auth = digestAuthorization(nonce, cnonce);
        String second = registerRequest(initialCseq + 1, auth);
        channel.writeSipMessage(second);
        String ok = channel.readSipMessage();
        return new RegistrationResult(
                ok.startsWith("SIP/2.0 200"),
                headerContainsToken(ok, "Require", "outbound"),
                headerValue(ok, "Flow-Timer"));
    }

    private static ServerRegistration acceptRegistration(
            SipChannel channel,
            EvidenceRecorder evidence,
            int initialCseq,
            String flowName) throws Exception {
        String nonce = "baudot-outbound-nonce-" + flowName;
        String cnonce = "baudot-outbound-cnonce-" + flowName;

        String first = channel.readSipMessage();
        validateOutboundRegister(first, initialCseq);
        channel.writeSipMessage(response401(first, nonce));

        String second = channel.readSipMessage();
        validateOutboundRegister(second, initialCseq + 1);
        String authorization = headerValue(second, "Authorization");
        require(digestAuthorization(nonce, cnonce).equals(authorization),
                flowName + " Digest response did not verify");

        String bindingKey = bindingKey(second);
        channel.writeSipMessage(response200(second));
        evidence.writeBytes(
                flowName + "-register-authenticated.request.redacted.sip",
                redactAuthorization(second).getBytes(StandardCharsets.UTF_8));
        evidence.event("outbound.registration.provider", Map.of(
                "flow", flowName,
                "bindingKeyPreserved", "true",
                "digestVerified", "true",
                "requireOutboundSent", "true",
                "flowTimer", FLOW_TIMER));
        return new ServerRegistration(bindingKey);
    }

    private static void validateOutboundRegister(String request, int cseq) {
        require(request.startsWith("REGISTER " + REGISTER_URI + " SIP/2.0"),
                "REGISTER target drift");
        require(Integer.toString(cseq).equals(cseqNumber(request)),
                "REGISTER CSeq drift");
        require(headerContainsToken(request, "Supported", "outbound"),
                "Supported: outbound missing");
        String contact = headerValue(request, "Contact");
        require(contact != null && contact.contains("reg-id=" + REG_ID),
                "reg-id missing");
        require(contact.contains("+sip.instance=\"" + INSTANCE + "\""),
                "+sip.instance missing");
    }

    private static String bindingKey(String request) {
        String contact = headerValue(request, "Contact");
        String instance = contactParameter(contact, "+sip.instance");
        String regId = contactParameter(contact, "reg-id");
        return headerValue(request, "To") + "|" + instance + "|" + regId;
    }

    private static String contactParameter(String contact, String name) {
        if (contact == null) {
            return "";
        }
        for (String part : contact.split(";")) {
            String trimmed = part.trim();
            if (trimmed.startsWith(name + "=")) {
                return trimmed.substring(name.length() + 1).replace("\"", "");
            }
        }
        return "";
    }

    private static String registerRequest(int cseq, String authorization) {
        String branch = "z9hG4bK-baudot-outbound-" + cseq;
        StringBuilder message = new StringBuilder();
        message.append("REGISTER ").append(REGISTER_URI).append(" SIP/2.0\r\n");
        message.append("Via: SIP/2.0/TLS 127.0.0.1:5171;branch=")
                .append(branch).append(";rport\r\n");
        message.append("Max-Forwards: 70\r\n");
        message.append("From: <").append(AOR).append(">;tag=baudot-rue-outbound\r\n");
        message.append("To: <").append(AOR).append(">\r\n");
        message.append("Call-ID: ").append(CALL_ID).append("\r\n");
        message.append("CSeq: ").append(cseq).append(" REGISTER\r\n");
        message.append("Contact: <sip:").append(NUMBER)
                .append("@127.0.0.1:5171;transport=tls>;reg-id=").append(REG_ID)
                .append(";+sip.instance=\"").append(INSTANCE).append("\"\r\n");
        message.append("Supported: path, outbound\r\n");
        message.append("Expires: 300\r\n");
        if (authorization != null) {
            message.append("Authorization: ").append(authorization).append("\r\n");
        }
        message.append("Content-Length: 0\r\n\r\n");
        return message.toString();
    }

    private static String response401(String request, String nonce) {
        return responseBase(request, 401, "Unauthorized")
                + "WWW-Authenticate: Digest realm=\"" + REALM + "\", nonce=\"" + nonce
                + "\", algorithm=MD5, qop=\"auth\"\r\nContent-Length: 0\r\n\r\n";
    }

    private static String response200(String request) {
        return responseBase(request, 200, "OK")
                + "Require: outbound\r\n"
                + "Flow-Timer: " + FLOW_TIMER + "\r\n"
                + "Expires: 300\r\n"
                + "Content-Length: 0\r\n\r\n";
    }

    private static String responseBase(String request, int status, String reason) {
        StringBuilder response = new StringBuilder("SIP/2.0 ")
                .append(status).append(' ').append(reason).append("\r\n");
        appendResponseHeader(response, request, "Via");
        appendResponseHeader(response, request, "From");
        appendResponseHeader(response, request, "To");
        appendResponseHeader(response, request, "Call-ID");
        appendResponseHeader(response, request, "CSeq");
        return response.toString();
    }

    private static void appendResponseHeader(StringBuilder response, String request, String name) {
        String value = headerValue(request, name);
        if (value != null) {
            response.append(name).append(": ").append(value).append("\r\n");
        }
    }

    private static String optionsRequest() {
        return "OPTIONS " + AOR + " SIP/2.0\r\n"
                + "Via: SIP/2.0/TLS " + DOMAIN + ";branch=z9hG4bK-baudot-inbound-options\r\n"
                + "Max-Forwards: 70\r\n"
                + "From: <sip:provider@" + DOMAIN + ">;tag=baudot-provider-options\r\n"
                + "To: <" + AOR + ">\r\n"
                + "Call-ID: baudot-outbound-inbound-options@" + DOMAIN + "\r\n"
                + "CSeq: 1 OPTIONS\r\n"
                + "Content-Length: 0\r\n\r\n";
    }

    private static String options200(String request) {
        return responseBase(request, 200, "OK")
                + "Content-Length: 0\r\n\r\n";
    }

    private static String digestAuthorization(String nonce, String cnonce) throws Exception {
        String ha1 = md5(USERNAME + ":" + REALM + ":" + PASSWORD);
        String ha2 = md5("REGISTER:" + REGISTER_URI);
        String response = md5(
                ha1 + ":" + nonce + ":00000001:" + cnonce + ":auth:" + ha2);
        return "Digest username=\"" + USERNAME + "\", realm=\"" + REALM
                + "\", nonce=\"" + nonce + "\", uri=\"" + REGISTER_URI
                + "\", response=\"" + response
                + "\", algorithm=MD5, qop=auth, nc=00000001, cnonce=\"" + cnonce + "\"";
    }

    private static String md5(String value) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("MD5");
        byte[] bytes = digest.digest(value.getBytes(StandardCharsets.UTF_8));
        StringBuilder result = new StringBuilder();
        for (byte b : bytes) {
            result.append(String.format("%02x", b));
        }
        return result.toString();
    }

    private static SSLContext sslContext(Path keyStorePath, char[] password) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (var in = Files.newInputStream(keyStorePath)) {
            store.load(in, password);
        }
        KeyManagerFactory kmf =
                KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(store, password);
        TrustManagerFactory tmf =
                TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(store);
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(kmf.getKeyManagers(), tmf.getTrustManagers(), null);
        return context;
    }

    private static boolean certificateContainsDnsName(
            X509Certificate certificate, String expected) throws Exception {
        Collection<List<?>> names = certificate.getSubjectAlternativeNames();
        if (names == null) {
            return false;
        }
        for (List<?> entry : names) {
            if (entry.size() >= 2
                    && Integer.valueOf(2).equals(entry.get(0))
                    && expected.equalsIgnoreCase(String.valueOf(entry.get(1)))) {
                return true;
            }
        }
        return false;
    }

    private static String cseqNumber(String message) {
        String cseq = headerValue(message, "CSeq");
        if (cseq == null) {
            return "";
        }
        String[] parts = cseq.split("\\s+");
        return parts.length > 0 ? parts[0] : "";
    }

    private static String headerValue(String message, String name) {
        String prefix = name.toLowerCase() + ":";
        for (String line : message.split("\\r?\\n")) {
            if (line.toLowerCase().startsWith(prefix)) {
                return line.substring(line.indexOf(':') + 1).trim();
            }
        }
        return null;
    }

    private static boolean headerContainsToken(String message, String name, String token) {
        String value = headerValue(message, name);
        if (value == null) {
            return false;
        }
        for (String item : value.split(",")) {
            if (token.equalsIgnoreCase(item.trim())) {
                return true;
            }
        }
        return false;
    }

    private static String redactAuthorization(String message) {
        return message.replaceAll(
                "(?im)^Authorization:.*$", "Authorization: Digest [redacted]");
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "missing required environment variable: " + name);
        }
        return value;
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    private record RegistrationResult(
            boolean accepted, boolean requireOutbound, String flowTimer) {
    }

    private record ServerRegistration(String bindingKey) {
    }

    private static final class SipChannel {
        private final InputStream in;
        private final OutputStream out;

        private SipChannel(SSLSocket socket) throws Exception {
            this.in = new BufferedInputStream(socket.getInputStream());
            this.out = new BufferedOutputStream(socket.getOutputStream());
        }

        private void writeSipMessage(String message) throws Exception {
            writeRaw(message.getBytes(StandardCharsets.UTF_8));
        }

        private void writeRaw(byte[] bytes) throws Exception {
            out.write(bytes);
            out.flush();
        }

        private int readOne() throws Exception {
            return in.read();
        }

        private byte[] readExact(int length) throws Exception {
            byte[] result = new byte[length];
            int offset = 0;
            while (offset < length) {
                int count = in.read(result, offset, length - offset);
                if (count < 0) {
                    throw new IllegalStateException(
                            "unexpected EOF while reading " + length + " bytes");
                }
                offset += count;
            }
            return result;
        }

        private String readSipMessage() throws Exception {
            byte[] marker = new byte[] {'\r', '\n', '\r', '\n'};
            java.io.ByteArrayOutputStream bytes = new java.io.ByteArrayOutputStream();
            int matched = 0;
            while (true) {
                int value = in.read();
                if (value < 0) {
                    throw new IllegalStateException(
                            "unexpected EOF while reading SIP headers");
                }
                bytes.write(value);
                if ((byte) value == marker[matched]) {
                    matched++;
                    if (matched == marker.length) {
                        break;
                    }
                } else {
                    matched = ((byte) value == marker[0]) ? 1 : 0;
                }
                if (bytes.size() > 65536) {
                    throw new IllegalStateException("SIP message exceeds harness limit");
                }
            }
            return bytes.toString(StandardCharsets.UTF_8);
        }
    }
}
